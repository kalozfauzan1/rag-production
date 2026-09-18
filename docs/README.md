# Dokumentasi — rag-production

Index semua dokumen. Diperbarui setiap kali ada dokumen baru atau berubah.

## Specs — desain sebelum implementasi

| Dokumen | Isi | Status |
| --- | --- | --- |
| [specs/2026-09-18-task1-fastapi-sse-setup-design.md](specs/2026-09-18-task1-fastapi-sse-setup-design.md) | Desain task 1: struktur FastAPI, kontrak SSE, pola async, failure mode | selesai |
| [specs/2026-09-18-task2-ingestion-chunking-design.md](specs/2026-09-18-task2-ingestion-chunking-design.md) | Desain task 2: upload HTTP, ekstraksi blocks, recursive chunking, job in-process | selesai |

## Plans — rencana eksekusi

| Dokumen | Isi | Status |
| --- | --- | --- |
| [plans/2026-09-18-task1-fastapi-sse-setup.md](plans/2026-09-18-task1-fastapi-sse-setup.md) | 6 task langkah-demi-langkah: toolchain, app factory, inti SSE, endpoint chat, halaman demo, dokumentasi | selesai dieksekusi |
| [plans/2026-09-18-task2-ingestion-chunking.md](plans/2026-09-18-task2-ingestion-chunking.md) | 9 task: config, schema, normalisasi, tokenizer+chunker, extractor, store, job+pipeline, API, verifikasi | selesai dieksekusi |

## Learning — konsep & penjelasan

| Dokumen | Isi | Status |
| --- | --- | --- |
| [learning/fastapi-async-sse.md](learning/fastapi-async-sse.md) | Async generator, wire format SSE, heartbeat, disconnect, failure mode, hasil percobaan, glosarium | selesai |
| [learning/ingestion-chunking.md](learning/ingestion-chunking.md) | Ekstraksi PDF/HTML, chunking berbasis token, temuan BPE tidak aditif, eksperimen event loop, glosarium | selesai |

## Lainnya

| Dokumen | Isi |
| --- | --- |
| [decisions.md](decisions.md) | Log keputusan (ADR ringkas) — uv, Python 3.13, SSE manual, struktur repo, test, lint |
| [../README.md](../README.md) | README utama repo (arsitektur, cara run, demo) |
| [../AGENTS.md](../AGENTS.md) | Aturan kerja agent: gaya penjelasan, dokumentasi wajib |
