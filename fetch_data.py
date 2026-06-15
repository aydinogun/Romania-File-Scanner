# -*- coding: utf-8 -*-
"""
fetch_data.py — Veri indirme / hazırlama script'i
=================================================
Bunu KENDİ BİLGİSAYARINDA çalıştır (senin IP'in siteye eriştiği için çalışır):

    pip install -r requirements.txt
    python fetch_data.py

Ne yapar:
  1) cetatenie.just.ro kaynak sayfalarından bütün PDF linklerini bulur,
  2) her PDF'i indirir, metnini çıkarır (gerekirse OCR),
  3) hepsini  data/index.json  içine yazar.

Sonra  data/  klasörünü GitHub'a yükle. Streamlit uygulaması bu dosyadan arar
(canlı internete ihtiyaç duymaz) — böylece bulutta da çalışır.
Veriyi güncellemek için script'i tekrar çalıştırıp data/ klasörünü yeniden yükle.
"""

import io
import re
import os
import json
import time
import requests
import pdfplumber
from bs4 import BeautifulSoup

BASE = "https://cetatenie.just.ro"
SOURCE_PAGES = [
    f"{BASE}/stadiu-dosar/",
    f"{BASE}/ordine-articolul-1-1/",
    f"{BASE}/ordine-articolul-10/",
    f"{BASE}/ordine-articolul-8/",
    f"{BASE}/ordine-articolul-8-indice-1/",
]
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/124.0 Safari/537.36"),
    "Accept-Language": "ro,en;q=0.8",
}
RE_YEAR = re.compile(r"(20\d{2})")
OUT_DIR = "data"


def discover():
    pdfs, seen = [], set()
    for page in SOURCE_PAGES:
        try:
            r = requests.get(page, headers=HEADERS, timeout=60)
            r.raise_for_status()
        except Exception as e:
            print(f"  ! {page} okunamadı: {e}")
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
            pdfs.append({"url": href, "name": name,
                         "year": m.group(1) if m else "?"})
        print(f"  + {page}  ({len(seen)} PDF toplam)")
    return pdfs


def extract_text(raw: bytes) -> str:
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


def main():
    print("1) PDF linkleri keşfediliyor...")
    pdfs = discover()
    if not pdfs:
        print("HİÇ PDF bulunamadı. Siteye bu bilgisayardan erişebildiğinden emin ol.")
        return

    print(f"2) {len(pdfs)} PDF indirilip metni çıkarılıyor...")
    index = []
    for i, p in enumerate(pdfs, 1):
        try:
            r = requests.get(p["url"], headers=HEADERS, timeout=120)
            r.raise_for_status()
            text = extract_text(r.content)
            index.append({**p, "text": text})
            print(f"  [{i}/{len(pdfs)}] {p['name']}  ({len(text)} karakter)")
        except Exception as e:
            print(f"  [{i}/{len(pdfs)}] {p['name']}  HATA: {e}")
        time.sleep(0.5)  # siteye saygılı ol

    os.makedirs(OUT_DIR, exist_ok=True)
    out = os.path.join(OUT_DIR, "index.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False)
    print(f"3) Bitti -> {out}  ({len(index)} PDF kaydedildi)")
    print("   Şimdi  data/  klasörünü GitHub'a yükle.")


if __name__ == "__main__":
    main()
