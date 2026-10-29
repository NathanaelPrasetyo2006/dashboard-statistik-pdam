"""Konstanta bersama: titik tekanan, lokasi penyimpanan, label, dan warna."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("PDAM_DATA_DIR", ROOT / "data"))

TITIK = ["IPA KM 8", "Bangun Reksa", "Simpang Prumnas", "Ojek Maxi", "Paldam"]

# Nilai acuan Model A dari brief & panduan serah-terima (dipakai untuk uji penerimaan).
UCL_MODEL_A = 22.5640
ACUAN_UJI = {
    "periode_phase_ii": ("2026-07-21", "2026-07-31"),
    "n_observasi": 264,
    "n_sinyal": 57,
    "n_episode": 10,
    "maks_t2": 73.758,
    "dominan": ("Bangun Reksa", 5),
}

STATUS_VERIFIKASI = ["Belum diperiksa", "Dalam pemeriksaan", "Terkonfirmasi", "Tidak terkonfirmasi"]

# Informasi model yang tercantum di brief tetapi tidak ada di metadata_model.json hasil ekspor.
# Metadata hasil ekspor selalu didahulukan bila memuat kunci yang sama.
INFO_MODEL_BRIEF = {
    "struktur_model": "VARX + Fourier → residual → MEWMA",
    "baseline_p_rata_rata": 0.13293,
    "baseline_p_kovarians": 0.38481,
    "data_khusus": "Interpolasi 2 nilai; pengamatan ekstrem 9 Juli 12.00 (Phase I)",
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
