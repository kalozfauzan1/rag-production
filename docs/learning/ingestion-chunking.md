# Ingestion Dokumen & Recursive Chunking (task 2)

Catatan belajar task 2. Angka di bagian **Hasil percobaan** adalah pengukuran di mesin ini,
bukan kutipan dokumentasi.

## Konsep

**Ingestion** — rangkaian langkah mengubah file mentah (PDF, HTML, Markdown) menjadi potongan
teks terstruktur yang siap dicari. Analogi: menyiapkan bahan masakan sebelum memasak — kalau
bahannya masih berbentuk karung, tidak ada yang bisa dipakai.

**Chunking** — memotong dokumen panjang menjadi potongan kecil (**chunk**). Kenapa perlu:
model embedding punya batas panjang masukan, dan pencarian lebih tepat kalau satu potongan
membahas satu topik. Analogi: buku yang dipecah jadi kartu catatan per bagian, supaya bisa
dicari per kartu, bukan per buku.

**Token** — satuan teks yang dikenali model. Bukan karakter, bukan kata: satu kata umum
bisa jadi satu token, kata langka bisa terpecah jadi beberapa. Karena batas model dinyatakan
dalam token, ukuran chunk juga dipakai dalam token — lihat temuan BPE di bawah.

**Recursive chunking** — memotong dari batas paling "besar makna"-nya dulu (antar-bab,
antar-paragraf), dan baru turun ke batas yang lebih halus (antar-kalimat, antar-kata) kalau
satu potongan masih terlalu panjang.

**Overlap** — beberapa kata terakhir chunk sebelumnya disalin ke awal chunk berikutnya, supaya
kalimat yang terpotong tidak kehilangan konteks saat dicari. Analogi: mengulang satu kalimat
terakhir sebelum melanjutkan cerita.

**OCR (Optical Character Recognition)** — mengubah gambar teks menjadi teks digital. Diperlukan
untuk PDF hasil scan; belum didukung di task ini, dan PDF seperti itu ditolak dengan pesan
jelas. Alternatifnya: Tesseract (open source, ringan, akurasi sedang), PaddleOCR, atau model
vision (akurat tapi butuh GPU/biaya) — dibahas kalau nanti benar-benar dibutuhkan.

**PDF "teks digital" vs "hasil scan"** — PDF hasil export (Word/LaTeX) menyimpan teksnya
sebagai teks, bisa dibaca langsung. PDF hasil scan hanyalah gambar per halaman, jadi tanpa OCR
sama sekali tidak ada teks yang bisa diambil.

## Alur data di repo ini

```text
POST /api/documents  (multipart)
   │  ekstensi diperiksa · ukuran dibatasi · sha256 dihitung (doc_id)
   ▼
data/uploads/{doc_id}{ext}
   │  JobRunner.submit()  → respons 202 langsung dikirim
   ▼
asyncio.to_thread(ingest_file)          ← parsing tidak boleh memblokir event loop
   │
   ├─ extract    .pdf → pdfplumber        (blocks + nomor halaman)
   │             .html/.htm → trafilatura (blocks + section dari heading)
   │             .md/.txt → pembaca teks  (blocks + section dari heading)
   ├─ normalize  hyphen terpotong disambung, spasi & baris kosong dirapikan
   ├─ chunk      offset karakter → batas per chunk → geser ke separator → overlap
   └─ persist    data/documents/{doc_id}/meta.json + chunks.jsonl
   ▼
GET /api/documents/{id}         → status: queued | processing | completed | failed
GET /api/documents/{id}/chunks  → isi chunk untuk diperiksa
```

## Keputusan & kenapa

### 1. pdfplumber untuk PDF (D9)

| Opsi | Kelebihan | Kekurangan | Lisensi |
| --- | --- | --- | --- |
| **pdfplumber** (dipilih) | akses char/word/posisi, bagus untuk layout | paling lambat; di atas pdfminer.six | MIT |
| PyMuPDF | paling cepat | AGPL-3.0 — demo publik bisa mewajibkan membuka kode | AGPL / komersial |
| pypdfium2 | cepat, lisensi longgar | bantuan layout lebih sedikit | Apache-2.0 |
| pypdf | murni Python | ekstraksi paling dasar | BSD-3 |

Kecepatan belum jadi masalah di skala ini (150 halaman ≈ 6,5 detik), dan lisensi longgar lebih
aman untuk repo portofolio. **Kapan pindah:** kalau ingestion jadi bottleneck nyata, PyMuPDF
adalah jalurnya — dengan konsekuensi lisensi yang harus diterima sadar.

### 2. trafilatura untuk HTML (D10)

Masalah HTML bukan parsing, tapi membuang boilerplate (menu, iklan, footer). trafilatura
memberi skor kepadatan teks dan mengambil bagian artikelnya. Alternatif: readability-lxml
(lebih sederhana, kurang rapi di halaman non-artikel) atau menulis heuristik sendiri dengan
BeautifulSoup (rapuh, memakan waktu untuk masalah yang bukan inti).

### 3. Extractor menghasilkan blocks, bukan satu string (D14)

Sitasi task 5 butuh asal-usul: halaman berapa, section mana. Karena itu extractor mengembalikan
`Block(text, order, page, section)`, bukan teks panjang. Harga: setiap extractor harus
memetakan struktur dokumennya.

### 4. Chunking berbasis offset karakter, bukan penjumlahan token per potongan (D15)

Ini temuan paling penting task ini, dan awalnya salah:

- Rencana pertama: pecah teks rekursif per separator menjadi potongan kecil, lalu jumlahkan
  token tiap potongan untuk mengisi anggaran 704 token.
- Hasil terukur: chunk hanya **234 token** — sepertiga dari yang diminta.
- Sebabnya: **tokenisasi BPE (Byte Pair Encoding) tidak aditif**. `count_tokens("kata ")`
  sendirian ≈ 3 token, tetapi kontribusinya di dalam teks panjang ≈ 1 token, karena BPE
  menggabungkan pasangan karakter yang sering muncul bersama. Menjumlahkan angka parsial
  melebih-lebihkan ukuran.
- Perbaikan: dokumen dijadikan satu teks; batas tiap chunk dicari sebagai offset karakter
  dengan `count_tokens` pada slice aslinya (binary search), lalu digeser ke separator terdekat.

**Pelajaran umum:** jangan pernah menjumlahkan hasil tokenizer secara parsial. Hitung selalu
pada teks utuh yang benar-benar dikirim ke model.

### 5. Section sebagai batas keras

Chunk tidak boleh melintasi pergantian section. Alasannya kualitas sitasi: chunk yang mencampur
dua bab membuat rujukan "bagian X" menyesatkan. Konsekuensinya terukur di percobaan: dokumen
dengan banyak sub-heading menghasilkan chunk kecil.

### 6. Job in-process + `asyncio.to_thread` (D11)

Unggahan dijawab `202` dan diproses di background, karena PDF besar butuh detik-an. Yang berat
dijalankan lewat `asyncio.to_thread`; percobaan di bawah menunjukkan apa yang terjadi kalau
tidak. Alternatif yang ditolak: queue Redis/Celery (satu layanan tambahan untuk masalah yang
belum ada).

## Hasil percobaan

**1. PDF 3 halaman → 1 chunk** (`laporan.pdf`, 3,5 KB):

```text
567202459ab0  completed  chunk=1 block=3 page=3  laporan.pdf
   chunk[0]: page=1 chars=2419   token_count=636
```

**2. Markdown dokumentasi → chunk per section** (`panduan-sse.md`, 13,6 KB — dokumen learning task 1):

```text
b6a2a69f6e69  completed  chunk=17 block=46 page=None  panduan-sse.md
   min=41  max=632  rata2=268 token
   jumlah chunk=17, section unik=17, section dengan >1 chunk: tidak ada
```

Setiap chunk berisi tepat satu section. Dokumen ini punya banyak sub-heading (`###`) sehingga
chunk-nya kecil-kecil. Ini **trade-off yang disadari**: sitasi jadi presisi, ukuran jadi tidak
seragam.

**3. PDF 150 halaman, parsing di thread** (`besar.pdf`, 359 KB):

```text
ping: n=55 max_gap=0.57s rata2=0.36s      (target ping: 0.30s)
  [ 1.11s] upload dikirim (359419 byte)
  [ 7.59s] ingestion completed: 150 chunk dari 150 halaman
```

**4. PDF 150 halaman, parsing inline di event loop** (`besar3.pdf`, 359 KB — dokumen setara):

```text
ping: n=42 max_gap=6.43s rata2=0.48s
  [ 1.12s] upload dikirim (359269 byte)
  [ 7.48s] ingestion completed: 150 chunk dari 150 halaman
```

| Variasi | Durasi ingestion | Max jeda `: ping` |
| --- | --- | --- |
| `asyncio.to_thread` | 6,47 detik | **0,57 detik** |
| inline di event loop | 6,36 detik | **6,43 detik** |

Max gap 6,43 detik ≈ durasi ingestion 6,36 detik: dengan parsing inline, event loop berhenti
total selama pekerjaan berjalan — semua koneksi SSE (chat) ikut mati. Dengan `to_thread`, jeda
terburuk 0,57 detik: masih ~2× target, artinya loop sesekali tetap tertahan (pdfminer murni
Python sehingga GIL dipakai bersama), tetapi tidak beku.

**5. Unduhan kosakata tiktoken** — `cl100k_base` (~1,7 MB) diunduh sekali pada pemakaian
pertama dan disimpan di cache; di mesin ini butuh **44 detik**. Percobaan pertama gagal karena
koneksi terputus di tengah unduhan; percobaan kedua berhasil. Konsekuensi praktis: CI atau
lingkungan offline harus menyiapkan cache ini lebih dulu (mis. `TIKTOKEN_CACHE_DIR`).

**Yang mengejutkan:**

- Token tidak aditif (item 4 di atas) — kesalahan desain yang ketahuan dari satu angka.
- Chunk PDF cenderung **sejajar batas halaman** karena snapping separator memilih `\n\n`
  (batas antar-block) bila masih dalam 40% terakhir rentang. Efeknya: 1 halaman = 1 chunk
  (~540 token) untuk dokumen ini, bagus untuk sitasi.
- Markdown dengan banyak sub-heading menghasilkan chunk sekecil 41 token.

## Failure mode

| Kegagalan | Gejala | Perilaku sistem | Deteksi |
| --- | --- | --- | --- |
| PDF hasil scan | `status: failed` | pesan menyebut OCR; tidak ada teks kosong yang lolos | `meta.json.error` |
| PDF rusak/terenkripsi | `status: failed` | error ditangkap, pesan menyebut penyebabnya | log + `meta.json.error` |
| Ekstensi tidak didukung | HTTP 415 | ditolak sebelum file disimpan permanen | respons API |
| Isi `.pdf` tidak diawali `%PDF-` | HTTP 415 | file sementara dihapus, tidak masuk `uploads/` | respons API |
| File > `MAX_UPLOAD_BYTES` | HTTP 413 | pembacaan dihentikan di tengah stream | respons API |
| Server restart saat memproses | `status: failed` ("Server restart…") | status dihitung saat dibaca; dokumen bisa diunggah ulang untuk retry | `resolve_status` |
| Parser menggantung di file aneh | `processing` selamanya | **belum ada timeout** — utang yang diketahui untuk task 9 | — |
| HTML tanpa isi artikel | `completed`, 0 chunk | bukan error; dokumen kosong dianggap sah | `chunk_count = 0` |

## Catatan produksi

- **Waktu proses:** 150 halaman ≈ 6,5 detik CPU (pdfplumber). Ratusan dokumen berarti menit-an;
  itu alasan wajar memindahkan pekerjaan ini ke worker terpisah nanti.
- **Biaya:** task ini belum memakai API berbayar. Biaya baru muncul di task 3 (embedding) —
  jumlah chunk menentukan biayanya, jadi chunk yang terlalu kecil berarti pemborosan.
- **Penyimpanan:** `chunks.jsonl` bisa dibaca mata dan langsung jadi input task 3–4. Setelah
  vector DB ada (task 4), JSONL tetap berguna sebagai artefak pemeriksaan.
- **Job hilang saat restart:** konsekuensi desain in-process. Yang penting: statusnya tidak
  menggantung — `resolve_status` menandainya gagal dan unggahan ulang memicu retry.
- **Batas ukuran upload:** 20 MB default. Untuk dokumen lebih besar, naikkan lewat `.env`
  sekaligus sadari bahwa waktu parsing juga naik.

## Cara menjalankan & menguji

```powershell
uv sync
uv run uvicorn app.main:app --reload          # server
uv run pytest -v                              # 71 test
uv run ruff check . ; uv run ruff format --check .
```

Unggah dan periksa:

```powershell
curl.exe -sS -X POST http://127.0.0.1:8000/api/documents -F "file=@dokumen.pdf;filename=dokumen.pdf"
curl.exe -sS http://127.0.0.1:8000/api/documents
Get-Content data/documents/*/meta.json -Raw
```

Uji jalur gagal (deteksi scan):

```powershell
# file PDF tanpa lapisan teks → status failed dengan pesan OCR
curl.exe -sS -X POST http://127.0.0.1:8000/api/documents -F "file=@kosong.pdf;filename=kosong.pdf"
```

## Poin Kunci

- **Token bukan karakter, dan tokenizer tidak bisa dijumlahkan secara parsial.** Ukuran chunk
  harus dihitung dari teks aslinya, bukan dari potongan-potongan kecil.
- Metadata (halaman/section) harus diambil saat ekstraksi; menambahkannya belakangan tidak
  mungkin karena informasi asalnya sudah hilang.
- Section sebagai batas keras membuat sitasi presisi, dengan harga ukuran chunk tidak seragam.
- `asyncio.to_thread` bukan optimasi kosmetik: tanpa itu, satu ingestion PDF membekukan semua
  koneksi SSE selama 6,4 detik (terukur).
- `doc_id` = SHA-256 isi file: upload ulang jadi idempotent, dan nama file dari client tidak
  pernah menyentuh path.

## Eksperimen lanjutan

1. **Bandingkan dengan `RecursiveCharacterTextSplitter` (LangChain)** pada dokumen yang sama:
   ukur sebaran ukuran chunk dan berapa banyak chunk yang melintasi batas section. Ini juga
   menjawab "apa yang framework sembunyikan".
2. **Chunking semantik:** potong berdasarkan perubahan topik (embedding antar-kalimat + deteksi
   titik belok), lalu bandingkan hasil retrieval-nya di task 4–5 dengan chunking mekanis ini.
3. **Batch ingestion:** jalankan 20 dokumen sekaligus, ukur apakah `to_thread` perlu diganti
   thread pool berukuran tetap (`max_workers`) supaya PDF besar tidak saling berebut.

## Glosarium

| Istilah | Kepanjangan / asal | Arti di konteks ini |
| --- | --- | --- |
| Ingestion | — | rangkaian extract → normalize → chunk → simpan |
| Chunk | — | potongan teks hasil pemotongan dokumen |
| Token | — | satuan teks yang dikenali model; bukan karakter, bukan kata |
| BPE | *Byte Pair Encoding* | algoritma tokenizer yang menggabungkan pasangan karakter/simbol yang sering muncul bersama |
| OCR | *Optical Character Recognition* | mengubah gambar teks menjadi teks digital; belum didukung di sini |
| Boilerplate | — | bagian halaman web yang bukan isi (menu, iklan, footer) |
| pdfplumber | — | library Python pembaca PDF (MIT), di atas pdfminer.six |
| trafilatura | — | library Python ekstraksi isi artikel dari HTML (Apache-2.0) |
| tiktoken | — | library tokenizer OpenAI; `cl100k_base` dipakai `text-embedding-3-*` |
| GIL | *Global Interpreter Lock* | kunci yang membuat satu proses Python hanya menjalankan satu thread pada satu waktu; CPU-bound tidak jadi paralel, tapi event loop tetap dapat giliran |
| Thread pool | — | kumpulan thread yang dipakai ulang untuk menjalankan pekerjaan sinkron di luar event loop |
| JSONL | *JSON Lines* | format teks: satu objek JSON per baris |
| SHA-256 | *Secure Hash Algorithm, 256-bit* | sidik jari isi file; dipakai sebagai `doc_id` |
| Idempotent | — | operasi yang diulang menghasilkan keadaan sama, bukan duplikat |
| Multipart | *multipart/form-data* | cara HTTP mengirim file lewat form |
| Header / heading | — | judul bagian dokumen; di sini dipakai sebagai metadata `section` |
| Hard bound | — | batas yang tidak boleh dilanggar chunker (pergantian section) |

## Referensi

- pdfplumber: <https://github.com/jsvine/pdfplumber>
- trafilatura: <https://trafilatura.readthedocs.io/>
- tiktoken: <https://github.com/openai/tiktoken>
- Starlette `UploadFile`: <https://www.starlette.io/requests/>
