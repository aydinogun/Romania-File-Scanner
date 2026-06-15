# -*- coding: utf-8 -*-
"""
cetatenie.just.ro — Dosar (Dosya) Arama Motoru
================================================
ANC'nin (Autoritatea Națională pentru Cetățenie) "Stadiu Dosar" bölümünde
maddeye ve yıla göre yayınlanan PDF'lerin içinde DOSYA NUMARASI arar.

Boru hattı (pipeline):
  1) Linkleri keşfet  -> madde sayfasındaki PDF linklerini topla (BeautifulSoup)
  2) PDF'i indir       -> requests (önbellekli)
  3) Metni çıkar       -> pdfplumber (taranmış PDF için OCR opsiyonel)
  4) Ara               -> dosya numarasını normalize edip regex ile bul
  5) Sonucu göster     -> eşleşen satır(lar) + indirme linki
"""

import io
import re
import requests
import pdfplumber
import streamlit as st
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# 0) SABİTLER
# ---------------------------------------------------------------------------
BASE = "https://cetatenie.just.ro"

# Her kanun maddesi -> ANC'deki "ordine" liste sayfası.
# Aşağıdaki adresler 15.06.2026 itibarıyla siteden teyit edildi.
ARTICLE_PAGES = {
    "Art. 11 (redobândire)":     f"{BASE}/ordine-articolul-1-1/",
    "Art. 10 (redobândire)":     f"{BASE}/ordine-articolul-10/",
    "Art. 8 (acordare)":         f"{BASE}/ordine-articolul-8/",
    "Art. 8^1 (acordare)":       f"{BASE}/ordine-articolul-8-indice-1/",
}

HEADERS = {
    # Bot gibi görünmemek için gerçek bir tarayıcı User-Agent'ı kullan
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/124.0 Safari/537.36"),
}
TIMEOUT = 30


# ---------------------------------------------------------------------------
# 1) LİNK KEŞFİ — madde sayfasındaki PDF linklerini topla
# ---------------------------------------------------------------------------
@st.cache_data(ttl=3600, show_spinner=False)
def discover_pdf_links(page_url: str) -> list[dict]:
    """
    Bir madde sayfasını çekip içindeki tüm PDF linklerini döndürür.
    Çıktı: [{"url": "...", "name": "...", "year": "2024"}, ...]
    """
    r = requests.get(page_url, headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    links = []
    seen = set()
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href.lower().endswith(".pdf"):
            continue
        # Göreli linkleri tam URL'ye çevir
        if href.startswith("/"):
            href = BASE + href
        if href in seen:
            continue
        seen.add(href)

        name = href.split("/")[-1]
        # Dosya adından ya da URL yolundan yıl yakala (2017–2026)
        m = re.search(r"(20\d{2})", name) or re.search(r"/(20\d{2})/", href)
        year = m.group(1) if m else "?"
        links.append({"url": href, "name": name, "year": year})

    # Yıla göre tersten sırala (en yeni üstte)
    links.sort(key=lambda x: x["year"], reverse=True)
    return links


# ---------------------------------------------------------------------------
# 2) İNDİR + 3) METİN ÇIKAR  (ikisi birlikte önbelleğe alınır)
# ---------------------------------------------------------------------------
@st.cache_data(ttl=86400, show_spinner=False)
def fetch_pdf_text(pdf_url: str) -> str:
    """
    PDF'i indirir ve içindeki metni döndürür.
    Önce pdfplumber ile dener (metin tabanlı PDF'ler için hızlı ve yeterli).
    Hiç metin çıkmazsa PDF taranmış (resim) demektir -> OCR gerekir (opsiyonel).
    """
    r = requests.get(pdf_url, headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    raw = r.content

    text_parts = []
    with pdfplumber.open(io.BytesIO(raw)) as pdf:
        for page in pdf.pages:
            text_parts.append(page.extract_text() or "")
    text = "\n".join(text_parts)

    # Metin tabanlı PDF'lerin neredeyse tamamı buradan döner.
    if text.strip():
        return text

    # --- OCR YEDEĞİ (taranmış/resim PDF'ler için) ---------------------------
    # Streamlit Cloud'da çalışması için packages.txt'e poppler-utils + tesseract
    # eklemen gerekir (aşağıdaki README'ye bak). Kurulu değilse boş döner.
    try:
        from pdf2image import convert_from_bytes
        import pytesseract
        images = convert_from_bytes(raw, dpi=200)
        ocr = [pytesseract.image_to_string(img, lang="ron") for img in images]
        return "\n".join(ocr)
    except Exception:
        return ""  # OCR yoksa sessizce boş geç


# ---------------------------------------------------------------------------
# 4) ARAMA — dosya numarasını normalize edip metinde bul
# ---------------------------------------------------------------------------
def normalize(s: str) -> str:
    """Boşluk, nokta, tireleri at; büyük harfe çevir. 8620/RD/2022 -> 8620RD2022"""
    return re.sub(r"[\s./\-]", "", s).upper()


def search_in_text(text: str, dossier: str) -> list[str]:
    """
    Metni satır satır gezer; normalize edilmiş dosya numarasını içeren
    satırları döndürür. Hem '8620/RD/2022' hem '8620 / RD / 2022' yakalanır.
    """
    target = normalize(dossier)
    hits = []
    for line in text.splitlines():
        if target and target in normalize(line):
            clean = line.strip()
            if clean:
                hits.append(clean)
    return hits


# ---------------------------------------------------------------------------
# 5) STREAMLIT ARAYÜZÜ
# ---------------------------------------------------------------------------
st.set_page_config(page_title="ANC Dosar Arama", page_icon="🇷🇴", layout="centered")
st.title("🇷🇴 ANC Dosar (Dosya) Arama")
st.caption("cetatenie.just.ro üzerindeki resmi PDF'lerde dosya numaranızı arar.")

with st.sidebar:
    st.header("Ayarlar")
    article = st.selectbox("Kanun maddesi", list(ARTICLE_PAGES.keys()))
    st.divider()
    st.markdown(
        "Veri kaynağı: **Autoritatea Națională pentru Cetățenie**\n\n"
        "Bu araç sadece resmi olarak yayımlanmış PDF'leri okur."
    )

# Seçilen maddenin PDF listesini keşfet
page_url = ARTICLE_PAGES[article]
try:
    pdfs = discover_pdf_links(page_url)
except Exception as e:
    st.error(f"Liste sayfasına ulaşılamadı: {e}")
    st.stop()

if not pdfs:
    st.warning("Bu sayfada PDF linki bulunamadı. Slug değişmiş olabilir, kontrol et.")
    st.stop()

# Tek kutu, tek buton — bütün yıllar otomatik taranır
dossier = st.text_input("Dosya numarası", placeholder="örn. 8620/RD/2022")
year_span = ", ".join(sorted({p["year"] for p in pdfs}, reverse=True))
st.caption(f"Bu maddede {len(pdfs)} PDF var ({year_span}). Hepsi taranacak.")

if st.button("🔎 Tüm yıllarda ara", type="primary", disabled=not dossier.strip()):
    found_any = False
    progress = st.progress(0.0)
    for i, pdf in enumerate(pdfs, start=1):
        progress.progress(i / len(pdfs))
        try:
            text = fetch_pdf_text(pdf["url"])
        except Exception as e:
            st.warning(f"{pdf['name']} okunamadı: {e}")
            continue

        hits = search_in_text(text, dossier)
        if hits:
            found_any = True
            with st.container(border=True):
                st.success(f"✅ Bulundu — {pdf['name']} ({pdf['year']})")
                for h in hits:
                    st.code(h, language=None)
                st.markdown(f"[PDF'i aç]({pdf['url']})")
    progress.empty()

    if not found_any:
        st.info(
            "Bu numara taranan PDF'lerde bulunamadı. Olası nedenler:\n"
            "- Dosya henüz bir 'ordin'e bağlanmamış (işlemde),\n"
            "- Yanlış madde seçildi (10 / 11 / 8 / 8¹),\n"
            "- PDF taranmış (resim) ve OCR kapalı."
        )
