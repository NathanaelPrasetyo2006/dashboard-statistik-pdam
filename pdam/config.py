"""Konstanta bersama: lokasi penyimpanan, pengaturan model otomatis, label, dan warna.

Titik tekanan, periode Phase I, UCL, dan hasil validasi tidak ada di sini: semuanya milik
masing-masing jaringan (lihat `pdam/jaringan.py` dan file model di `pdam/models/`).
"""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("PDAM_DATA_DIR", ROOT / "data"))
MODEL_DIR = ROOT / "pdam" / "models"

JARINGAN_AWAL = "km8"   # jaringan yang dipilih saat dashboard dibuka

# Struktur dan kalibrasi model otomatis, mengikuti Model A Jaringan KM 8 (notebook Jaringan_KM_8.ipynb).
PENGATURAN_MODEL = {
    "lag": [1, 2, 3, 24],
    "fourier_k": [1, 2],
    "lambda_mewma": 0.1,
    "burn_in_kovarians": 50,
    "target_arl0": 200,
    "bootstrap_blok_jam": 48,
    "bootstrap_replikasi": 1000,
    "panjang_simulasi": 3000,
    "seed_kalibrasi": 4810,
    "seed_validasi": 4820,
}
MIN_TITIK = 2            # MEWMA multivariat memerlukan minimal dua titik
MIN_HARI_PHASE_I = 7     # data lengkap minimal untuk melatih model otomatis

STATUS_VERIFIKASI = ["Belum diperiksa", "Dalam pemeriksaan", "Terkonfirmasi", "Tidak terkonfirmasi"]

# Warna titik mengikuti urutan titik di jaringan; merah tidak dipakai karena khusus untuk sinyal.
PALET_TITIK = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4",
               "#7a5bd1", "#2aa6b8", "#a3742c", "#5f6b7a", "#9cbf3b"]
WARNA_UTAMA = "#2a78d6"      # garis T² / tekanan aktual
WARNA_PROFIL = "#eb6834"     # profil rata-rata per jam Phase I
WARNA_SINYAL = "#d03b3b"     # merah hanya untuk sinyal / perlu perhatian
WARNA_EPISODE = "rgba(208,59,59,0.10)"
WARNA_NETRAL = "#898781"

KALIMAT_BATASAN = "Sinyal tidak membuktikan kebocoran atau lokasi sumber gangguan."


def warna_titik(titik: list[str]) -> dict[str, str]:
    return {t: PALET_TITIK[i % len(PALET_TITIK)] for i, t in enumerate(titik)}
