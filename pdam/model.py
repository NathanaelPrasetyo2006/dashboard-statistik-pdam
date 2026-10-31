"""Model A: VARX + Fourier harian → residual → MEWMA (sama dengan notebook Colab `Jaringan_KM_8.ipynb`).

Parameter dibekukan sekali dari Phase I (lihat `tools/bekukan_model.py`) dan disimpan di `model_A.json`.
Dashboard hanya *menerapkan* parameter tersebut pada data tekanan yang diimpor; model tidak pernah
diestimasi ulang, sehingga UCL dan hasil Juli 2026 tetap sama dengan Colab.

Langkah per jam (mengikuti notebook):
1. Nilai kosong tunggal diisi interpolasi waktu (limit 1 jam, hanya di antara dua nilai).
2. Prediktor: konstanta, sin/cos harian k = 1, 2, dan lag 1, 2, 3, 24 jam dari kelima titik.
3. Residual = tekanan − prediksi VARX.
4. z_t = λ(e_t − μ₀) + (1 − λ) z_{t−1}, mulai dari nol pada awal Phase II; T² = z' Σ_z⁻¹ z.
5. Kontribusi titik j = T² − T² tanpa titik j; titik dominan episode = rata-rata kontribusi terbesar.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from .config import TITIK

FILE_MODEL = Path(__file__).resolve().parent / "model_A.json"
LAG = [1, 2, 3, 24]
FOURIER_K = [1, 2]


# --------------------------------------------------------------------------- persiapan data

def _grid_per_jam(tekanan: pd.DataFrame) -> pd.DataFrame:
    """Data pada grid per jam yang rapat (jam yang tidak ada = NaN) lalu interpolasi seperti notebook."""
    d = tekanan[["Datetime", *TITIK]].dropna(subset=["Datetime"]).drop_duplicates("Datetime", keep="last")
    d = d.set_index("Datetime").sort_index()
    d = d.reindex(pd.date_range(d.index.min(), d.index.max(), freq="h"))
    d[TITIK] = d[TITIK].astype(float).interpolate(method="time", limit=1, limit_area="inside")
    return d


def nama_fitur() -> list[str]:
    fourier = [f"{f}{k}" for k in FOURIER_K for f in ("sin", "cos")]
    return fourier + [f"{t}_lag{lag}" for lag in LAG for t in TITIK]


def matriks_fitur(grid: pd.DataFrame) -> pd.DataFrame:
    jam = grid.index.hour.to_numpy()
    X = pd.DataFrame(index=grid.index)
    for k in FOURIER_K:
        X[f"sin{k}"] = np.sin(2 * np.pi * k * jam / 24)
        X[f"cos{k}"] = np.cos(2 * np.pi * k * jam / 24)
    for lag in LAG:
        for t in TITIK:
            X[f"{t}_lag{lag}"] = grid[t].shift(lag)
    return X[nama_fitur()]


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


# --------------------------------------------------------------------------- pembekuan (sekali, offline)

def latih(tekanan: pd.DataFrame, phase_i: tuple[str, str], phase_ii: tuple[str, str],
          lam: float, ucl: float, burn: int = 50) -> dict:
    """Estimasi parameter Model A dari Phase I. Dipakai `tools/bekukan_model.py`, bukan oleh dashboard."""
    grid = _grid_per_jam(tekanan)
    X = matriks_fitur(grid)
    data = pd.concat([grid[TITIK], X], axis=1).dropna()
    a, b = pd.Timestamp(phase_i[0]), pd.Timestamp(phase_i[1]) + pd.Timedelta(hours=23)
    latih_ = data[(data.index >= a) & (data.index <= b)]
    A = _dengan_konstanta(latih_[X.columns])
    koef, *_ = np.linalg.lstsq(A, latih_[TITIK].to_numpy(), rcond=None)
    E1 = latih_[TITIK].to_numpy() - A @ koef
    mu0 = E1.mean(axis=0)
    sigma_z = np.cov(_mewma(E1, mu0, lam)[burn:], rowvar=False)

    asli = tekanan.set_index("Datetime")[TITIK]
    asli = asli[(asli.index >= a) & (asli.index <= b)]
    profil = (asli.reset_index().melt(id_vars="Datetime", var_name="Titik", value_name="Tekanan")
              .assign(Jam=lambda d: d["Datetime"].dt.hour)
              .groupby(["Titik", "Jam"])["Tekanan"].agg(Rata_rata="mean", SD="std", N="count").reset_index())
    kosong = tekanan[tekanan[TITIK].isna().any(axis=1)]
    interpolasi = [{"Datetime": f"{r['Datetime']:%Y-%m-%d %H:%M}", "Titik": t}
                   for _, r in kosong.iterrows() for t in TITIK if pd.isna(r[t])]
    return {
        "nama_model": "Model A",
        "struktur_model": "VARX + Fourier harian → residual → MEWMA",
        "periode_phase_i": list(phase_i),
        "periode_phase_ii": list(phase_ii),
        "lambda_mewma": lam,
        "ucl": ucl,
        "burn_in_kovarians": burn,
        "lag": LAG,
        "fourier_k": FOURIER_K,
        "titik": TITIK,
        "fitur": ["const", *X.columns],
        "koefisien": koef.tolist(),
        "mu0": mu0.tolist(),
        "sigma_z": sigma_z.tolist(),
        "n_residual_phase_i": int(len(E1)),
        "profil_phase_i": profil.to_dict(orient="records"),
        "interpolasi_phase_i": interpolasi,
    }


# --------------------------------------------------------------------------- penerapan (dashboard)

@lru_cache(maxsize=1)
def muat_model() -> dict:
    return json.loads(FILE_MODEL.read_text(encoding="utf-8"))


def hitung_monitoring(tekanan: pd.DataFrame, model: dict | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Terapkan model beku. Hasil: (monitoring [Datetime, T2_MEWMA, UCL, Sinyal], kontribusi [Datetime, 5 titik]).

    T² dihitung untuk jam yang ada di data sejak awal Phase II dan memiliki tekanan + seluruh lag lengkap.
    Jam yang tidak lengkap dilewati (keadaan MEWMA dibawa ke jam berikutnya, seperti notebook).
    """
    model = model or muat_model()
    kosong = (pd.DataFrame({"Datetime": pd.Series(dtype="datetime64[ns]"), "T2_MEWMA": pd.Series(dtype=float),
                            "UCL": pd.Series(dtype=float), "Sinyal": pd.Series(dtype=bool)}),
              pd.DataFrame({"Datetime": pd.Series(dtype="datetime64[ns]"), **{t: pd.Series(dtype=float) for t in TITIK}}))
    if tekanan is None or tekanan.empty:
        return kosong
    grid = _grid_per_jam(tekanan)
    X = matriks_fitur(grid)
    data = pd.concat([grid[TITIK], X], axis=1)
    data = data[data.index.isin(set(tekanan["Datetime"]))]
    data = data[data.index >= pd.Timestamp(model["periode_phase_ii"][0])].dropna()
    if data.empty:
        return kosong

    koef = np.asarray(model["koefisien"])
    E = data[TITIK].to_numpy() - _dengan_konstanta(data[X.columns]) @ koef
    S = np.asarray(model["sigma_z"])
    Z = _mewma(E, np.asarray(model["mu0"]), float(model["lambda_mewma"]))
    t2 = _kuadratik(Z, S)
    ucl = float(model["ucl"])
    mon = pd.DataFrame({"Datetime": data.index, "T2_MEWMA": t2, "UCL": ucl, "Sinyal": t2 > ucl})

    kon = pd.DataFrame({"Datetime": data.index})
    for j, t in enumerate(TITIK):
        sisa = [i for i in range(len(TITIK)) if i != j]
        kon[t] = t2 - _kuadratik(Z[:, sisa], S[np.ix_(sisa, sisa)])
    return mon.reset_index(drop=True), kon


def titik_dominan(mon: pd.DataFrame, kon: pd.DataFrame) -> pd.DataFrame:
    """Per episode: titik dengan rata-rata kontribusi terbesar pada jam bersinyal (cara notebook)."""
    sig = mon.loc[mon["Sinyal"], ["Datetime", "Episode"]].merge(kon, on="Datetime")
    if sig.empty:
        return pd.DataFrame(columns=["Episode", "Titik_Dominan"])
    rata = sig.groupby("Episode")[TITIK].mean()
    return rata.idxmax(axis=1).rename("Titik_Dominan").reset_index()
