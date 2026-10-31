"""Perhitungan turunan untuk tampilan: filter, profil Phase I, interpretasi berbasis aturan, uji penerimaan.

Statistik model (T², sinyal, kontribusi) dihitung di `pdam/model.py`. Di sini hanya ringkasan
deskriptif (selisih terhadap profil per jam, korelasi) dan pemeriksaan terhadap hasil peneliti.
"""
from __future__ import annotations

import pandas as pd

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


def periode_phase_i(store: Store):
    a, b = store.model["periode_phase_i"]
    return pd.Timestamp(a), pd.Timestamp(b)


def profil_phase1(store: Store) -> pd.DataFrame | None:
    """Profil rata-rata & SD per jam dalam sehari pada Phase I (deskriptif, bukan batas kendali)."""
    return store.profil


def deviasi(tek: pd.DataFrame, profil: pd.DataFrame | None, titik: str) -> pd.DataFrame:
    d = tek[["Datetime", titik]].rename(columns={titik: "Tekanan"}).copy()
    d["Jam"] = d["Datetime"].dt.hour
    if profil is None:
        d[["Rata_rata", "SD"]] = float("nan")
    else:
        p = profil[profil["Titik"] == titik][["Jam", "Rata_rata", "SD"]]
        d = d.merge(p, on="Jam", how="left")
    d["Selisih"] = d["Tekanan"] - d["Rata_rata"]
    d["Z"] = d["Selisih"] / d["SD"]
    return d


def z_semua_titik(tek: pd.DataFrame, profil: pd.DataFrame | None, titik: list[str]) -> pd.DataFrame:
    """Z-skor deskriptif tiap titik terhadap profil jam yang sama (kolom = titik)."""
    out = pd.DataFrame({"Datetime": tek["Datetime"].values})
    for t in titik:
        out[t] = deviasi(tek, profil, t)["Z"].astype(float).values
    return out


def interpretasi_t2(t2: float, ucl: float) -> tuple[str, str]:
    if t2 > ucl:
        return ("Terdeteksi kandidat penyimpangan multivariat: pola gabungan tekanan berbeda dari referensi statistik.",
                "Lihat episode dan tekanan semua titik; statistik MEWMA melewati batas kendali, pemeriksaan lanjutan "
                "diperlukan.")
    return ("Tidak ada sinyal MEWMA pada waktu terpilih.", "Lanjutkan pemantauan.")


def hitung_dominan(eps: pd.DataFrame, titik: list[str]) -> tuple[pd.DataFrame, int]:
    terisi = eps["Titik_Dominan"].dropna().astype(str).str.strip()
    terisi = terisi[terisi != ""]
    hitung = terisi.value_counts()
    return pd.DataFrame({"Titik": titik, "Episode": [int(hitung.get(t, 0)) for t in titik]}), len(terisi)


def narasi_overview(eps: pd.DataFrame, awal, akhir, titik: list[str]) -> str:
    rentang = f"{pd.Timestamp(awal):%d %b %Y} – {pd.Timestamp(akhir):%d %b %Y}"
    if eps.empty:
        return f"Tidak ada episode kandidat penyimpangan selama {rentang}."
    teks = f"Terdapat {len(eps)} episode kandidat penyimpangan selama {rentang}."
    dom, n_terisi = hitung_dominan(eps, titik)
    if n_terisi:
        top = dom.sort_values("Episode", ascending=False).iloc[0]
        seri = (dom["Episode"] == top["Episode"]).sum()
        if seri == 1:
            teks += f" {top['Titik']} paling sering dominan ({top['Episode']} episode)."
        else:
            teks += " Beberapa titik sama-sama paling sering dominan."
    else:
        teks += " Titik dominan tidak dapat ditentukan."
    puncak = eps.loc[eps["Maksimum_T2"].idxmax()]
    teks += f" T² tertinggi {fmt_angka(puncak['Maksimum_T2'], 3)} pada episode {int(puncak['Episode'])} ({fmt_waktu(puncak['Waktu_T2_Maks'])})."
    return teks


def uji_penerimaan(store: Store) -> list[dict] | None:
    """Bandingkan hasil dashboard dengan hasil peneliti (bila file model memuat `acuan_uji`)."""
    acuan = (store.model or {}).get("acuan_uji")
    if not acuan:
        return None
    a, b = acuan["periode"]
    mon = potong(store.monitoring, a, b)
    tek = potong(store.tekanan, a, b)
    eps = episode_dalam_rentang(store, a, b)
    dom, _ = hitung_dominan(eps, store.titik)
    nama_dom, n_dom = acuan["dominan"]
    hasil_dom = int(dom.set_index("Titik").loc[nama_dom, "Episode"]) if nama_dom in store.titik else 0
    tek_lengkap = int(tek.dropna(subset=store.titik).shape[0]) if not tek.empty else 0
    maks = mon["T2_MEWMA"].max() if not mon.empty else None
    return [
        dict(Kriteria="Jam monitoring pada periode uji", Acuan=acuan["n_observasi"], Hasil=len(mon),
             Lulus=len(mon) == acuan["n_observasi"]),
        dict(Kriteria=f"Jam dengan {len(store.titik)} tekanan lengkap", Acuan=acuan["n_observasi"], Hasil=tek_lengkap,
             Lulus=tek_lengkap == acuan["n_observasi"]),
        dict(Kriteria="Jumlah sinyal (Sinyal=True)", Acuan=acuan["n_sinyal"], Hasil=int(mon["Sinyal"].sum()),
             Lulus=int(mon["Sinyal"].sum()) == acuan["n_sinyal"]),
        dict(Kriteria="Jumlah episode", Acuan=acuan["n_episode"], Hasil=len(eps), Lulus=len(eps) == acuan["n_episode"]),
        dict(Kriteria="Maksimum T²", Acuan=fmt_angka(acuan["maks_t2"], 3), Hasil=fmt_angka(maks, 3),
             Lulus=maks is not None and abs(maks - acuan["maks_t2"]) < 0.0015),
        dict(Kriteria=f"Episode dominan {nama_dom}", Acuan=n_dom, Hasil=hasil_dom, Lulus=hasil_dom == n_dom),
    ]
