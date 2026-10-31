"""Model VARX + Fourier harian → residual → MEWMA (Model A dari notebook Colab `Jaringan_KM_8.ipynb`).

Satu file model (JSON) memuat semua yang diperlukan untuk satu jaringan: daftar titik, struktur lag,
koefisien VARX, rata-rata & kovarians MEWMA dari Phase I, UCL, dan profil per jam Phase I. Dashboard
hanya *menerapkan* model tersebut pada data tekanan; model tidak berubah saat data baru diimpor.

Langkah per jam (mengikuti notebook):
1. Nilai kosong tunggal diisi interpolasi waktu (limit 1 jam, hanya di antara dua nilai).
2. Prediktor: konstanta, sin/cos harian, dan lag dari semua titik.
3. Residual = tekanan − prediksi VARX (satu regresi OLS per titik, dari Phase I).
4. z_t = λ(e_t − μ₀) + (1 − λ) z_{t−1}, mulai dari nol pada awal monitoring; T² = z' Σ_z⁻¹ z.
5. Kontribusi titik j = T² − T² tanpa titik j; titik dominan episode = rata-rata kontribusi terbesar.

UCL model otomatis dikalibrasi seperti notebook: residual Phase I di-bootstrap per blok, lalu UCL dicari
dengan bisection sampai rata-rata run length (ARL₀) = target, dan diperiksa dengan simulasi terpisah.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from .config import PENGATURAN_MODEL

KUNCI_WAJIB = ["titik", "lag", "fourier_k", "koefisien", "mu0", "sigma_z", "ucl", "lambda_mewma",
               "periode_phase_i", "mulai_monitoring", "profil_phase_i"]


# --------------------------------------------------------------------------- persiapan data

def _grid_per_jam(tekanan: pd.DataFrame, titik: list[str]) -> pd.DataFrame:
    """Data pada grid per jam yang rapat (jam yang tidak ada = NaN) lalu interpolasi seperti notebook."""
    d = tekanan[["Datetime", *titik]].dropna(subset=["Datetime"]).drop_duplicates("Datetime", keep="last")
    d = d.set_index("Datetime").sort_index()
    d = d.reindex(pd.date_range(d.index.min(), d.index.max(), freq="h"))
    d[titik] = d[titik].astype(float).interpolate(method="time", limit=1, limit_area="inside")
    return d


def nama_fitur(titik: list[str], lag: list[int], fourier_k: list[int]) -> list[str]:
    fourier = [f"{f}{k}" for k in fourier_k for f in ("sin", "cos")]
    return fourier + [f"{t}_lag{l}" for l in lag for t in titik]


def matriks_fitur(grid: pd.DataFrame, titik: list[str], lag: list[int], fourier_k: list[int]) -> pd.DataFrame:
    jam = grid.index.hour.to_numpy()
    X = pd.DataFrame(index=grid.index)
    for k in fourier_k:
        X[f"sin{k}"] = np.sin(2 * np.pi * k * jam / 24)
        X[f"cos{k}"] = np.cos(2 * np.pi * k * jam / 24)
    for l in lag:
        for t in titik:
            X[f"{t}_lag{l}"] = grid[t].shift(l)
    return X[nama_fitur(titik, lag, fourier_k)]


def _dengan_konstanta(X: pd.DataFrame) -> np.ndarray:
    return np.column_stack([np.ones(len(X)), X.to_numpy()])


def _mewma(E: np.ndarray, mu0: np.ndarray, lam: float) -> np.ndarray:
    z = np.zeros(E.shape[1])
    Z = np.empty_like(E)
    for i, e in enumerate(E):
        z = lam * (e - mu0) + (1 - lam) * z
        Z[i] = z
    return Z


def _kuadratik(Z: np.ndarray, S: np.ndarray) -> np.ndarray:
    return np.einsum("ij,jk,ik->i", Z, np.linalg.pinv(S), Z)


def _data_phase_i(tekanan, titik, phase_i, lag, fourier_k):
    grid = _grid_per_jam(tekanan, titik)
    X = matriks_fitur(grid, titik, lag, fourier_k)
    data = pd.concat([grid[titik], X], axis=1).dropna()
    a, b = pd.Timestamp(phase_i[0]), pd.Timestamp(phase_i[1]) + pd.Timedelta(hours=23)
    return data[(data.index >= a) & (data.index <= b)], X.columns


# --------------------------------------------------------------------------- kalibrasi UCL (bootstrap blok)

def _cummax_t2(E1, mu0, inv, lam, replikasi, panjang, blok, rng) -> np.ndarray:
    """Maksimum kumulatif T² untuk `replikasi` jalur bootstrap blok residual Phase I (seperti notebook)."""
    n, p = E1.shape
    n_blok = -(-panjang // blok)
    awal = rng.integers(0, n - blok + 1, size=(replikasi, n_blok))
    indeks = (awal[:, :, None] + np.arange(blok)).reshape(replikasi, -1)[:, :panjang]
    z = np.zeros((replikasi, p))
    t2 = np.empty((replikasi, panjang))
    for t in range(panjang):
        z = lam * (E1[indeks[:, t]] - mu0) + (1 - lam) * z
        t2[:, t] = np.einsum("ij,jk,ik->i", z, inv, z)
    return np.maximum.accumulate(t2, axis=1)


def _run_length(cummax: np.ndarray, ucl: float) -> np.ndarray:
    """Jam pertama T² > UCL; tanpa alarm = panjang simulasi (seperti `hitung_run_length` di notebook)."""
    alarm = cummax > ucl
    return np.where(alarm.any(axis=1), alarm.argmax(axis=1) + 1, cummax.shape[1])


def kalibrasi_ucl(E1, mu0, sigma_z, lam, cfg=PENGATURAN_MODEL) -> dict:
    inv = np.linalg.pinv(sigma_z)
    args = (E1, mu0, inv, lam, cfg["bootstrap_replikasi"], cfg["panjang_simulasi"], cfg["bootstrap_blok_jam"])
    cal = _cummax_t2(*args, np.random.default_rng(cfg["seed_kalibrasi"]))
    target = cfg["target_arl0"]
    low, high = 0.0, 50.0
    while _run_length(cal, high).mean() < target and high < 1e6:
        high *= 2
    for _ in range(18):
        mid = (low + high) / 2
        if _run_length(cal, mid).mean() < target:
            low = mid
        else:
            high = mid
    ucl = (low + high) / 2
    rl = _run_length(_cummax_t2(*args, np.random.default_rng(cfg["seed_validasi"])), ucl)
    se = rl.std(ddof=1) / np.sqrt(len(rl))
    return {"ucl": float(ucl), "arl0_kalibrasi": float(_run_length(cal, ucl).mean()),
            "arl0_validasi": float(rl.mean()), "arl0_ci95": [float(rl.mean() - 1.96 * se), float(rl.mean() + 1.96 * se)]}


# --------------------------------------------------------------------------- pelatihan

def cek_kelayakan(tekanan: pd.DataFrame, titik: list[str], phase_i, cfg=PENGATURAN_MODEL,
                  min_hari=7) -> tuple[list[str], int]:
    """Masalah yang menghalangi pelatihan (kosong = layak) dan jumlah jam Phase I yang lengkap."""
    galat = []
    if len(titik) < 2:
        galat.append("Model memerlukan minimal 2 titik tekanan.")
        return galat, 0
    if tekanan is None or tekanan.empty:
        return ["Belum ada data tekanan."], 0
    data, kolom = _data_phase_i(tekanan, titik, phase_i, cfg["lag"], cfg["fourier_k"])
    n, n_param = len(data), len(kolom) + 1
    if n < min_hari * 24:
        galat.append(f"Phase I hanya memiliki {n} jam lengkap (semua titik + lag {max(cfg['lag'])} jam). "
                     f"Diperlukan minimal {min_hari * 24} jam ({min_hari} hari).")
    elif n < 3 * n_param:
        galat.append(f"Phase I terlalu pendek untuk {len(titik)} titik: {n} jam lengkap, sedangkan setiap "
                     f"persamaan VARX memiliki {n_param} parameter (perlu minimal {3 * n_param} jam).")
    if n - cfg["burn_in_kovarians"] < 10 * len(titik):
        galat.append("Data Phase I tidak cukup untuk menaksir kovarians MEWMA.")
    return galat, n


def latih(tekanan: pd.DataFrame, titik: list[str], phase_i, mulai_monitoring, *, ucl: float | None = None,
          sumber: str, nama_model: str, cfg=PENGATURAN_MODEL) -> dict:
    """Estimasi model dari Phase I. `ucl=None` → UCL dikalibrasi bootstrap (model otomatis)."""
    lag, fourier_k, lam, burn = cfg["lag"], cfg["fourier_k"], cfg["lambda_mewma"], cfg["burn_in_kovarians"]
    data, kolom = _data_phase_i(tekanan, titik, phase_i, lag, fourier_k)
    A = _dengan_konstanta(data[kolom])
    koef, *_ = np.linalg.lstsq(A, data[titik].to_numpy(), rcond=None)
    E1 = data[titik].to_numpy() - A @ koef
    mu0 = E1.mean(axis=0)
    sigma_z = np.cov(_mewma(E1, mu0, lam)[burn:], rowvar=False)

    validasi = {"target_arl0": cfg["target_arl0"], "bootstrap_blok_jam": cfg["bootstrap_blok_jam"],
                "bootstrap_replikasi": cfg["bootstrap_replikasi"]}
    if ucl is None:
        hasil = kalibrasi_ucl(E1, mu0, sigma_z, lam, cfg)
        ucl = hasil.pop("ucl")
        validasi.update(hasil)

    a, b = pd.Timestamp(phase_i[0]), pd.Timestamp(phase_i[1]) + pd.Timedelta(hours=23)
    asli = tekanan.set_index("Datetime")[titik]
    asli = asli[(asli.index >= a) & (asli.index <= b)]
    profil = (asli.reset_index().melt(id_vars="Datetime", var_name="Titik", value_name="Tekanan")
              .assign(Jam=lambda d: d["Datetime"].dt.hour)
              .groupby(["Titik", "Jam"])["Tekanan"].agg(Rata_rata="mean", SD="std", N="count").reset_index())
    kosong = asli[asli.isna().any(axis=1)]
    interpolasi = [{"Datetime": f"{w:%Y-%m-%d %H:%M}", "Titik": t}
                   for w, r in kosong.iterrows() for t in titik if pd.isna(r[t])]
    return {
        "nama_model": nama_model,
        "struktur_model": "VARX + Fourier harian → residual → MEWMA",
        "sumber": sumber,
        "dibuat": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "titik": list(titik),
        "periode_phase_i": [str(phase_i[0]), str(phase_i[1])],
        "mulai_monitoring": str(mulai_monitoring),
        "lambda_mewma": lam,
        "ucl": float(ucl),
        "burn_in_kovarians": burn,
        "lag": lag,
        "fourier_k": fourier_k,
        "fitur": ["const", *kolom],
        "koefisien": koef.tolist(),
        "mu0": mu0.tolist(),
        "sigma_z": sigma_z.tolist(),
        "n_residual_phase_i": int(len(E1)),
        "validasi": validasi,
        "profil_phase_i": profil.to_dict(orient="records"),
        "interpolasi_phase_i": interpolasi,
        "catatan": [],
    }


# --------------------------------------------------------------------------- baca / periksa file model

def baca_model(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def periksa_model(m: dict) -> list[str]:
    """Galat struktur file model (dipakai saat memasang model dari peneliti)."""
    kurang = [k for k in KUNCI_WAJIB if k not in m]
    if kurang:
        return ["File model tidak lengkap; kunci yang hilang: " + ", ".join(kurang) + "."]
    p = len(m["titik"])
    n_fitur = 1 + 2 * len(m["fourier_k"]) + p * len(m["lag"])
    galat = []
    if np.shape(m["koefisien"]) != (n_fitur, p):
        galat.append(f"Ukuran koefisien {np.shape(m['koefisien'])} tidak sesuai ({n_fitur}, {p}).")
    if np.shape(m["sigma_z"]) != (p, p) or len(m["mu0"]) != p:
        galat.append("Ukuran mu0/sigma_z tidak sesuai jumlah titik.")
    return galat


# --------------------------------------------------------------------------- penerapan (dashboard)

def _kosong(titik):
    return (pd.DataFrame({"Datetime": pd.Series(dtype="datetime64[ns]"), "T2_MEWMA": pd.Series(dtype=float),
                          "UCL": pd.Series(dtype=float), "Sinyal": pd.Series(dtype=bool)}),
            pd.DataFrame({"Datetime": pd.Series(dtype="datetime64[ns]"), **{t: pd.Series(dtype=float) for t in titik}}))


def hitung_monitoring(tekanan: pd.DataFrame, model: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Terapkan model. Hasil: (monitoring [Datetime, T2_MEWMA, UCL, Sinyal], kontribusi [Datetime, titik…]).

    T² dihitung untuk jam yang ada di data sejak `mulai_monitoring` dan memiliki tekanan + seluruh lag lengkap.
    Jam yang tidak lengkap dilewati (keadaan MEWMA dibawa ke jam berikutnya, seperti notebook).
    """
    titik = model["titik"]
    if tekanan is None or tekanan.empty or not set(titik).issubset(tekanan.columns):
        return _kosong(titik)
    grid = _grid_per_jam(tekanan, titik)
    X = matriks_fitur(grid, titik, model["lag"], model["fourier_k"])
    data = pd.concat([grid[titik], X], axis=1)
    data = data[data.index.isin(set(tekanan["Datetime"]))]
    data = data[data.index >= pd.Timestamp(model["mulai_monitoring"])].dropna()
    if data.empty:
        return _kosong(titik)

    E = data[titik].to_numpy() - _dengan_konstanta(data[X.columns]) @ np.asarray(model["koefisien"])
    S = np.asarray(model["sigma_z"])
    Z = _mewma(E, np.asarray(model["mu0"]), float(model["lambda_mewma"]))
    t2 = _kuadratik(Z, S)
    ucl = float(model["ucl"])
    mon = pd.DataFrame({"Datetime": data.index, "T2_MEWMA": t2, "UCL": ucl, "Sinyal": t2 > ucl})

    kon = pd.DataFrame({"Datetime": data.index})
    for j, t in enumerate(titik):
        sisa = [i for i in range(len(titik)) if i != j]
        kon[t] = t2 - (_kuadratik(Z[:, sisa], S[np.ix_(sisa, sisa)]) if sisa else 0.0)
    return mon.reset_index(drop=True), kon


def titik_dominan(mon: pd.DataFrame, kon: pd.DataFrame, titik: list[str]) -> pd.DataFrame:
    """Per episode: titik dengan rata-rata kontribusi terbesar pada jam bersinyal (cara notebook)."""
    sig = mon.loc[mon["Sinyal"], ["Datetime", "Episode"]].merge(kon, on="Datetime")
    if sig.empty:
        return pd.DataFrame({"Episode": pd.Series(dtype=int), "Titik_Dominan": pd.Series(dtype=object)})
    rata = sig.groupby("Episode")[titik].mean()
    return rata.idxmax(axis=1).rename("Titik_Dominan").reset_index()
