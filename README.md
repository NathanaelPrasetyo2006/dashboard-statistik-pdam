# Dashboard Monitoring Tekanan Jaringan PDAM (VARX–MEWMA Model A)

Aplikasi Streamlit untuk menampilkan hasil Model A (statistik T² MEWMA, episode kandidat penyimpangan,
tekanan lima titik) dan mencatat verifikasi lapangan. Data periode baru dapat diimpor sehingga
pemantauan berlanjut di atas data sebelumnya.

> Dashboard ini **tidak mengestimasi ulang** VARX/MEWMA. Semua angka model berasal dari paket
> ekspor Google Colab (`export_dashboard_model_A.py`). Sinyal = kandidat penyimpangan statistik,
> bukan bukti kebocoran.

## Menjalankan di komputer sendiri

Windows: klik ganda `jalankan.bat` (pertama kali akan memasang library).

Manual:

```bash
py -3.10 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\streamlit run app.py
```

Browser terbuka di `http://localhost:8501`. Perlu Python 3.10 ke atas.

## Alur pemakaian

1. Dosen menjalankan `export_dashboard_model_A.py` di Colab → menghasilkan `dashboard_model_A.zip`.
2. Buka **Kelola Data & Import** → tab *Import hasil model* → unggah ZIP → periksa pratinjau → **Simpan**.
3. Semua halaman (Overview, Monitoring Tekanan, Peta Kendali, Investigasi Episode, Analisis Jaringan,
   Validasi Model) langsung terisi.
4. Periode berikutnya: jalankan Model A yang sudah dibekukan pada data baru di Colab, ekspor, lalu impor
   ZIP-nya dengan mode **Tambahkan ke data sebelumnya**. Data digabung berdasarkan waktu; episode
   dinomori ulang secara kronologis; catatan verifikasi tetap menempel pada episode yang sama
   (dikunci pada waktu mulai episode).

### Dua jenis import

| Tab | Isi | Hasil |
|---|---|---|
| Import hasil model | ZIP/CSV hasil ekspor Colab (`mewma_monitoring.csv` wajib) | Peta kendali, episode, KPI, kontribusi ikut diperbarui |
| Import tekanan mentah | CSV/Excel: `Datetime` (atau `Tanggal`+`Jam`) + 5 kolom titik | Tampil di Monitoring Tekanan & Analisis Jaringan (dibandingkan dengan profil Phase I), **tanpa** T² sampai hasil modelnya diimpor |

Pengaman saat import: paket dengan UCL atau λ berbeda dari data tersimpan ditolak (hasil model berbeda
tidak dicampur); waktu ganda diganti dengan nilai terbaru; selang bukan 1 jam, nilai kosong, dan
ketidaksesuaian `Sinyal` vs `T² > UCL` dilaporkan.

### Untuk periode baru di Colab

Skrip `export_dashboard_model_A.py` sengaja gagal bila jumlah sinyal ≠ 57 atau episode ≠ 10. Itu benar
untuk Juli 2026, tetapi untuk periode baru pemeriksaan tersebut perlu dilewati. **UCL 22,5640 dan λ = 0,1
tidak boleh diubah.**

Ke depan, agar data mentah bisa langsung diproses di dashboard tanpa Colab, peneliti perlu mengekspor
parameter model yang dibekukan (koefisien VARX + Fourier, matriks kovarians residual, keadaan akhir
MEWMA). Setelah itu fungsi skoring dapat ditambahkan ke `pdam/`.

## Apakah bisa diakses publik tanpa deploy?

**Tidak.** `streamlit run` hanya menyajikan aplikasi dari komputer yang menjalankannya:

- `Local URL` (localhost) → hanya komputer itu.
- `Network URL` → perangkat lain di jaringan Wi-Fi/LAN yang sama, selama laptop menyala.
- `External URL` yang dicetak Streamlit biasanya tidak bisa dibuka dari luar karena NAT/firewall.

Agar bisa dibuka siapa pun lewat tautan, cara termudah adalah **Streamlit Community Cloud** (gratis):

1. Unggah folder ini ke repositori GitHub (boleh privat).
2. Buka <https://share.streamlit.io> → masuk dengan GitHub → **Create app** → pilih repo, branch, file `app.py`.
3. (Disarankan) di *Advanced settings → Secrets* isi `ADMIN_PASSWORD = "..."` agar hanya pengelola yang bisa
   import data dan mengisi verifikasi. Pengunjung lain tetap bisa melihat dashboard.
4. Dapat alamat `https://<nama-app>.streamlit.app`. Setiap `git push` otomatis memperbarui aplikasi.

**Penting soal penyimpanan di Cloud:** disk Streamlit Cloud tidak permanen. Data hasil import dan catatan
verifikasi bisa hilang saat aplikasi tidur/dimulai ulang. Pilihan:

- Import di komputer lokal, lalu commit folder `data/` ke GitHub. Aplikasi Cloud selalu mulai dengan data itu.
- Rutin **Unduh backup** (tab *Backup & reset*) dan **Pulihkan** bila data hilang.
- Untuk pemakaian operasional jangka panjang: pindahkan penyimpanan `pdam/storage.py` ke basis data
  (mis. PostgreSQL/Supabase atau Google Sheets).

Alternatif sementara tanpa GitHub: terowongan seperti `cloudflared tunnel --url http://localhost:8501`
memberi tautan publik selama laptop menyala.

## Struktur

```
app.py                 navigasi + filter tanggal global (sidebar)
views/                 satu file per halaman (01–06 sesuai brief + Kelola Data)
pdam/config.py         titik, UCL acuan, warna, status verifikasi
pdam/storage.py        import, validasi, penggabungan periode, verifikasi, backup
pdam/analysis.py       filter, profil Phase I, interpretasi berbasis aturan, uji penerimaan
pdam/charts.py         grafik Plotly
pdam/ui.py             komponen tampilan bersama, login pengelola
data/                  penyimpanan (dibuat otomatis saat import pertama)
contoh_data/           paket SINTETIS untuk mencoba aplikasi (bukan hasil Model A)
tools/buat_data_demo.py  pembuat paket sintetis
```

## Kamus data penyimpanan (`data/`)

| File | Kolom | Sifat |
|---|---|---|
| `monitoring.csv` | Datetime, T2_MEWMA, UCL, Sinyal, Batch | Hasil model, read-only (hanya berubah lewat import) |
| `tekanan.csv` | Datetime, 5 titik, Batch | Read-only |
| `episode_info.csv` | Mulai, Titik_Dominan | Dari `episode_monitoring.csv` hasil ekspor |
| `kontribusi.csv` | Datetime, 5 titik | Opsional; bila tidak ada tampil "Data kontribusi belum diekspor" |
| `metadata_model.json` | UCL, λ, ARL, periode, catatan | Dari paket ekspor pertama |
| `verifikasi.csv` | Kunci_Episode, Status, Catatan, Tanggal_Pemeriksaan, Petugas, Diperbarui | Data operasional, terpisah dari hasil model |
| `verifikasi_log.csv` | sama | Riwayat setiap perubahan verifikasi |
| `riwayat_import.json` | waktu, jenis, mode, file, periode | Jejak import |

Nomor episode tidak disimpan; selalu dihitung ulang dari `Sinyal` (rangkaian jam bersinyal berurutan,
sama dengan aturan di skrip ekspor).

## Mencoba dengan data sintetis

`contoh_data/` berisi paket rekaan (Juli, lanjutan Agustus, dan tekanan mentah 8–10 Agustus) untuk
mencoba import berkelanjutan. Dashboard menampilkan peringatan **DATA SINTETIS** selama data ini dimuat.
Hapus lewat tab *Backup & reset* sebelum mengimpor paket asli.

## Uji penerimaan

Halaman **06 Validasi Model** otomatis memeriksa data Phase II (21–31 Juli 2026) terhadap acuan brief:
264 waktu & 5 titik, UCL 22,5640, 57 sinyal, 10 episode, maks T² ≈ 73,758, Bangun Reksa dominan 5 episode.
Semua harus ✓ setelah paket asli diimpor.
