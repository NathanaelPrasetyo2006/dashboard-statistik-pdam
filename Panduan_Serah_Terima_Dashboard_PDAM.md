# Panduan serah-terima dashboard Streamlit VARX–MEWMA Model A

## Langkah dosen di Google Colab
1. Buka notebook yang menghasilkan **hasil_final** dan **ringkasan_episode** Model A, lalu jalankan semua sel yang diperlukan hingga selesai.
2. Tambahkan sel paling akhir, salin seluruh isi `export_dashboard_model_A.py`, lalu jalankan.
3. Colab akan mengunduh `dashboard_model_A.zip`. Berikan ZIP ini kepada mahasiswa Informatika bersama panduan ini.
4. Bila muncul pesan kesalahan, jangan mengubah angka UCL atau jumlah sinyal untuk memaksa lolos; periksa kembali objek hasil final.

## Peta hasil untuk mahasiswa
| File | Kolom utama | Tampilan dashboard | Interpretasi pengguna |
|---|---|---|---|
| `metadata_model.json` | UCL, lambda, ARL, periode, catatan | KPI & informasi model | Model historis; sinyal belum membuktikan kebocoran |
| `tekanan_aktual.csv` | Datetime, 5 titik | Grafik tekanan per titik | Bandingkan tekanan antarwaktu, jangan otomatis menyebut gangguan |
| `mewma_monitoring.csv` | Datetime, T2_MEWMA, UCL, Sinyal, Episode | Peta kendali, filter tanggal, titik merah | T² > UCL = kandidat penyimpangan multivariat |
| `episode_monitoring.csv` | Episode, Mulai, Selesai, Jumlah_Jam_Sinyal, Maksimum_T2, Titik Dominan, Status_Verifikasi | Tabel investigasi dan detail episode | Perlu pengecekan catatan operasional PDAM |
| `kontribusi_diagnostik.csv` (jika tersedia) | Datetime, 5 kontribusi titik | Heatmap diagnostik | Kontribusi bukan bukti sebab atau lokasi kebocoran |

## Fitur yang harus dikembangkan
**Overview:** 5 titik, 57 kandidat OOC, 10 episode, UCL 22,5640, ARL validasi 194,07. Tampilkan periode 21–31 Juli 2026 dan label **DATA HISTORIS**.

**Peta kendali:** grafik garis T², garis horizontal UCL, titik merah pada Sinyal=True. Tooltip: tanggal, T², status, nomor episode. Saat diklik, tampilkan penjelasan: 'Statistik MEWMA melewati batas kendali; pemeriksaan lanjutan diperlukan.'

**Tekanan:** pilih titik, filter tanggal, tampilkan tekanan aktual dan marker waktu sinyal MEWMA. Profil rata-rata per jam Phase I dapat ditambahkan jika data profil tersebut diekspor tersendiri.

**Investigasi:** tabel 10 episode, detail rentang waktu dan maksimum T², catatan verifikasi operator. Titik dominan ditampilkan bila terisi. Tidak mengklaim kebocoran otomatis.

**Validasi model:** tampilkan UCL, target dan ARL validasi, CI 95%, lambda, metode blok 48 jam, serta keterbatasan residual Paldam dan pengamatan ekstrem 9 Juli.

## Pengujian penerimaan (acceptance test)
- Data final memiliki 57 baris `Sinyal=True` dan 10 nomor episode berbeda.
- Garis UCL = 22,5640 pada semua grafik, bukan 22,5399 (hasil blok 24 jam).
- Periode Phase II adalah 21–31 Juli 2026; data per jam dan tidak boleh diklaim realtime.
- Jumlah jam episode adalah banyaknya pengamatan bersinyal, bukan durasi kerusakan terkonfirmasi.
- Jika file kontribusi belum tersedia, halaman kontribusi menampilkan pesan 'Data kontribusi belum diekspor' dan tidak menampilkan angka rekaan.
- Status verifikasi disimpan terpisah dari hasil statistik agar perubahan catatan operator tidak mengubah hasil analisis.

## Pembagian tugas
**Peneliti statistik:** memastikan model, hasil, interpretasi dan kebenaran dataset ekspor. **Mahasiswa Informatika:** membangun antarmuka Streamlit, grafik Plotly, filter, detail episode, serta pengelolaan catatan verifikasi.
