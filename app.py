# -*- coding: utf-8 -*-
"""
ANC Dosar Sorgulama
===================
Kullanıcı SADECE dosya numarasını girer. Madde seçmez.
Sistem girilen numaradan kayıt yılını çıkarır, o yılın bütün madde
(art. 8 / 8^1 / 10 / 11) "stadiu dosar" PDF'lerini tarar ve sonucu verir:

  - SOLUȚIE doluysa  -> Ordin numarası (dosya çözülmüş)
  - SOLUȚIE boşsa    -> TERMEN tarihi (komisyon tarihi, işlemde)
"""

import io
import re
import requests
import pdfplumber
import streamlit as st
from bs4 import BeautifulSoup

BASE = "https://cetatenie.just.ro"

# Tüm "stadiu dosar" PDF'lerinin linklendiği sayfalar.
# Hepsi taranır; kullanıcı madde seçmez.
SOURCE_PAGES = [
    f"{BASE}/stadiu-dosar/",
    f"{BASE}/ordine-articolul-1-1/",        # art. 11
    f"{BASE}/ordine-articolul-10/",         # art. 10
    f"{BASE}/ordine-articolul-8/",          # art. 8
    f"{BASE}/ordine-articolul-8-indice-1/", # art. 8^1
]

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/124.0 Safari/537.36"),
}
TIMEOUT = 30

# --- Regex desenleri --------------------------------------------------------
RE_DATE  = re.compile(r"\b\d{1,2}\.\d{1,2}\.\d{4}\b")            # 15.03.2024
RE_ORDER = re.compile(r"\b\d{1,6}\s*/\s*(?:RD|P|A|RE|R)\s*/\s*\d{4}\b", re.I)
RE_YEAR  = re.compile(r"(20\d{2})")


# ---------------------------------------------------------------------------
# 1) Bütün kaynak sayfalardaki PDF linklerini topla
# ---------------------------------------------------------------------------
@st.cache_data(ttl=3600, show_spinner=False)
def discover_all_pdfs() -> list[dict]:
    pdfs, seen = [], set()
    for page in SOURCE_PAGES:
        try:
            r = requests.get(page, headers=HEADERS, timeout=TIMEOUT)
            r.raise_for_status()
        except Exception:
            continue
        soup = BeautifulSoup(r.text, "html.parser")
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if not href.lower().endswith(".pdf"):
                continue
            if href.startswith("/"):
                href = BASE + href
            if href in seen:
                continue
            seen.add(href)
            name = href.split("/")[-1]
            m = RE_YEAR.search(name) or RE_YEAR.search(href)
            pdfs.append({"url": href, "name": name, "year": m.group(1) if m else "?"})
    return pdfs


# ---------------------------------------------------------------------------
# 2) PDF indir + metin çıkar (gerekirse OCR)
# ---------------------------------------------------------------------------
@st.cache_data(ttl=86400, show_spinner=False)
def fetch_pdf_text(pdf_url: str) -> str:
    r = requests.get(pdf_url, headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    raw = r.content
    parts = []
    with pdfplumber.open(io.BytesIO(raw)) as pdf:
        for page in pdf.pages:
            parts.append(page.extract_text() or "")
    text = "\n".join(parts)
    if text.strip():
        return text
    # OCR yedeği (taranmış PDF)
    try:
        from pdf2image import convert_from_bytes
        import pytesseract
        imgs = convert_from_bytes(raw, dpi=200)
        return "\n".join(pytesseract.image_to_string(i, lang="ron") for i in imgs)
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# 3) Eşleştirme + TERMEN / SOLUȚIE ayrıştırma
# ---------------------------------------------------------------------------
def normalize(s: str) -> str:
    return re.sub(r"[\s./\-]", "", s).upper()


def parse_row(line: str, dossier: str) -> dict:
    """Eşleşen satırı çözümle: termen tarihi ve soluție (ordin) ayır."""
    target = normalize(dossier)
    dates = RE_DATE.findall(line)
    # Satırdaki tüm 'ordin benzeri' tokenlar; dosyanın kendisini çıkar
    orders = [t for t in RE_ORDER.findall(line) if normalize(t) != target]

    if orders:                       # SOLUȚIE dolu -> çözülmüş
        return {"status": "solved", "solutie": orders[0],
                "termen": dates[0] if dates else None, "raw": line.strip()}
    if dates:                        # SOLUȚIE boş, TERMEN var -> işlemde
        return {"status": "pending", "solutie": None,
                "termen": dates[0], "raw": line.strip()}
    return {"status": "unknown", "solutie": None, "termen": None, "raw": line.strip()}


def search_pdf(text: str, dossier: str) -> list[dict]:
    target = normalize(dossier)
    out = []
    for line in text.splitlines():
        if target and target in normalize(line):
            out.append(parse_row(line, dossier))
    return out


# ---------------------------------------------------------------------------
# 4) Arayüz — tek kutu, tek buton
# ---------------------------------------------------------------------------
st.set_page_config(page_title="ANC Dosar Sorgulama", page_icon="🇷🇴", layout="centered")
st.title("🇷🇴 ANC Dosar Sorgulama")
st.caption("Dosya numaranızı girin. Sistem maddeyi kendisi tespit eder ve "
           "Soluție (ordin) veya Termen (tarih) sonucunu verir.")

dossier = st.text_input("Dosya numarası", placeholder="örn. 8620/RD/2022")

if st.button("🔎 Sorgula", type="primary", disabled=not dossier.strip()):
    pdfs = discover_all_pdfs()
    if not pdfs:
        st.error("Kaynak sayfalara ulaşılamadı. Daha sonra tekrar deneyin.")
        st.stop()

    # Numaradaki yılı yakala -> sadece o yılın dosyalarını tara (hızlı + isabetli)
    ym = RE_YEAR.search(dossier)
    if ym:
        target_year = ym.group(1)
        scan = [p for p in pdfs if p["year"] == target_year] or pdfs
        st.caption(f"Kayıt yılı {target_year} tespit edildi · {len(scan)} PDF taranıyor.")
    else:
        scan = pdfs
        st.caption(f"Yıl tespit edilemedi · {len(scan)} PDF taranıyor.")

    found = False
    progress = st.progress(0.0)
    for i, pdf in enumerate(scan, start=1):
        progress.progress(i / len(scan))
        try:
            text = fetch_pdf_text(pdf["url"])
        except Exception:
            continue
        for row in search_pdf(text, dossier):
            found = True
            with st.container(border=True):
                if row["status"] == "solved":
                    st.success(f"✅ ÇÖZÜLDÜ — Ordin (Soluție): **{row['solutie']}**")
                    if row["termen"]:
                        st.write(f"Termen (komisyon tarihi): {row['termen']}")
                elif row["status"] == "pending":
                    st.warning(f"⏳ İŞLEMDE — Termen (komisyon tarihi): **{row['termen']}**")
                    st.write("Soluție sütunu henüz boş (ordin verilmemiş).")
                else:
                    st.info("Eşleşme bulundu, sütunlar otomatik ayrıştırılamadı.")
                st.caption(f"Kaynak: {pdf['name']}")
                st.code(row["raw"], language=None)
                st.markdown(f"[PDF'i aç]({pdf['url']})")
    progress.empty()

    if not found:
        st.info(
            "Bu numara taranan PDF'lerde bulunamadı. Olası nedenler:\n"
            "- Dosya henüz listeye girmemiş (çok yeni kayıt),\n"
            "- Numara/yıl yanlış yazıldı,\n"
            "- İlgili PDF taranmış (resim) ve OCR kapalı."
        )
