"""Membuat paket data SINTETIS untuk mencoba dashboard sebelum paket ekspor Colab tersedia.

Angka di sini rekaan dan BUKAN hasil Model A. Metadata diberi label 'DATA SINTETIS' sehingga
dashboard menampilkan peringatan selama data ini dimuat.

Jalankan:  python tools/buat_data_demo.py
Hasil di folder contoh_data/:
  - demo_juli_2026_SINTETIS.zip     (periode awal, format sama dengan dashboard_model_A.zip)
  - demo_agustus_2026_SINTETIS.zip  (periode lanjutan 1–7 Agustus untuk menguji import berkelanjutan)
  - demo_tekanan_mentah_8-10_agustus_SINTETIS.csv (tekanan tanpa T², untuk tab import tekanan mentah)
"""
import json
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "contoh_data"
TITIK = ["IPA KM 8", "Bangun Reksa", "Simpang Prumnas", "Ojek Maxi", "Paldam"]
UCL, LAM = 22.5640, 0.1

rng = np.random.default_rng(2026)
waktu = pd.date_range("2026-07-01 00:00", "2026-08-10 23:00", freq="h")
n = len(waktu)
jam = waktu.hour.values

dasar = np.array([2.6, 1.9, 2.2, 2.5, 1.6])
amplitudo = np.array([0.35, 0.25, 0.30, 0.33, 0.20])
pola_harian = -np.cos(2 * np.pi * (jam - 3) / 24)[:, None] * amplitudo  # tekanan tinggi dini hari

# Gangguan berkorelasi (IPA KM 8 dan Ojek Maxi sangat berkorelasi) dengan sedikit autokorelasi.
kor = np.array([[1, .3, .4, .95, .2], [.3, 1, .35, .3, .25], [.4, .35, 1, .4, .3],
                [.95, .3, .4, 1, .2], [.2, .25, .3, .2, 1]])
L = np.linalg.cholesky(kor)
gangguan = np.zeros((n, 5))
for i in range(1, n):
    gangguan[i] = 0.15 * gangguan[i - 1] + (L @ rng.normal(size=5)) * 0.06
tekanan = dasar + pola_harian + gangguan

# Pergeseran rekaan pada periode monitoring (titik, mulai, lama jam, besar).
pergeseran = [("Bangun Reksa", "2026-07-21 03:00", 4, -0.14), ("Bangun Reksa", "2026-07-23 00:00", 12, -0.22),
              ("Simpang Prumnas", "2026-07-24 14:00", 5, 0.16), ("Paldam", "2026-07-26 08:00", 4, -0.14),
              ("Bangun Reksa", "2026-07-27 20:00", 5, -0.16), ("IPA KM 8", "2026-07-29 10:00", 4, 0.14),
              ("Bangun Reksa", "2026-07-31 00:00", 7, -0.24), ("Paldam", "2026-08-03 05:00", 6, -0.18),
              ("Simpang Prumnas", "2026-08-05 18:00", 4, 0.18)]
for titik, mulai, lama, besar in pergeseran:
    i0 = waktu.get_loc(pd.Timestamp(mulai))
    tekanan[i0:i0 + lama, TITIK.index(titik)] += besar
tekanan[waktu.get_loc(pd.Timestamp("2026-07-09 12:00")), 4] += 0.9  # pengamatan ekstrem Phase I

df = pd.DataFrame(tekanan.round(3), columns=TITIK)
df.insert(0, "Datetime", waktu)

# "Residual" sederhana = selisih dari rata-rata per jam Phase I (pengganti residual VARX untuk demo).
fase1 = df["Datetime"] < "2026-07-21"
profil = df[fase1].groupby(df.loc[fase1, "Datetime"].dt.hour)[TITIK].mean()
resid = df[TITIK].values - profil.loc[jam].values
sigma = np.cov(resid[fase1.values].T)
sigma_z_inv = np.linalg.inv(LAM / (2 - LAM) * sigma)
z = np.zeros(5)
t2, kontrib = np.zeros(n), np.zeros((n, 5))
for i in range(n):
    z = LAM * resid[i] + (1 - LAM) * z
    w = sigma_z_inv @ z
    t2[i], kontrib[i] = z @ w, z * w   # kontribusi menjumlah ke T²

mon = pd.DataFrame({"Datetime": waktu, "T2_MEWMA": t2.round(4), "UCL": UCL})
mon["Sinyal"] = mon["T2_MEWMA"] > UCL
mulai = mon["Sinyal"] & ~mon["Sinyal"].shift(fill_value=False)
mon["Episode"] = mulai.cumsum().where(mon["Sinyal"]).astype("Int64")
kon = pd.DataFrame(kontrib.round(4), columns=TITIK)
kon.insert(0, "Datetime", waktu)

metadata = {
    "nama_model": "DEMO SINTETIS (meniru struktur Model A)",
    "jenis_data": "DATA SINTETIS untuk uji coba, bukan hasil Model A",
    "periode_phase_i": "2026-07-01 sampai 2026-07-20",
    "periode_phase_ii": "2026-07-21 sampai 2026-07-31",
    "interval_pengamatan": "1 jam",
    "lambda_mewma": LAM, "bootstrap_blok_jam": 48, "ucl": UCL,
    "target_arl0": 200, "arl0_validasi": None, "arl0_ci95": [None, None],
    "satuan_tekanan": "bar (sintetis)",
    "interpretasi": "Sinyal menunjukkan penyimpangan statistik multivariat; bukan bukti kebocoran.",
    "catatan": "Data sintetis hanya untuk menguji tampilan dan alur import.",
}


def paket(nama, awal_mon, akhir_mon, awal_tek):
    m = mon[(mon["Datetime"] >= awal_mon) & (mon["Datetime"] <= akhir_mon)].copy()
    m["Episode"] = (m["Sinyal"] & ~m["Sinyal"].shift(fill_value=False)).cumsum().where(m["Sinyal"]).astype("Int64")
    sig = m[m["Sinyal"]]
    ep = (sig.groupby("Episode").agg(Mulai=("Datetime", "min"), Selesai=("Datetime", "max"),
                                     Jumlah_Jam_Sinyal=("Sinyal", "sum"), Maksimum_T2=("T2_MEWMA", "max"))
          .reset_index())
    k = kon.set_index("Datetime")
    ep["Titik Dominan"] = [k.loc[r.Mulai:r.Selesai, TITIK].mean().idxmax() for r in ep.itertuples()]
    ep["Status_Verifikasi"] = "Belum diverifikasi"
    t = df[(df["Datetime"] >= awal_tek) & (df["Datetime"] <= akhir_mon)]
    kk = kon[(kon["Datetime"] >= awal_mon) & (kon["Datetime"] <= akhir_mon)]
    with zipfile.ZipFile(OUT / nama, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("mewma_monitoring.csv", m.to_csv(index=False))
        z.writestr("tekanan_aktual.csv", t.to_csv(index=False))
        z.writestr("episode_monitoring.csv", ep.to_csv(index=False))
        z.writestr("kontribusi_diagnostik.csv", kk.to_csv(index=False))
        z.writestr("metadata_model.json", json.dumps(metadata, indent=2, ensure_ascii=False))
    print(f"{nama}: {len(m)} jam, {int(m['Sinyal'].sum())} sinyal, {len(ep)} episode")


OUT.mkdir(exist_ok=True)
paket("demo_juli_2026_SINTETIS.zip", "2026-07-21 00:00", "2026-07-31 23:00", "2026-07-01 00:00")
paket("demo_agustus_2026_SINTETIS.zip", "2026-08-01 00:00", "2026-08-07 23:00", "2026-08-01 00:00")
mentah = df[df["Datetime"] >= "2026-08-08"]
mentah.to_csv(OUT / "demo_tekanan_mentah_8-10_agustus_SINTETIS.csv", index=False, sep=";", decimal=",")
print(f"demo_tekanan_mentah: {len(mentah)} jam")
