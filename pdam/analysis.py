"""Perhitungan turunan untuk tampilan: filter, profil Phase I, interpretasi berbasis aturan, uji penerimaan.

Tidak ada estimasi ulang model di sini. Semua angka statistik model berasal dari data impor;
yang dihitung hanyalah ringkasan deskriptif (rata-rata per jam, selisih, korelasi).
"""
from __future__ import annotations

import re

import pandas as pd

from .config import ACUAN_UJI, TITIK, UCL_MODEL_A
from .storage import Store


def fmt_angka(x, desimal=2) -> str:
    """Format angka gaya Indonesia: 22,5640 / 1.234,5."""
    if x is None or pd.isna(x):
        return "–"
    s = f"{x:,.{desimal}f}"
    return s.replace(",", "§").replace(".", ",").replace("§", ".")


def fmt_waktu(t) -> str:
    return "–" if t is None or pd.isna(t) else pd.Timestamp(t).strftime("%d %b %Y %H:%M")


def potong(df: pd.DataFrame, awal, akhir, kolom="Datetime") -> pd.DataFrame:
    if df is None or df.empty:
        return df
    a, b = pd.Timestamp(awal), pd.Timestamp(akhir) + pd.Timedelta(days=1)
    return df[(df[kolom] >= a) & (df[kolom] < b)]


def episode_dalam_rentang(store: Store, awal, akhir) -> pd.DataFrame:
    """Episode yang memiliki setidaknya satu jam sinyal di dalam rentang."""
    mon = potong(store.monitoring, awal, akhir)
    ids = set(mon.loc[mon["Sinyal"], "Episode"].dropna().astype(int))
    return store.episodes[store.episodes["Episode"].isin(ids)]


def _periode(teks: str | None):
    if not teks:
        return None
    tgl = re.findall(r"\d{4}-\d{2}-\d{2}", str(teks))
    return (pd.Timestamp(tgl[0]), pd.Timestamp(tgl[-1])) if len(tgl) >= 2 else None


def periode_phase(store: Store, fase: str):
    return _periode(store.metadata.get(f"periode_phase_{fase}"))


def profil_phase1(store: Store) -> pd.DataFrame | None:
    """Profil rata-rata & SD per jam dalam sehari dari periode Phase I (deskriptif, bukan batas kendali)."""
    if store.profil is not None and not store.profil.empty:
        p = store.profil.copy()
        p["Jam"] = pd.to_numeric(p["Jam"], errors="coerce").astype("Int64")
        if "N" not in p.columns:
            p["N"] = pd.NA
        return p[["Jam", "Titik", "Rata_rata", "SD", "N"]]
    per = periode_phase(store, "i")
    if per is None or store.tekanan.empty:
        return None
    ref = potong(store.tekanan, *per)
    if ref.empty:
        return None
    long = ref.melt(id_vars="Datetime", value_vars=TITIK, var_name="Titik", value_name="Tekanan")
    long["Jam"] = long["Datetime"].dt.hour
    return (long.groupby(["Titik", "Jam"])["Tekanan"]
            .agg(Rata_rata="mean", SD="std", N="count").reset_index())


def deviasi(tek: pd.DataFrame, profil: pd.DataFrame | None, titik: str) -> pd.DataFrame:
    d = tek[["Datetime", titik]].rename(columns={titik: "Tekanan"}).copy()
    d["Jam"] = d["Datetime"].dt.hour
    if profil is None:
        d[["Rata_rata", "SD"]] = pd.NA
    else:
        p = profil[profil["Titik"] == titik][["Jam", "Rata_rata", "SD"]]
        d = d.merge(p, on="Jam", how="left")
    d["Selisih"] = d["Tekanan"] - d["Rata_rata"]
    d["Z"] = d["Selisih"] / d["SD"]
    return d


def z_semua_titik(tek: pd.DataFrame, profil: pd.DataFrame | None) -> pd.DataFrame:
    """Z-skor deskriptif tiap titik terhadap profil jam yang sama (kolom = titik)."""
    out = pd.DataFrame({"Datetime": tek["Datetime"].values})
    for t in TITIK:
        out[t] = deviasi(tek, profil, t)["Z"].astype(float).values
    return out


def interpretasi_t2(t2: float, ucl: float) -> tuple[str, str]:
    if t2 > ucl:
        return ("Terdeteksi kandidat penyimpangan multivariat: pola gabungan tekanan berbeda dari referensi statistik.",
                "Lihat episode dan lima tekanan; statistik MEWMA melewati batas kendali, pemeriksaan lanjutan diperlukan.")
    return ("Tidak ada sinyal MEWMA pada waktu terpilih.", "Lanjutkan pemantauan.")


def hitung_dominan(eps: pd.DataFrame) -> pd.DataFrame:
    terisi = eps["Titik_Dominan"].dropna().astype(str).str.strip()
    terisi = terisi[terisi != ""]
    hitung = terisi.value_counts()
    return pd.DataFrame({"Titik": TITIK, "Episode": [int(hitung.get(t, 0)) for t in TITIK]}), len(terisi)


def narasi_overview(eps: pd.DataFrame, awal, akhir) -> str:
    rentang = f"{pd.Timestamp(awal):%d %b %Y} – {pd.Timestamp(akhir):%d %b %Y}"
    if eps.empty:
        return f"Tidak ada episode kandidat penyimpangan selama {rentang}."
    teks = f"Terdapat {len(eps)} episode kandidat penyimpangan selama {rentang}."
    dom, n_terisi = hitung_dominan(eps)
    if n_terisi:
        top = dom.sort_values("Episode", ascending=False).iloc[0]
        seri = (dom["Episode"] == top["Episode"]).sum()
        if seri == 1:
            teks += f" {top['Titik']} paling sering dominan ({top['Episode']} episode)."
        else:
            teks += " Beberapa titik sama-sama paling sering dominan."
    else:
        teks += " Titik dominan belum tersedia pada tabel episode."
    puncak = eps.loc[eps["Maksimum_T2"].idxmax()]
    teks += f" T² tertinggi {fmt_angka(puncak['Maksimum_T2'], 3)} pada episode {int(puncak['Episode'])} ({fmt_waktu(puncak['Waktu_T2_Maks'])})."
    return teks


def uji_penerimaan(store: Store) -> list[dict]:
    """Bandingkan data Phase II Model A dengan angka acuan brief (kriteria 'cocok dengan Colab')."""
    a, b = ACUAN_UJI["periode_phase_ii"]
    mon = potong(store.monitoring, a, b)
    tek = potong(store.tekanan, a, b)
    eps = episode_dalam_rentang(store, a, b)
    dom, _ = hitung_dominan(eps)
    nama_dom, n_dom = ACUAN_UJI["dominan"]
    hasil_dom = int(dom.set_index("Titik").loc[nama_dom, "Episode"])
    tek_lengkap = int(tek.dropna(subset=TITIK).shape[0]) if not tek.empty else 0
    maks = mon["T2_MEWMA"].max() if not mon.empty else None
    ucl_ok = (not mon.empty) and bool(((mon["UCL"] - UCL_MODEL_A).abs() < 1e-4).all())
    return [
        dict(Kriteria="Waktu Phase II (monitoring)", Acuan=ACUAN_UJI["n_observasi"], Hasil=len(mon),
             Lulus=len(mon) == ACUAN_UJI["n_observasi"]),
        dict(Kriteria="Waktu Phase II dengan 5 tekanan lengkap", Acuan=ACUAN_UJI["n_observasi"], Hasil=tek_lengkap,
             Lulus=tek_lengkap == ACUAN_UJI["n_observasi"]),
        dict(Kriteria="UCL di semua baris", Acuan=fmt_angka(UCL_MODEL_A, 4),
             Hasil=fmt_angka(mon["UCL"].iloc[0], 4) if not mon.empty else "–", Lulus=ucl_ok),
        dict(Kriteria="Jumlah sinyal (Sinyal=True)", Acuan=ACUAN_UJI["n_sinyal"], Hasil=int(mon["Sinyal"].sum()),
             Lulus=int(mon["Sinyal"].sum()) == ACUAN_UJI["n_sinyal"]),
        dict(Kriteria="Jumlah episode", Acuan=ACUAN_UJI["n_episode"], Hasil=len(eps),
             Lulus=len(eps) == ACUAN_UJI["n_episode"]),
        dict(Kriteria="Maksimum T²", Acuan=fmt_angka(ACUAN_UJI["maks_t2"], 3), Hasil=fmt_angka(maks, 3),
             Lulus=maks is not None and abs(maks - ACUAN_UJI["maks_t2"]) < 0.0015),
        dict(Kriteria=f"Episode dominan {nama_dom}", Acuan=n_dom, Hasil=hasil_dom, Lulus=hasil_dom == n_dom),
    ]
