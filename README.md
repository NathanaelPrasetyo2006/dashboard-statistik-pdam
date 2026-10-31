# Dashboard Monitoring Tekanan Jaringan PDAM (VARX–MEWMA Model A)

Aplikasi Streamlit untuk memantau tekanan lima titik jaringan PDAM (IPA KM 8, Bangun Reksa,
Simpang Prumnas, Ojek Maxi, Paldam) dengan Model A: VARX + Fourier harian → residual → MEWMA.
Pengelola cukup mengimpor file Excel tekanan per jam; statistik T², kandidat OOC, episode, dan
kontribusi titik dihitung otomatis, lalu verifikasi lapangan dicatat per episode.

> Sinyal MEWMA = kandidat penyimpangan statistik multivariat, **bukan** bukti kebocoran.
> Data bersifat historis per jam, bukan realtime.

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

1. Buka **Kelola Data & Import** → unduh **template Excel** bila perlu.
2. Unggah file tekanan per jam (format sama dengan `Data Bersih.xlsx`: judul dua baris
   `Tanggal` | `Tekanan` → `Jam` + lima titik). CSV/Excel berkolom `Datetime` + lima titik juga diterima.
3. Pratinjau menampilkan jumlah jam yang memperoleh T² dan jumlah kandidat OOC → **Simpan ke dashboard**.
4. Bulan berikutnya: unggah file bulan itu. Data digabung berdasarkan waktu, MEWMA berlanjut dari jam
   terakhir data sebelumnya, episode dinomori ulang secara kronologis, dan catatan verifikasi tetap
   menempel pada episode yang sama (dikunci pada waktu mulai episode).

Mulailah dengan mengimpor data Juli 2026 (`Data Bersih.xlsx`): Phase I menjadi referensi profil per jam
dan Phase II menjadi bahan uji penerimaan.

Pemeriksaan saat import: nilai kosong, waktu ganda (yang terakhir dipakai), selang bukan 1 jam, jam yang
sudah tersimpan (diganti nilai baru), dan jeda antara data lama dan file baru.

## Model A di dashboard

Parameter model dibekukan sekali di `pdam/model_A.json` dan **tidak diestimasi ulang** saat import:

| Komponen | Nilai |
|---|---|
| Phase I (estimasi) / Phase II (monitoring awal) | 1–20 Juli 2026 / 21–31 Juli 2026 |
| Prediktor VARX | konstanta, sin/cos harian k = 1, 2, lag 1, 2, 3, 24 jam dari kelima titik |
| Nilai kosong | interpolasi waktu, maksimal 1 jam berurutan |
| MEWMA | λ = 0,1; rata-rata & kovarians dari residual Phase I (burn-in 50) |
| UCL | 22,5640 (ARL₀ = 200, bootstrap blok 48 jam) |
| Kontribusi titik | T² − T² tanpa titik tersebut; titik dominan episode = rata-rata kontribusi terbesar |

T² dihitung untuk setiap jam sejak 21 Juli 2026 yang memiliki lima tekanan dan data 24 jam sebelumnya.
Jam tanpa data lengkap ditandai "Tanpa T²" dan tetap tampil di grafik tekanan.

`pdam/model_A.json` dibuat dari notebook Colab `Jaringan_KM_8.ipynb` yang ditulis ulang dengan numpy:

```bash
.venv\Scripts\python tools/bekukan_model.py "Data Bersih.xlsx"
```

Skrip berhenti tanpa menulis file bila hasil Phase II tidak sama dengan Colab (264 jam, 57 sinyal,
10 episode, T² maks 73,758, Bangun Reksa dominan pada 5 episode). Jalankan ulang hanya bila peneliti
mengganti model. Angka ARL₀ validasi dan uji stabilitas baseline (bootstrap) diambil dari notebook dan
tercatat di `pdam/config.py`.

## Uji penerimaan

Halaman **06 Validasi Model** memeriksa Phase II (21–31 Juli 2026) terhadap hasil Colab: 264 waktu &
5 titik, UCL 22,5640, 57 sinyal, 10 episode, maks T² ≈ 73,758, Bangun Reksa dominan 5 episode.
Semua harus ✓ setelah data Juli diimpor.

## Akses publik

`streamlit run` hanya menyajikan aplikasi dari komputer yang menjalankannya (localhost, atau perangkat
lain di jaringan yang sama selama laptop menyala). Agar bisa dibuka lewat tautan, gunakan
**Streamlit Community Cloud** (gratis):

1. Unggah folder ini ke repositori GitHub (boleh privat).
2. Buka <https://share.streamlit.io> → masuk dengan GitHub → **Create app** → pilih repo, branch, file `app.py`.
3. Di *Advanced settings → Secrets* isi `ADMIN_PASSWORD = "..."` agar hanya pengelola yang bisa import
   data dan mengisi verifikasi. Pengunjung lain tetap bisa melihat dashboard.
4. Setiap `git push` otomatis memperbarui aplikasi.

**Penyimpanan di Cloud tidak permanen.** Data hasil import dan catatan verifikasi bisa hilang saat
aplikasi tidur/dimulai ulang. Rutin **Unduh backup** (tab *Backup & reset*) dan **Pulihkan** bila data
hilang. Untuk pemakaian jangka panjang, pindahkan penyimpanan `pdam/storage.py` ke basis data
(mis. PostgreSQL/Supabase).

## Struktur

```
app.py                   navigasi + filter tanggal global (sidebar)
views/                   satu file per halaman (01–06 + Kelola Data)
pdam/config.py           titik, periode, UCL, hasil validasi Colab, warna, status verifikasi
pdam/model.py            penerapan Model A: residual VARX, MEWMA, kontribusi, titik dominan
pdam/model_A.json        parameter Model A yang dibekukan + profil per jam Phase I
pdam/storage.py          import tekanan, perhitungan store, verifikasi, backup
pdam/analysis.py         filter, profil Phase I, interpretasi berbasis aturan, uji penerimaan
pdam/charts.py           grafik Plotly
pdam/ui.py               komponen tampilan bersama, login pengelola
tools/bekukan_model.py   membuat model_A.json dari data Juli 2026
data/                    penyimpanan (dibuat otomatis saat import pertama)
```

## Kamus data penyimpanan (`data/`)

| File | Kolom | Sifat |
|---|---|---|
| `tekanan.csv` | Datetime, 5 titik, Batch | Satu-satunya data analisis yang disimpan; hanya berubah lewat import |
| `verifikasi.csv` | Kunci_Episode, Status, Catatan, Tanggal_Pemeriksaan, Petugas, Diperbarui | Data operasional, terpisah dari hasil model |
| `verifikasi_log.csv` | sama | Riwayat setiap perubahan verifikasi |
| `riwayat_import.json` | waktu, periode, file, rentang, jam dengan T², sinyal | Jejak import |

T², sinyal, episode, dan kontribusi tidak disimpan; selalu dihitung ulang dari `tekanan.csv` dengan
parameter beku, sehingga tidak dapat berubah karena penyuntingan tangan.
