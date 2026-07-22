# Benchmark Indonesia Multi-Genre

Perluasan pilot ini berisi **48 sampel**: 24 teks manusia dan 24 teks AI model nyata berpasangan topik.

## Komposisi

- 8 teks ensiklopedis dari Wikipedia bahasa Indonesia.
- 8 teks instruksional dari Wikibooks bahasa Indonesia.
- 8 teks dokumen/sastra dari Wikisource bahasa Indonesia.
- 24 teks AI model nyata dengan gaya genre sepadan.

URL, ID revisi, korpus, genre, dan lisensi disimpan di `dataset.csv`. Konten manusia menggunakan lisensi CC BY-SA 4.0. Split dilakukan berdasarkan topik sehingga pasangan manusia/AI tidak bocor lintas calibration dan test.

## Provenance AI model nyata

Dataset aktif `dataset-real-ai-multimodel.csv` dibuat melalui API lokal OpenAI-compatible `http://localhost:20128/v1`. Delapan route diminta, masing-masing untuk tepat satu sampel per genre (3 sampel per route):

- `kimchi/minimax-m3`
- `ollama/minimax-m3`
- `kimchi/kimi-k2.7`
- `gemini/gemini-3.5-flash`
- `gemini/gemini-3.1-flash-lite-preview`
- `gemini/gemini-3-flash-preview`
- `ag/gemini-3.5-flash-low`
- `ag/gemini-3.1-pro-low`

Dua ID Gemini 2.5 dari gambar awal tidak diiklankan oleh endpoint `/models`; dengan persetujuan pengguna keduanya diganti dua route `ag/*` terakhir di atas. Semua 24 teks unik, panjangnya minimal 80 kata, memiliki completion/request ID, prompt ID, waktu generasi, dan `fallback=false`.

Kolom `requested_model` menyimpan route yang diminta dan `model` menyimpan nama aktual dari respons. Delapan route menghasilkan tujuh nama aktual: `minimax-m3` (6 sampel), serta masing-masing 3 sampel dari `kimi-k2.7`, `gemini-3.5-flash`, `gemini-3.1-flash-lite`, `gemini-3-flash-preview`, `gemini-default`, dan `gemini-3.1-pro-low`.

## Hasil

Baseline formula produksi lama pada threshold UI 70:

- Accuracy: **29,2%**
- Precision: **18,8%**
- Recall: **12,5%**
- Specificity: **45,8%**
- False-positive rate: **54,2%**
- F1: **15,0%**
- MCC: **-0,442**

Threshold baseline yang dipilih evaluator lama juga tidak berguna. Arah skor pada dataset multi-model cenderung terbalik: banyak teks AI nyata memperoleh skor lebih rendah daripada prosa manusia formal.

## Eksperimen formula calibration-only

`calibrate_formula.py` mendeklarasikan tiga kandidat sebelum evaluasi, menghapus jalur maksimum ekspositoris, menghapus nomina topikal dari kosakata gaya, mengecilkan bobot gaya, dan menguji ada/tidaknya repetition floor. Split baru dibuat dengan SHA-256 dan salt tetap agar berbeda dari test lama.

Perintah `--select` hanya membaca **34 sampel calibration** dan membekukan `no_repetition_floor` pada threshold 13. Hasil calibration masih lemah: MCC 0,174, specificity 5,9%, dan FPR 94,1%. Sesudah kandidat dan threshold tersimpan di `formula-frozen.json`, holdout 14 sampel dibuka tepat satu kali dengan `--evaluate-frozen`:

- Accuracy: **35,7%**
- Recall: **71,4%**
- Specificity: **0%**
- False-positive rate: **100%**
- MCC: **-0,408**

Kandidat dinyatakan **gagal**. Sesuai metodologi, holdout tidak dipakai untuk tuning ulang. Formula gagal tidak disalin ke `app.js` atau `benchmark.py`; produksi tetap pada formula sebelumnya sambil hasil UI disebut indikasi pola, bukan kepastian.

## Korpus v2: 96 pasangan baru

Iterasi v2 disimpan terpisah di `dataset-real-ai-multimodel-v2.csv` dan berisi **192 baris**: 96 teks manusia serta 96 teks AI dengan topik berpasangan. Seluruh 96 topik baru tidak beririsan dengan v1. Komposisinya seimbang: 32 topik per genre, 12 keluaran per requested route, dan 4 keluaran untuk setiap kombinasi genre/route.

`v2-split-manifest.json` dibuat sebelum generasi AI dan ditandai `created_before_ai_generation=true`. Hash topik bersalt menetapkan 71 pasangan (142 baris) sebagai calibration dan 25 pasangan (50 baris) sebagai holdout. Validasi final memastikan setiap topik muncul tepat dua kali, seluruh 96 teks AI unik dan minimal 80 kata, tidak ada fallback, serta provenance requested/actual model lengkap. Route `minimax-m3` menghasilkan 24 sampel aktual karena dua requested route memetakannya ke nama model aktual yang sama; enam nama aktual lainnya masing-masing menghasilkan 12 sampel.

Generator v2 bersifat resume-safe. Ketika route Kimi terkena HTTP 429 pada sampel 83, checkpoint 82 baris dipertahankan. `generate_real_ai.py` kemudian ditambah retry 429 yang menghormati `Retry-After` atau keterangan `reset after`, dan proses berhasil dilanjutkan tanpa mengulang sampel terdahulu.

## Calibration formula lama; holdout tetap tertutup

`calibrate_formula_v2.py` hanya membaca 142 baris calibration melalui manifest beku. Sebelum seleksi, gate dideklarasikan sebagai MCC ≥ 0,20, balanced accuracy ≥ 0,60, dan specificity ≥ 0,65; threshold yang tidak memenuhi gate specificity tidak diprioritaskan. Urutan objektif tetap MCC, balanced accuracy, specificity, lalu F1.

Kandidat terbaik dari keluarga yang telah dideklarasikan adalah `balanced_no_expository_max` pada threshold 95, tetapi hasilnya degeneratif:

- Accuracy: **50,0%**
- Recall: **0%**
- Specificity: **100%**
- Balanced accuracy: **50,0%**
- MCC: **0**

Kandidat gagal gate calibration dan dibekukan dengan `calibration_pass=false` di `formula-v2-frozen.json`. Karena itu holdout v2 **tidak dibuka sama sekali**; `formula-v2-holdout.json` tidak dibuat. Tidak ada perubahan pada `app.js` atau `benchmark.py`. Langkah berikutnya bukan menyesuaikan kandidat terhadap holdout, melainkan merancang keluarga fitur baru menggunakan hanya calibration v2 atau mengumpulkan korpus baru untuk eksperimen berikutnya.

## Keluarga fitur stilometrik baru (calibration-only)

`calibrate_features_v2.py` menjalankan iterasi berikutnya tanpa membaca atau menskor topik outer holdout. Tiga kandidat kecil dideklarasikan di source dan hanya memakai sinyal non-topikal: keseragaman panjang kalimat/paragraf, kelengkapan tanda akhir kalimat, keseragaman koma, stabilitas function-word antarbagi teks, stabilitas keragaman leksikal antarbagi, serta penalti ringan untuk digit dan tanda kutip. Kandidat tidak menggunakan topik, nama sumber, genre, requested/actual model, atau provenance sebagai prediktor.

Untuk menghindari estimasi resubstitution, 71 pasangan calibration dibagi deterministik menjadi **5 fold berdasarkan topik** (15/14/14/14/14 pasangan). Pada setiap iterasi, threshold dipilih hanya dari empat fold training dan diterapkan ke fold validasi yang belum dipakai. Agregasi 142 prediksi out-of-fold memilih dan membekukan `rhythm_and_closure`:

- Accuracy: **78,2%**
- Precision: **75,0%**
- Recall: **84,5%**
- Specificity: **71,8%**
- False-positive rate: **28,2%**
- Balanced accuracy: **78,2%**
- F1: **79,5%**
- MCC: **0,568**

Hasil ini melewati gate calibration (MCC ≥ 0,20, balanced accuracy ≥ 0,60, specificity ≥ 0,65). Konfigurasi dan threshold full-calibration `0.5435406480407824` dibekukan di `feature-v2-frozen.json`; rincian fold berada di `feature-v2-calibration-cv.json`. Nilai `outer_holdout_scored=false` dipertahankan sebagai snapshot historis kondisi saat pembekuan, bukan status mutable.

## One-shot holdout dan promosi produksi

Sebelum holdout dibaca, gate promosi dikunci di `evaluate_features_v2_holdout.py`: MCC ≥ 0,30, balanced accuracy ≥ 0,70, specificity ≥ 0,65, recall ≥ 0,70, dan balanced accuracy minimum per genre ≥ 0,60. Evaluator menolak second look bila `feature-v2-holdout.json` sudah ada. Evaluasi tepat satu kali atas 25 pasangan/50 baris menghasilkan:

- TP/TN/FP/FN: **22/18/7/3**
- Accuracy: **80,0%**
- Precision: **75,9%**
- Recall: **88,0%**
- Specificity: **72,0%**
- Balanced accuracy: **80,0%**
- F1: **81,5%**
- MCC: **0,608**
- Balanced accuracy minimum per genre: **72,7%**

Semua gate lulus (`promotion_pass=true`). Artefak menetapkan `one_shot=true` dan `retuning_permitted=false`; holdout ini tidak boleh dievaluasi ulang atau dipakai tuning. Formula frozen dipromosikan identik ke `app.js` dan `benchmark.py`, dengan threshold keputusan UI 50. Parity memeriksa seluruh 192 baris: skor JS/Python identik, keputusan integer identik dengan `raw_score >= frozen threshold`, dan confusion matrix holdout tetap 22/18/7/3.

## Menjalankan

```powershell
# Evaluasi ulang dataset beku, tanpa jaringan
python benchmark_expanded.py

# Buat ulang teks AI melalui API lokal (key hanya dari environment variable)
python generate_real_ai.py

# Pilih pada calibration dan bekukan kandidat (hanya sekali)
python calibrate_formula.py --select

# Buka holdout kandidat beku (hanya sekali)
python calibrate_formula.py --evaluate-frozen

# Pipeline v2: bangun human + manifest, lalu generate di terminal ber-API key
python build_v2_dataset.py
python generate_v2_ai.py

# Seleksi v2. Evaluasi holdout hanya boleh dijalankan bila calibration_pass=true.
python calibrate_formula_v2.py --select
python calibrate_formula_v2.py --evaluate-frozen

# Cari keluarga fitur baru hanya dengan paired calibration CV; tidak membuka holdout.
python calibrate_features_v2.py

# Catatan historis: sudah dijalankan satu kali; sekarang menolak rerun karena artefak ada.
python evaluate_features_v2_holdout.py
```

## Keputusan dan tahap eksternal berikutnya

Jangan sekadar menaikkan atau menurunkan threshold produksi. Hasil held-out membuktikan perubahan threshold tidak memperbaiki generalisasi. Perbaikan formula harus dikerjakan hanya pada calibration set dengan prioritas:

1. hapus jalur skor maksimum yang menjadikan `expositorySignal` bukti AI independen;
2. kurangi bobot daftar kosakata topik/gaya formal;
3. gunakan sinyal gaya hanya sebagai bukti pendukung, bukan penentu;
4. tambah jumlah topik secara substansial; tiga sampel per route belum cukup untuk estimasi per-model;
5. jangan retune terhadap holdout yang kini sudah dibuka—buat korpus/topik baru untuk iterasi berikutnya.

Formula stilometrik baru dipromosikan karena melewati paired calibration CV dan seluruh gate holdout yang dideklarasikan sebelumnya. Aplikasi tetap harus menyebut hasil sebagai **indikasi pola**, bukan kepastian kepengarangan AI.

Perbandingan dengan detector internet memerlukan dataset eksternal baru yang tidak dipakai dalam pengembangan ini. Bekukan pasangan, label, urutan, metrik, dan aturan konversi keluaran setiap tool sebelum submission. Jalankan semua tool pada teks yang sama; catat versi/tanggal, kegagalan, batas panjang, serta kebijakan privasi. Jangan mengunggah materi sensitif atau berlisensi terbatas. Metrik utama: MCC, balanced accuracy, specificity, recall, dan minimum balanced accuracy per genre; laporkan juga coverage bila tool menolak sampel.

## Benchmark eksternal eksploratori 24 teks

`external-comparison-dataset.csv` membekukan 12 pasangan baru (24 teks; 4 pasangan per genre) tanpa overlap topik v1/v2. Dataset ini tidak dipakai untuk tuning. Pada threshold keputusan 50, hasilnya:

| Detector | Coverage | TP | TN | FP | FN | Accuracy | Recall | Specificity | Balanced accuracy | MCC |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Sinyal.AI | 100% | 9 | 11 | 1 | 3 | 83,3% | 75,0% | 91,7% | 83,3% | 0,676 |
| ZeroGPT | 100% | 4 | 4 | 8 | 8 | 33,3% | 33,3% | 33,3% | 33,3% | -0,333 |
| GPTZero | 4,2% | — | — | — | — | — | — | — | — | — |

ZeroGPT dijalankan satu dokumen per request melalui sesi browser anonim pada endpoint yang digunakan UI publik. Artefak skornya berada di `external-comparison-zerogpt-browser.json`. ZeroGPT salah menandai delapan teks manusia sebagai AI dan melewatkan delapan teks AI. GPTZero hanya mengizinkan satu scan anonim, lalu meminta login; satu hasil tidak cukup untuk menghitung metrik dan dilaporkan sebagai keterbatasan coverage, bukan sebagai pembanding akurasi.

Pada benchmark kecil dan spesifik bahasa Indonesia ini, Sinyal.AI mengungguli ZeroGPT secara jelas. Kesimpulan tersebut tidak berarti keunggulan universal: ukuran hanya 24 teks, sumber manusia berasal dari tiga korpus Wikimedia, dan keluaran AI berasal dari empat route. Formula dan threshold produksi tidak diubah setelah melihat hasil eksternal.

## Sorotan kalimat kontekstual

UI menyediakan bagian **Bagian untuk ditinjau** sebagai lapisan interpretasi yang terpisah dari formula dokumen frozen. Setiap kalimat dinilai bersama satu kalimat sebelum dan sesudahnya; skor dokumen, threshold 50, dan verdict produksi tidak berubah. Warna kuning berarti sinyal konteks sedang dan jingga berarti tinggi. Saat diarahkan atau difokuskan, sorotan menampilkan skor konteks serta alasan struktural ringkas.

Sorotan ini bukan classifier sentence-level tervalidasi dan tidak menyatakan bahwa suatu kalimat pasti ditulis AI. Fungsinya hanya membantu pengguna menentukan bagian yang layak ditinjau. Fitur tidak menulis ulang teks dan bukan humanizer otomatis.

## Editor revisi lokal

Bagian **Editor revisi** menyediakan tiga gaya (`Natural`, `Ringkas`, `Formal ringan`) dan tiga tingkat intensitas. Transformasinya deterministik dan berjalan sepenuhnya di browser: mengganti beberapa transisi kaku, memecah kalimat yang sangat panjang pada batas koma yang layak, serta mengurangi pembuka berulang pada intensitas aktif. Hasil selalu ditampilkan sebagai pratinjau `readonly`; pengguna harus memilih sendiri untuk menyalin atau menerapkannya kembali ke detector.

Editor ini ditujukan untuk keterbacaan dan kontrol editorial, bukan untuk menjamin teks melewati AI detector. Ia tidak memeriksa kebenaran fakta atau kesetaraan semantik secara otomatis, sehingga pengguna wajib meninjau hasil. Penambahan editor tidak mengubah formula detector frozen; regresi 24 skor eksternal tetap memiliki checksum 1131.