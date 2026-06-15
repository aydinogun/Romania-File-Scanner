# ANC Dosar Arama Motoru

cetatenie.just.ro üzerindeki resmi PDF'lerde Romanya vatandaşlık **dosya numarası** arar.

## Yerelde çalıştırma
```bash
pip install -r requirements.txt
streamlit run app.py
```
Tarayıcıda http://localhost:8501 açılır.

## Streamlit Cloud'a yükleme (ücretsiz, herkese açık link)
1. Bu klasörü bir GitHub deposuna koy.
2. https://share.streamlit.io -> "New app" -> depoyu ve `app.py`yi seç.
3. Deploy. Sana `https://...streamlit.app` linki verir.

`packages.txt` taranmış PDF'ler için OCR sistem paketlerini kurar
(poppler + tesseract). OCR'a ihtiyacın yoksa `packages.txt`'i ve
`requirements.txt`'teki son iki satırı silebilirsin — uygulama daha hızlı açılır.

## Nasıl çalışır (5 adım)
1. **Link keşfi** — seçilen maddenin "ordine" sayfası çekilir, içindeki tüm
   `.pdf` linkleri toplanır (`discover_pdf_links`).
2. **İndirme** — seçilen PDF `requests` ile indirilir, `st.cache_data` ile
   önbelleğe alınır (aynı PDF tekrar inmez).
3. **Metin çıkarma** — `pdfplumber` ile metin okunur. Metin çıkmazsa PDF
   taranmıştır; OCR (pdf2image + pytesseract) devreye girer.
4. **Arama** — dosya numarası normalize edilir (`8620/RD/2022 -> 8620RD2022`)
   ve satır satır aranır.
5. **Sonuç** — eşleşen satır(lar) ve PDF linki gösterilir.

## Dikkat
- WordPress slug'ları (ör. `/ordine-articolul-1-1/`) değişebilir; link gelmezse
  `ARTICLE_PAGES` sözlüğünü güncelle.
- Siteye saygılı ol: önbellek sayesinde gereksiz indirme olmaz; çok sık tarama yapma.
- Bu araç sadece resmi olarak **kamuya açık** PDF'leri okur.
