"""Konstanta bersama: titik tekanan, lokasi penyimpanan, label, dan warna."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("PDAM_DATA_DIR", ROOT / "data"))

TITIK = ["IPA KM 8", "Bangun Reksa", "Simpang Prumnas", "Ojek Maxi", "Paldam"]

# Satuan tekanan sensor. Kosong = grafik hanya berlabel "Tekanan" (satuan belum dipastikan PDAM).
SATUAN_TEKANAN = ""

# Parameter Model A dari notebook Colab `Jaringan_KM_8.ipynb` (dipakai saat membekukan model).
PHASE_I = ("2026-07-01", "2026-07-20")
PHASE_II = ("2026-07-21", "2026-07-31")
LAMBDA_MEWMA = 0.1
UCL_MODEL_A = 22.5640   # kalibrasi ARL₀ = 200, bootstrap blok 48 jam

# Hasil Colab untuk Phase II (dipakai untuk uji penerimaan).
ACUAN_UJI = {
    "periode_phase_ii": ("2026-07-21", "2026-07-31"),
    "n_observasi": 264,
    "n_sinyal": 57,
    "n_episode": 10,
    "maks_t2": 73.758,
    "dominan": ("Bangun Reksa", 5),
}

STATUS_VERIFIKASI = ["Belum diperiksa", "Dalam pemeriksaan", "Terkonfirmasi", "Tidak terkonfirmasi"]

# Hasil validasi Model A di notebook Colab (tidak dihitung ulang di dashboard karena berbasis bootstrap).
INFO_VALIDASI = {
    "target_arl0": 200,
    "arl0_validasi": 194.07,
    "arl0_ci95": (182.47, 205.66),
    "bootstrap_blok_jam": 48,
    "bootstrap_replikasi": 1000,
    "baseline_p_rata_rata": 0.13293,
    "baseline_p_kovarians": 0.38481,
    "interval_pengamatan": "1 jam",
}

# Warna: satu warna tetap per titik (mengikuti entitas, bukan urutan).
WARNA_TITIK = {
    "IPA KM 8": "#2a78d6",
    "Bangun Reksa": "#eb6834",
    "Simpang Prumnas": "#1baf7a",
    "Ojek Maxi": "#eda100",
    "Paldam": "#e87ba4",
}
WARNA_UTAMA = "#2a78d6"      # garis T² / tekanan aktual
WARNA_PROFIL = "#eb6834"     # profil rata-rata per jam Phase I
WARNA_SINYAL = "#d03b3b"     # merah hanya untuk sinyal / perlu perhatian
WARNA_EPISODE = "rgba(208,59,59,0.10)"
WARNA_NETRAL = "#898781"

KALIMAT_BATASAN = "Sinyal tidak membuktikan kebocoran atau lokasi sumber gangguan."
