# FastAPI + Async + Streaming SSE (task 1)

Catatan belajar untuk task 1. Semua angka di bagian **Hasil percobaan** adalah hasil
pengukuran di mesin ini, bukan kutipan dari dokumentasi.

## Konsep

**Streaming response.** Analogi: restoran yang menyajikan hidangan satu per satu begitu
matang, bukan menahan semua piring sampai semuanya selesai. Secara teknis: server mengirim
badan response bertahap lewat satu koneksi HTTP yang dibiarkan terbuka, bukan mengirim satu
blok utuh di akhir.

**SSE (Server-Sent Events)** — cara standar mengirim data satu arah dari server ke client
lewat HTTP biasa. Analogi: radio siaran, server bicara terus, client hanya mendengar.

- *Kelebihan:* protokolnya sederhana (teks biasa), lewat HTTP/HTTPS biasa (tembus proxy dan
  firewall), browser punya auto-reconnect untuk `EventSource`.
- *Kekurangan:* satu arah (client tidak bisa mengirim apa pun setelah koneksi terbuka),
  hanya teks (binary harus di-encode, mis. base64), dan ada batas jumlah koneksi per origin
  di browser.
- *Alternatif:* **WebSocket** (dua arah, lebih kompleks, butuh protokol upgrade),
  **long polling** (client bertanya berulang; boros dan lambat), **chunked JSON** (kirim
  potongan JSON di response biasa; tidak ada format standar untuk memisahkan pesan).

**Async generator** — fungsi Python yang bisa `yield` berkali-kali dan `await` di antaranya.
Analogi: kran air yang mengalirkan sedikit-sedikit saat diminta, bukan ember yang harus penuh
dulu. Inilah bentuk paling alami untuk "sumber yang menghasilkan data bertahap" — dan
`StreamingResponse` menerima iterator async apa pun.

**ASGI (Asynchronous Server Gateway Interface)** — kontrak antara server web (uvicorn) dan
framework (FastAPI). WSGI (pendahulunya) sinkron: satu request menempati satu thread sampai
selesai. ASGI mendukung `async`, jadi satu proses bisa melayani ribuan koneksi yang menunggu
tanpa memblokir thread. Streaming butuh ini: koneksi SSE hidup lama sambil menunggu.

**CORS (Cross-Origin Resource Sharing)** — aturan browser yang memblokir JavaScript di
origin A membaca response dari origin B, kecuali server B mengizinkan lewat header. Nanti
frontend Next.js (`localhost:3000`) memanggil API ini (`localhost:8000`) — dua origin
berbeda, jadi izinnya disiapkan sekarang.

## Wire format

Satu frame SSE:

```text
event: token
data: {"text": "Apa"}

```

Aturannya:

| Bagian | Arti |
| --- | --- |
| `event: <nama>` | jenis event (opsional). Client bisa memilih jenis yang dikenal dan mengabaikan sisanya — inilah alasan kita bisa menambah `sources` di task 5 tanpa merusak client lama |
| `data: <teks>` | isi. Beberapa baris `data:` digabung dengan newline oleh client |
| baris kosong | pemisah antar-frame; tanpa ini client menunggu kelanjutan |
| `: <teks>` | komentar; **diabaikan client**, tapi dihitung sebagai trafik oleh proxy — ini yang kita pakai sebagai heartbeat |
| `Content-Type` | `text/event-stream` |

Kita selalu mengirim `data:` sebagai JSON object (`{"text": "..."}`), bukan teks polos,
supaya field baru bisa ditambah tanpa memecah client yang sudah ada.

## Alur data di repo ini

```text
client (curl / demo / nanti Next.js)
   │  POST /api/chat/stream   {"message": "..."}
   ▼
app/api/routes/chat.py         bikin StreamingResponse + header anti-buffer
   │  Annotated[Streamer, Depends(get_streamer)]
   ▼
app/api/deps.py                message -> aliran (nama_event, payload)
   │                           [task 5: diganti pipeline RAG]
   ▼
app/services/fake_llm.py       async generator: potongan teks + jeda
   ▼
app/core/sse.py                producer task + queue:
   │                           - format frame
   │                           - timeout → ": ping"
   │                           - exception → frame error
   │                           - finally → producer.cancel()
   ▼
StreamingResponse              kirim per frame ke client
```

| File | Tanggung jawab |
| --- | --- |
| `app/api/routes/chat.py` | kontrak HTTP: validasi request, header, media type |
| `app/api/deps.py` | pemetaan teks → event + titik ganti saat test |
| `app/services/fake_llm.py` | sumber jawaban (nanti: RAG) |
| `app/core/sse.py` | protokol SSE murni; tidak tahu isi jawaban |

Pemisahan ini yang membuat task 5 nanti bisa mengganti sumber jawaban tanpa menyentuh
`app/core/sse.py`.

## Keputusan & kenapa

### 1. SSE manual, bukan `sse-starlette`

| Opsi | Kelebihan | Kekurangan | Cocok untuk | Hindari saat |
| --- | --- | --- | --- | --- |
| Manual (`StreamingResponse`) | paham wire format, kontrol penuh, tanpa dependency | ping/disconnect/format diurus sendiri | belajar mekanisme, butuh kontrol | fitur harus cepat jadi |
| `sse-starlette` | ping + disconnect otomatis, kode ringkas | detail protokol tersembunyi | produksi cepat | tujuan utamanya belajar |

Dipilih manual karena tujuan task ini memahami mekanismenya. `sse-starlette` tetap jadi
pembanding yang wajar setelah ini.

### 2. Heartbeat pakai producer/consumer, bukan `asyncio.wait_for` langsung

Versi naif terlihat masuk akal:

```python
event, data = await asyncio.wait_for(source.__anext__(), timeout=ping_interval)
```

Masalahnya: saat timeout, `wait_for` **membatalkan await yang sedang berjalan**. Kalau yang
dibatalkan adalah `__anext__()` milik sumber, `CancelledError` menjalar masuk ke generator
sumber dan **mematikannya** — padahal justru saat diam itulah sumber masih bekerja (di task 5:
LLM sedang menghasilkan token pertama). Heartbeat-nya jadi membunuh hal yang ia jaga.

Solusinya: sumber dibaca task terpisah (`produce()`) yang mengisi `asyncio.Queue`; konsumen
hanya menunggu `queue.get()` dengan timeout. Timeout membatalkan `queue.get()` — bukan sumber.

### 3. Dependency bergaya `Annotated[..., Depends(...)]`

Ruff (aturan `B008`) menandai `Depends()` yang ditulis sebagai nilai default argumen. Bentuk
`Annotated` adalah rekomendasi terkini FastAPI dan menghindari pengecualian lint. Dicatat
sebagai D7 di `docs/decisions.md`.

### 4. Konfigurasi logging aplikasi (temuan saat verifikasi)

Uvicorn hanya mengatur logger `uvicorn.*`. Root logger tidak diberi handler, sehingga
`logger.info(...)` dari kode kita **tidak muncul sama sekali** — pesan "client disconnect"
hilang tanpa jejak. Perbaikannya: `logging.basicConfig(...)` di `create_app()`.

### 5. Pesan log sengaja ASCII (temuan encoding Windows)

Percobaan pertama memakai em-dash (`—`) di pesan log. Saat stderr dialihkan ke file di
Windows, Python memakai encoding locale (bukan UTF-8), dan karakter itu tersimpan rusak
(`�`). Pesan log kini memakai `-`. Catatan: teks yang dikirim lewat HTTP **tidak** kena
masalah ini karena body response tetap UTF-8.

## Hasil percobaan

**1. Frame mentah lewat `curl -N`** (delay token 60 ms) — format sesuai spesifikasi, urutan
`token`… lalu `done`:

```text
event: token
data: {"text": "Ini "}

event: token
data: {"text": "jawaban "}

...

event: done
data: {"finish_reason": "stop"}
```

**2. Kedatangan token bertahap** — client yang mencatat waktu tiap frame:

```text
[  0.18s] status=200 type=text/event-stream; charset=utf-8
[  0.26s] event: token
[  0.32s] event: token
[  0.39s] event: token
...
[  2.22s] event: done
```

32 frame dalam ~2 detik, jarak antar frame ~65 ms dengan `FAKE_TOKEN_DELAY_MS=60`. Artinya
token benar-benar dikirim bertahap oleh server, bukan menggumpal di akhir.

**3. Heartbeat** (`FAKE_TOKEN_DELAY_MS=1000`, `SSE_PING_INTERVAL_SECONDS=0.3`):

```text
[  0.43s] : ping
[  0.75s] : ping
[  1.06s] : ping
[  1.13s] event: token
[  1.43s] : ping
...
```

`: ping` muncul tiap ~0.3 detik selama sumber idle, dan token tetap lewat saat siap.

**4. Disconnect** — client berhenti membaca di tengah stream, lalu koneksi ditutup. Log server:

```text
INFO app.core.sse: Stream berhenti sebelum `done` - client disconnect atau dibatalkan
```

Ini **terverifikasi, bukan asumsi**: Starlette 1.6.0 membatalkan task generator kita saat
koneksi putus, blok `finally` jalan, `producer.cancel()` menghentikan sumber. Di task 5 ini
yang mencegah kita membayar token LLM yang sudah ditinggalkan user.

**Yang mengejutkan / berbeda dari dugaan awal:**

- Rencana awal memakai `wait_for` langsung ke `__anext__()`; ternyata itu mematikan sumber
  (lihat Keputusan #2). Ketahuan saat menyusun plan, sebelum ditulis ke kode.
- Log disconnect awalnya tidak muncul sama sekali (Keputusan #4).
- Em-dash di pesan log rusak di file (Keputusan #5).

## Failure mode

| Kegagalan | Gejala di client | Perilaku sistem | Deteksi |
| --- | --- | --- | --- |
| Client menutup koneksi | stream berhenti | `finally` jalan, producer dibatalkan | log `Stream berhenti sebelum 'done'` |
| Exception di sumber | stream berhenti setelah teks terakhir | frame `error` dikirim, detail internal tidak bocor ke client | frame terakhir bukan `done`; traceback penuh di log server |
| Request invalid | HTTP 422 | stream tidak pernah dimulai | status 422 + body JSON |
| Proxy/CDN menahan buffer | token muncul sekaligus di akhir | header `X-Accel-Buffering: no` + `Cache-Control: no-cache` | bandingkan `curl -N` langsung vs lewat proxy |
| Sumber lama diam | layar kosong | `: ping` menjaga koneksi | ada `: ping` di stream mentah |
| Server restart | koneksi putus | tidak ada resume (di luar cakupan task 1) | client harus retry |

## Catatan produksi

- **Biaya:** di task 5, tiap token = uang. Handling disconnect di atas bukan kerapian, tapi
  penghematan langsung. Uji: buka stream, tutup di tengah, pastikan permintaan ke LLM berhenti.
- **Latency:** yang dirasakan user adalah TTFB (time to first byte) — saat LLM butuh 3–10 detik
  sebelum token pertama, heartbeat-lah yang menjaga koneksi hidup.
- **Idle timeout proxy:** banyak proxy memutus koneksi yang diam. Nginx punya `proxy_read_timeout`
  (default 60 detik pada konfigurasi umum) — nilai ping kita harus jauh di bawah itu. Verifikasi
  di proxy yang benar-benar dipakai (task 8).
- **Jumlah koneksi:** satu stream = satu koneksi TCP yang hidup lama. Browser membatasi
  koneksi per origin (umumnya 6 untuk HTTP/1.1), dan server juga menahan memori per koneksi.
  Ini pertimbangan nyata saat frontend (task 7) membuka banyak tab.
- **Worker:** satu proses uvicorn memakai satu event loop. Async membuat banyak koneksi
  tidak saling memblokir, tapi CPU-heavy (mis. embedding lokal di task 3) bisa menghentikan
  semua koneksi — itu masalah yang berbeda dan akan dibahas saat muncul.

## Cara menjalankan & menguji

```powershell
uv sync                                        # pasang dependency
uv run uvicorn app.main:app --reload           # jalankan server
uv run pytest -v                               # 12 test
uv run ruff check .                            # lint
uv run ruff format --check .                   # cek format
```

Uji manual:

- `http://127.0.0.1:8000/demo` — lihat frame mentah + tombol Stop untuk menguji disconnect.
- `curl.exe -N -X POST http://127.0.0.1:8000/api/chat/stream -H "Content-Type: application/json" -d "@payload.json"`
  (body lewat file; PowerShell merusak tanda kutip di dalam JSON)
- Ubah `.env` → `FAKE_TOKEN_DELAY_MS`, `SSE_PING_INTERVAL_SECONDS` untuk menguji heartbeat.

## Poin Kunci

- SSE = teks dengan format `event:`/`data:` + baris kosong; kekuatannya ada di field `event`
  yang membuat kontrak bisa berkembang tanpa merusak client lama.
- Async generator adalah bentuk paling alami untuk sumber data bertahap, dan
  `StreamingResponse` menerimanya langsung.
- Heartbeat harus **tidak mengganggu sumber**; itulah alasan producer/consumer + queue dipakai.
- Setelah header terkirim, error tidak bisa lagi jadi status HTTP — ia harus jadi frame
  `error`. Ini batas yang sering bikin bingung.
- Disconnect = sinyal bisnis (berhenti membayar), bukan sekadar kerapian teknis.

## Eksperimen lanjutan

1. **Bandingkan dengan `sse-starlette`.** Ganti `sse_stream()` dengan `EventSourceResponse`,
   lalu ukur: berapa baris kode yang hilang, dan perilaku apa yang berubah saat disconnect?
2. **Naikkan skala koneksi.** Jalankan `uv run uvicorn app.main:app --workers 4`, buka 20
   koneksi bersamaan (mis. `hey`/script async), perhatikan memori dan apakah heartbeat tetap rapi.
3. **Uji lewat proxy.** Jalankan nginx/Caddy di depan uvicorn, buktikan token menggumpal
   tanpa `X-Accel-Buffering: no` dan lancar setelah header itu ada.

## Glosarium

| Istilah | Kepanjangan / asal | Arti di konteks ini |
| --- | --- | --- |
| SSE | *Server-Sent Events* | protokol kirim data satu arah lewat HTTP, berbasis teks |
| ASGI | *Asynchronous Server Gateway Interface* | kontrak server ↔ framework Python yang mendukung async |
| WSGI | *Web Server Gateway Interface* | pendahulu ASGI, sinkron, satu request satu thread |
| CORS | *Cross-Origin Resource Sharing* | aturan browser soal akses antar-origin |
| TTFB | *Time To First Byte* | jeda sampai byte pertama jawaban diterima |
| Heartbeat / ping | — | frame komentar `: ping` untuk menjaga koneksi tetap hidup |
| Producer/consumer | — | pola dua task: satu mengisi queue, satu mengonsumsi |
| Buffering | — | penahanan data oleh proxy/server sebelum diteruskan |
| `uv` | — | package manager + pengelola interpreter Python (Rust) |
| Dependency injection | — | pola FastAPI menyediakan objek ke route lewat `Depends` |

## Referensi

- MDN — *Using server-sent events*: <https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events>
- Starlette — *Responses* (`StreamingResponse`): <https://www.starlette.io/responses/>
- FastAPI — *Dependencies with Annotated*: <https://fastapi.tiangolo.com/tutorial/dependencies/>
