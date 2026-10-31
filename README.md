# Dashboard Monitoring Tekanan Jaringan PDAM (VARX–MEWMA)

Aplikasi Streamlit untuk memantau tekanan per jam di satu atau beberapa jaringan PDAM dengan model
VARX + Fourier harian → residual → MEWMA. Pengelola cukup mengimpor file Excel tekanan; statistik T²,
kandidat OOC, episode, dan kontribusi titik dihitung otomatis, lalu verifikasi lapangan dicatat per episode.

Setiap jaringan boleh memiliki jumlah dan nama titik yang berbeda. Jaringan bawaan saat ini:
**Jaringan KM 8** (IPA KM 8, Bangun Reksa, Simpang Prumnas, Ojek Maxi, Paldam) dengan Model A dari peneliti.

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

1. Pilih jaringan di sidebar. Semua halaman menampilkan data jaringan itu.
2. **Kelola Data & Import → Import data tekanan**: unduh template jaringan bila perlu, lalu unggah file
   tekanan per jam. Judul boleh dua baris seperti `Data Bersih.xlsx` (`Tanggal` | `Tekanan` → `Jam` + titik)
   atau satu baris (`Tanggal`, `Jam`, titik… / `Datetime`, titik…).
3. Pratinjau menampilkan jumlah jam yang memperoleh T² dan jumlah kandidat OOC → **Simpan ke dashboard**.
4. Bulan berikutnya: unggah file bulan itu. Data digabung berdasarkan waktu, MEWMA berlanjut dari jam terakhir
   data sebelumnya, episode dinomori ulang secara kronologis, dan catatan verifikasi tetap menempel pada episode
   yang sama (dikunci pada waktu mulai episode).

Untuk Jaringan KM 8, mulailah dengan mengimpor data Juli 2026 (`Data Bersih.xlsx`): Phase I menjadi referensi
profil per jam dan periode 21–31 Juli menjadi bahan uji penerimaan.

### Pencocokan kolom

Kolom tekanan = semua kolom berisi angka selain `Tanggal`/`Jam`/`Datetime`. Nama kolom dicocokkan dengan nama
titik jaringan tanpa memperhatikan huruf besar/kecil dan spasi.

| Kondisi file | Yang terjadi |
|---|---|
| Semua titik ada | Diimpor normal |
| Ada titik yang tidak ada (mis. sensor rusak) | Diimpor dengan peringatan; titik itu kosong sehingga jam-jam tersebut tidak memiliki T² |
| Ada kolom yang bukan titik jaringan | Diabaikan; untuk jaringan tambahan bisa ditambahkan sebagai titik baru (model perlu dibuat ulang) |
| Tidak ada kolom yang cocok | Ditolak; dashboard menawarkan **membuat jaringan baru** dari kolom file tersebut |

Pemeriksaan lain: nilai kosong, waktu ganda (yang terakhir dipakai), selang bukan 1 jam, jam yang sudah
tersimpan (diganti nilai baru), dan jeda antara data lama dan file baru.

## Jaringan baru dan modelnya

**Kelola Data & Import → Jaringan & model → Tambah jaringan baru**: isi nama dan daftar titik (atau unggah file
contoh, titik diambil dari judul kolom), lalu import datanya. Sebelum ada model, tekanan sudah tampil di
Monitoring Tekanan dan Analisis Jaringan; halaman T², episode, dan validasi menunggu model.

Ada dua cara membuat model; periode Phase I (periode operasi normal sebagai acuan) ditentukan di keduanya:

| Cara | Siapa | Phase I & UCL | Catatan |
|---|---|---|---|
| **Model otomatis** (tab *Jaringan & model*) | Pengelola di dashboard | Phase I dipilih di kalender; UCL dikalibrasi bootstrap blok 48 jam untuk ARL₀ = 200 | Struktur mengikuti Model A KM 8; diberi label *belum divalidasi peneliti* |
| **Model peneliti** | Peneliti (Colab/lokal) | Ditentukan peneliti; UCL boleh diberikan atau dikalibrasi | File JSON dipasang lewat tab *Jaringan & model* atau disimpan di `pdam/models/` |

Model otomatis memerlukan minimal 2 titik dan 7 hari data lengkap di Phase I. Kalibrasinya sama dengan notebook
Colab: pada data KM 8 menghasilkan UCL 22,5640 dan ARL₀ validasi 194,07 (CI 182,47–205,66), persis seperti
hasil peneliti.

Membuat model peneliti dari file data:

```bash
# Jaringan KM 8 (preset; diperiksa terhadap hasil Colab sebelum ditulis)
.venv\Scripts\python tools/bekukan_model.py "Data Bersih.xlsx"

# Jaringan lain → pdam/models/cabang2.json (menjadi jaringan bawaan setelah di-commit)
.venv\Scripts\python tools/bekukan_model.py data_cabang2.xlsx --id cabang2 --nama "Jaringan Cabang 2" ^
    --phase-i 2027-01-01 2027-01-20 --satuan bar --catatan "Residual titik X masih berautokorelasi."
```

Tanpa `--ucl`, UCL dikalibrasi dengan bootstrap. File JSON hasil skrip juga bisa dipasang langsung di dashboard
(Cloud) lewat **Pasang model dari peneliti**, tanpa commit. Struktur lag/Fourier di file model dibaca apa adanya,
jadi peneliti dapat memakai struktur lain asalkan formatnya sama.

## Model A Jaringan KM 8

| Komponen | Nilai |
|---|---|
| Phase I (estimasi) / periode uji | 1–20 Juli 2026 / 21–31 Juli 2026 |
| Prediktor VARX | konstanta, sin/cos harian k = 1, 2, lag 1, 2, 3, 24 jam dari kelima titik |
| Nilai kosong | interpolasi waktu, maksimal 1 jam berurutan |
| MEWMA | λ = 0,1; rata-rata & kovarians dari residual Phase I (burn-in 50) |
| UCL | 22,5640 (ARL₀ = 200, bootstrap blok 48 jam) |
| Kontribusi titik | T² − T² tanpa titik tersebut; titik dominan episode = rata-rata kontribusi terbesar |

Halaman **06 Validasi Model** memeriksa periode uji terhadap hasil Colab: 264 jam monitoring dengan 5 tekanan
lengkap, 57 sinyal, 10 episode, maks T² ≈ 73,758, Bangun Reksa dominan 5 episode. Semua harus ✓ setelah data
Juli diimpor. Uji ini muncul untuk model yang memuat `acuan_uji`.

## Akses publik

`streamlit run` hanya menyajikan aplikasi dari komputer yang menjalankannya. Agar bisa dibuka lewat tautan,
gunakan **Streamlit Community Cloud** (gratis):

1. Unggah folder ini ke repositori GitHub (boleh privat).
2. Buka <https://share.streamlit.io> → masuk dengan GitHub → **Create app** → pilih repo, branch, file `app.py`.
3. Di *Advanced settings → Secrets* isi `ADMIN_PASSWORD = "..."` agar hanya pengelola yang bisa import data,
   mengelola jaringan/model, dan mengisi verifikasi. Pengunjung lain tetap bisa melihat dashboard.
4. Setiap `git push` otomatis memperbarui aplikasi.

**Penyimpanan di Cloud tidak permanen.** Data, jaringan tambahan, model otomatis/terpasang, dan catatan
verifikasi bisa hilang saat aplikasi tidur/dimulai ulang. Rutin **Unduh backup** (tab *Backup & reset*, berisi
semua jaringan) dan **Pulihkan** bila data hilang. Model yang sudah final sebaiknya disimpan sebagai model
bawaan di `pdam/models/` lalu di-commit. Untuk pemakaian jangka panjang, pindahkan penyimpanan ke basis data.

## Struktur

```
app.py                   navigasi, pilihan jaringan, filter tanggal global (sidebar)
views/                   satu file per halaman (01–06 + Kelola Data)
pdam/config.py           lokasi penyimpanan, pengaturan model otomatis, warna, status verifikasi
pdam/jaringan.py         daftar jaringan (bawaan + tambahan) dan model aktif masing-masing
pdam/model.py            VARX, MEWMA, kalibrasi UCL bootstrap, kontribusi, titik dominan
pdam/models/<id>.json    model peneliti jaringan bawaan (km8.json = Model A)
pdam/storage.py          import tekanan, perhitungan store per jaringan, verifikasi, backup
pdam/analysis.py         filter, profil Phase I, interpretasi berbasis aturan, uji penerimaan
pdam/charts.py           grafik Plotly
pdam/ui.py               komponen tampilan bersama, pilihan jaringan, login pengelola
tools/bekukan_model.py   membuat file model peneliti dari data tekanan
data/                    penyimpanan (dibuat otomatis saat import pertama)
```

## Kamus data penyimpanan (`data/`)

| File | Isi | Sifat |
|---|---|---|
| `jaringan.json` | jaringan tambahan (nama, titik, satuan) dan perubahan nama/satuan jaringan bawaan | Diubah lewat tab *Jaringan & model* |
| `<id>/tekanan.csv` | Datetime, titik jaringan, Batch | Satu-satunya data analisis yang disimpan; hanya berubah lewat import |
| `<id>/model.json` | model otomatis atau model peneliti yang dipasang lewat dashboard | Menggantikan model bawaan bila ada |
| `<id>/verifikasi.csv` | Kunci_Episode, Status, Catatan, Tanggal_Pemeriksaan, Petugas, Diperbarui | Data operasional, terpisah dari hasil model |
| `<id>/verifikasi_log.csv` | sama | Riwayat setiap perubahan verifikasi |
| `<id>/riwayat_import.json` | import, pelatihan/pemasangan model, penambahan titik | Jejak kegiatan |

T², sinyal, episode, dan kontribusi tidak disimpan; selalu dihitung ulang dari `tekanan.csv` dengan model aktif,
sehingga tidak dapat berubah karena penyuntingan tangan.
