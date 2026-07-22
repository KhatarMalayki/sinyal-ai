# Benchmark Indonesia Sinyal.AI

Pilot ini membandingkan 25 teks manusia publik dengan 25 teks AI sintetis bertopik sepadan.

## Sumber dan lisensi

- Teks manusia berasal dari bagian pembuka artikel acak Wikipedia bahasa Indonesia.
- URL dan ID revisi disimpan pada `dataset.csv` untuk provenance.
- Konten Wikipedia tersedia berdasarkan CC BY-SA 4.0; lihat https://id.wikipedia.org/wiki/Wikipedia:Hak_cipta.
- Teks AI dibuat oleh generator deterministik lokal `benchmark.py` dan tidak dianggap sebagai representasi semua model AI.

## Menjalankan ulang

```powershell
python benchmark.py
```

Perintah tersebut memakai ulang `dataset.csv` yang sudah dibekukan, sehingga hasil dapat direproduksi tanpa mengambil artikel acak baru. Untuk sengaja membuat korpus Wikipedia baru (dan menimpa dataset lama), gunakan:

```powershell
python benchmark.py --refresh
```

MediaWiki memilih halaman acak di sisi server; karena itu `--refresh` tidak dijamin menghasilkan artikel yang sama meskipun seed lokal tetap sama.

Output:

- `dataset.csv`: teks, label, topik, sumber, revisi, dan lisensi.
- `results.csv`: skor dan split calibration/test setiap sampel.
- `report.json`: confusion matrix serta accuracy, precision, recall, specificity, false-positive rate, balanced accuracy, F1, dan MCC.

## Hasil pilot saat ini

Dataset berisi 25 pasangan topik (25 manusia, 25 AI). Pasangan topik tidak dipisah lintas kelompok: 15 topik/30 sampel digunakan untuk memilih threshold dan 10 topik/20 sampel disimpan sebagai held-out test.

| Evaluasi | Threshold | TP | TN | FP | FN | Accuracy | Precision | Recall | Specificity | FPR | F1 | MCC |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Seluruh data, threshold UI | 70 | 25 | 6 | 19 | 0 | 62% | 56,8% | 100% | 24% | 76% | 72,5% | 0,369 |
| Calibration | 91 | 15 | 12 | 3 | 0 | 90% | 83,3% | 100% | 80% | 20% | 90,9% | 0,816 |
| Held-out test | 91 | 10 | 1 | 9 | 0 | 55% | 52,6% | 100% | 10% | 90% | 69,0% | 0,229 |

Skor manusia berkisar 24–96 dengan rata-rata **79,36**, sedangkan seluruh sampel AI mendapat **96**. Pada threshold UI 70, 19 dari 25 teks manusia ditandai sebagai AI. Threshold 91 yang dipilih hanya dari calibration juga gagal menggeneralisasi: 9 dari 10 teks manusia pada held-out test menjadi false positive.

## Interpretasi dan keputusan

- Detector v2 sangat bias terhadap prosa Indonesia formal/ekspositoris. Sinyal kosakata ekspositoris tidak boleh diperlakukan sebagai bukti kuat kepengarangan AI.
- Recall 100% tidak meyakinkan karena generator AI berbasis tiga paragraf tetap menghasilkan skor identik 96; benchmark ini terlalu mudah pada kelas AI.
- Perbedaan besar calibration vs held-out menunjukkan threshold tuning pada korpus kecil tidak stabil.
- **Belum ada perubahan threshold atau formula produksi berdasarkan pilot ini.** Langkah berikutnya adalah menambah genre manusia (narasi, ulasan, berita, blog) dan keluaran AI dari beberapa model/prompt/gaya dengan provenance tersimpan, lalu mengevaluasi sekali pada test set yang benar-benar tidak disentuh.

## Batasan

Ini adalah pilot kecil. Artikel Wikipedia memiliki gaya ensiklopedis dan label "human" berarti sumbernya merupakan korpus tulisan manusia publik, bukan jaminan bahwa setiap revisi bebas bantuan otomatis. Sampel AI berasal dari satu generator berbasis templat dan bukan keluaran model bahasa nyata yang beragam. Split hanya 15/10 topik dan threshold masih dipilih pada korpus yang sangat sempit. Hasil tidak boleh digunakan untuk klaim akurasi produksi tanpa dataset lebih besar, beragam, berlisensi jelas, dan diaudit manual.