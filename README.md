# Sinyal.AI

Detector pola tulisan dan editor revisi kontekstual bahasa Indonesia. Analisis detector berjalan di browser, sedangkan editor LLM menggunakan backend lokal yang kompatibel dengan OpenAI API.

## Fitur

- Analisis enam sinyal linguistik secara lokal.
- Input tanpa batas kata buatan aplikasi.
- Unggah TXT, Markdown, DOCX, dan PDF berbasis teks.
- Sorotan kalimat kontekstual dengan sampling aman untuk dokumen panjang.
- Editor LLM dengan gaya, intensitas, konteks pengguna, dan chunking dokumen.
- API key hanya dibaca oleh backend dari environment variable.
- Fallback editor lokal jika endpoint LLM tidak tersedia.

## Menjalankan aplikasi

Gunakan PowerShell:

```powershell
$env:SINYAL_AI_API_KEY="local"
$env:SINYAL_AI_BASE_URL="http://localhost:20128/v1"
$env:SINYAL_AI_HUMANIZER_MODEL="my-combo"
python server.py
```

Buka alamat yang tercetak di terminal, secara default `http://127.0.0.1:8765`.

## Konfigurasi

| Variable | Default | Keterangan |
|---|---|---|
| `SINYAL_AI_API_KEY` | kosong | Credential endpoint OpenAI-compatible |
| `SINYAL_AI_BASE_URL` | `http://localhost:20128/v1` | Base URL API |
| `SINYAL_AI_HUMANIZER_MODEL` | `my-combo` | Model editor |
| `SINYAL_AI_HOST` | `127.0.0.1` | Host server web |
| `SINYAL_AI_PORT` | `8765` | Port server web |
| `SINYAL_AI_TIMEOUT` | `120` | Timeout request LLM dalam detik |

> Jangan commit API key. Gunakan environment variable pada terminal yang menjalankan server.

## Catatan

- PDF hasil scan memerlukan OCR dan belum dapat diekstrak langsung.
- Skor detector adalah indikator probabilistik, bukan bukti tunggal mengenai asal sebuah tulisan.
- Editor dirancang untuk meningkatkan kualitas tulisan dan menjaga makna, bukan menjamin hasil tertentu pada detector eksternal.