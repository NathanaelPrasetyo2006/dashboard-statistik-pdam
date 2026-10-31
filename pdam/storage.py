"""Penyimpanan data dashboard: import tekanan, penerapan Model A, verifikasi, dan backup.

Yang disimpan hanya data tekanan (`tekanan.csv`) dan catatan operator. Statistik T², sinyal,
episode, dan kontribusi selalu dihitung ulang dari tekanan dengan parameter Model A yang
dibekukan (`pdam/model_A.json`), sehingga hasilnya tidak bisa diubah tangan. Catatan verifikasi
disimpan terpisah (`verifikasi.csv`) dan tidak pernah menyentuh hasil analisis.
"""
from __future__ import annotations

import io
import json
import numbers
import re
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st

from . import model
from .config import DATA_DIR, INFO_VALIDASI, STATUS_VERIFIKASI, TITIK

F_TEKANAN = "tekanan.csv"
F_VERIFIKASI = "verifikasi.csv"
F_VERIFIKASI_LOG = "verifikasi_log.csv"
F_RIWAYAT = "riwayat_import.json"
SEMUA_FILE = [F_TEKANAN, F_VERIFIKASI, F_VERIFIKASI_LOG, F_RIWAYAT]

KOLOM_VERIFIKASI = ["Kunci_Episode", "Status", "Catatan", "Tanggal_Pemeriksaan", "Petugas", "Diperbarui"]

STATUS_ADA_T2 = "Ada T²"
STATUS_PHASE_I = "Referensi Phase I"
STATUS_TANPA_T2 = "Tanpa T² (data tidak lengkap)"


# --------------------------------------------------------------------------- util kolom

def _k(name) -> str:
    return re.sub(r"[^a-z0-9]", "", str(name).lower())


ALIAS = {
    "datetime": "Datetime", "waktu": "Datetime", "timestamp": "Datetime", "tanggaljam": "Datetime",
    "tanggal": "Tanggal", "jam": "Jam",
    **{_k(t): t for t in TITIK},
}


def normalisasi_kolom(df: pd.DataFrame) -> pd.DataFrame:
    return df.rename(columns={c: ALIAS.get(_k(c), c) for c in df.columns})


def _ke_angka(s: pd.Series) -> pd.Series:
    if s.dtype == object:
        s = s.astype(str).str.strip().str.replace(",", ".", regex=False)
    return pd.to_numeric(s, errors="coerce")


def _baca_tabel(raw: bytes, nama: str, header=0) -> pd.DataFrame:
    if nama.lower().endswith((".xlsx", ".xls")):
        return pd.read_excel(io.BytesIO(raw), header=header)
    teks = raw.decode("utf-8-sig", errors="replace")
    return pd.read_csv(io.StringIO(teks), sep=None, engine="python", header=header)


def _baca_tabel_tekanan(raw: bytes, nama: str) -> pd.DataFrame:
    """Baca tabel tekanan yang judulnya bisa lebih dari satu baris.

    Format data PDAM: baris 1 `Tanggal | Tekanan` (sel gabungan), baris 2 `Jam | IPA KM 8 | ... | Paldam`.
    Baris judul = baris pertama yang memuat nama titik; nama kolom yang kosong di baris itu diambil dari
    baris di atasnya (mis. `Tanggal` yang selnya digabung dua baris).
    """
    df = _baca_tabel(raw, nama, header=None).dropna(how="all").reset_index(drop=True)
    kunci_titik = {_k(t) for t in TITIK}
    judul = next((i for i in range(min(len(df), 10))
                  if sum(_k(v) in kunci_titik for v in df.iloc[i]) >= 3), 0)
    nama_kolom = []
    for j in range(df.shape[1]):
        atas = df.iloc[judul::-1, j].dropna()
        nama_kolom.append(str(atas.iloc[0]).strip() if not atas.empty else f"Kolom_{j + 1}")
    data = df.iloc[judul + 1:].reset_index(drop=True)
    data.columns = nama_kolom
    return data


def _jam_ke_timedelta(v) -> pd.Timedelta:
    """Jam dalam sehari dari berbagai bentuk: 01:00, 01.00, 1, 0.0417 (pecahan hari Excel), objek time."""
    if v is None or (not isinstance(v, str) and pd.isna(v)):
        return pd.NaT
    if isinstance(v, (time, datetime)):
        return pd.Timedelta(hours=v.hour, minutes=v.minute, seconds=v.second)
    if isinstance(v, timedelta):
        return pd.Timedelta(v)
    if isinstance(v, numbers.Real):
        return pd.Timedelta(days=v) if 0 < v < 1 else pd.Timedelta(hours=v)
    s = str(v).strip()
    cocok = re.fullmatch(r"(\d{1,2})(?:[.:](\d{2}))?(?:[.:](\d{2}))?", s)
    if cocok:
        j, m, d = (int(x or 0) for x in cocok.groups())
        return pd.Timedelta(hours=j, minutes=m, seconds=d)
    try:
        return pd.Timedelta(pd.Timestamp(s).strftime("%H:%M:%S"))
    except (ValueError, TypeError):
        return pd.NaT


def _gabung_datetime(df: pd.DataFrame) -> pd.DataFrame:
    """Bentuk kolom Datetime dari Datetime atau pasangan Tanggal + Jam."""
    if "Datetime" not in df.columns and {"Tanggal", "Jam"}.issubset(df.columns):
        # Tanggal sering berupa sel gabungan (hanya terisi di jam pertama) → isi ke bawah.
        tanggal = pd.to_datetime(df["Tanggal"], errors="coerce", dayfirst=True).dt.normalize()
        tanggal = tanggal.where(df["Tanggal"].notna(), tanggal.ffill())
        df["Datetime"] = tanggal + df["Jam"].map(_jam_ke_timedelta).astype("timedelta64[ns]")
    if "Datetime" in df.columns:
        df["Datetime"] = pd.to_datetime(df["Datetime"], errors="coerce")
    return df


# --------------------------------------------------------------------------- baca / tulis

def _path(nama: str) -> Path:
    return DATA_DIR / nama


def _baca_csv(nama: str, tanggal=()) -> pd.DataFrame | None:
    p = _path(nama)
    if not p.exists():
        return None
    df = pd.read_csv(p)
    for c in tanggal:
        if c in df.columns:
            df[c] = pd.to_datetime(df[c], errors="coerce")
    return df


def _tulis_csv(nama: str, df: pd.DataFrame) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(_path(nama), index=False)


def _baca_json(nama: str, default):
    p = _path(nama)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default


def _tulis_json(nama: str, obj) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    _path(nama).write_text(json.dumps(obj, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


# --------------------------------------------------------------------------- episode

def hitung_episode(mon: pd.DataFrame) -> pd.Series:
    """Nomor episode = rangkaian sinyal berurutan per jam (aturan yang sama dengan notebook Colab)."""
    s = mon["Sinyal"].astype(bool)
    mulai = s & (~s.shift(fill_value=False) | mon["Datetime"].diff().gt(pd.Timedelta(hours=1)))
    return mulai.cumsum().where(s).astype("Int64")


def kunci_episode(mulai: pd.Timestamp) -> str:
    return pd.Timestamp(mulai).strftime("%Y-%m-%d %H:%M")


def _tabel_episode(mon: pd.DataFrame, kon: pd.DataFrame, ver: pd.DataFrame) -> pd.DataFrame:
    sig = mon.loc[mon["Sinyal"]]
    if sig.empty:
        return pd.DataFrame(columns=["Episode", "Mulai", "Selesai", "Jumlah_Jam_Sinyal", "Maksimum_T2",
                                     "Waktu_T2_Maks", "Titik_Dominan", "Batch", "Kunci_Episode"] + KOLOM_VERIFIKASI[1:])
    ep = (sig.groupby("Episode")
          .agg(Mulai=("Datetime", "min"), Selesai=("Datetime", "max"),
               Jumlah_Jam_Sinyal=("Sinyal", "sum"), Maksimum_T2=("T2_MEWMA", "max"),
               Batch=("Batch", "first"))
          .reset_index())
    idx_maks = sig.groupby("Episode")["T2_MEWMA"].idxmax()
    ep["Waktu_T2_Maks"] = mon.loc[idx_maks.values, "Datetime"].values
    ep["Episode"] = ep["Episode"].astype(int)
    ep["Jumlah_Jam_Sinyal"] = ep["Jumlah_Jam_Sinyal"].astype(int)
    ep["Kunci_Episode"] = ep["Mulai"].map(kunci_episode)
    dom = model.titik_dominan(mon, kon).astype({"Episode": int})
    ep = ep.merge(dom, on="Episode", how="left")
    ep = ep.merge(ver, on="Kunci_Episode", how="left")
    ep["Status"] = ep["Status"].fillna(STATUS_VERIFIKASI[0])
    for c in ["Catatan", "Petugas", "Tanggal_Pemeriksaan", "Diperbarui"]:
        ep[c] = ep[c].fillna("")
    return ep


# --------------------------------------------------------------------------- store

@dataclass
class Store:
    metadata: dict
    monitoring: pd.DataFrame          # Datetime, T2_MEWMA, UCL, Sinyal, Batch, Episode
    tekanan: pd.DataFrame             # Datetime, 5 titik, Batch, Status_Model
    episodes: pd.DataFrame
    kontribusi: pd.DataFrame          # Datetime, 5 titik (T² − T² tanpa titik itu)
    profil: pd.DataFrame              # profil per jam Phase I (beku bersama model)
    riwayat: list = field(default_factory=list)

    @property
    def kosong(self) -> bool:
        return self.tekanan.empty

    @property
    def ucl(self) -> float:
        return float(self.metadata["ucl"])


def _signature() -> tuple:
    return tuple((n, _path(n).stat().st_mtime_ns if _path(n).exists() else 0) for n in SEMUA_FILE)


def _status_model(tek: pd.DataFrame, mon: pd.DataFrame, meta: dict) -> pd.Series:
    a, b = meta["periode_phase_i"]
    fase1 = tek["Datetime"].between(pd.Timestamp(a), pd.Timestamp(b) + pd.Timedelta(hours=23))
    status = pd.Series(STATUS_TANPA_T2, index=tek.index)
    status[fase1] = STATUS_PHASE_I
    status[tek["Datetime"].isin(set(mon["Datetime"]))] = STATUS_ADA_T2
    return status


@st.cache_data(show_spinner="Menghitung statistik MEWMA…")
def _muat(_sig: tuple, data_dir: str) -> Store:
    params = model.muat_model()
    meta = {**{k: v for k, v in params.items() if k not in ("koefisien", "sigma_z", "mu0", "profil_phase_i")},
            **INFO_VALIDASI}

    tek = _baca_csv(F_TEKANAN, ["Datetime"])
    if tek is None:
        tek = pd.DataFrame({"Datetime": pd.Series(dtype="datetime64[ns]"), **{t: pd.Series(dtype=float) for t in TITIK},
                            "Batch": pd.Series(dtype=object)})
    tek = tek.sort_values("Datetime").reset_index(drop=True)

    mon, kon = model.hitung_monitoring(tek, params)
    mon = mon.merge(tek[["Datetime", "Batch"]], on="Datetime", how="left")
    mon["Episode"] = hitung_episode(mon) if not mon.empty else pd.Series(dtype="Int64")
    tek["Status_Model"] = _status_model(tek, mon, meta)

    ver = _baca_csv(F_VERIFIKASI)
    if ver is None:
        ver = pd.DataFrame(columns=KOLOM_VERIFIKASI)
    ver = ver.astype({c: "object" for c in KOLOM_VERIFIKASI})
    eps = _tabel_episode(mon, kon, ver)
    profil = pd.DataFrame(params["profil_phase_i"])
    return Store(meta, mon, tek, eps, kon, profil, _baca_json(F_RIWAYAT, []))


def muat_store() -> Store:
    return _muat(_signature(), str(DATA_DIR))


def _segarkan():
    _muat.clear()


# --------------------------------------------------------------------------- import tekanan

def _rapikan_tekanan(df: pd.DataFrame):
    pesan = {"galat": [], "peringatan": []}
    df = _gabung_datetime(normalisasi_kolom(df))
    kurang = [t for t in ["Datetime", *TITIK] if t not in df.columns]
    if kurang:
        pesan["galat"].append("Data tekanan kekurangan kolom: " + ", ".join(kurang)
                              + ". Gunakan template Excel; nama titik harus: " + ", ".join(TITIK) + ".")
        return None, pesan
    for t in TITIK:
        df[t] = _ke_angka(df[t])
    n_waktu = int(df["Datetime"].isna().sum())
    if n_waktu:
        pesan["peringatan"].append(f"{n_waktu} baris tanpa tanggal/jam yang valid dibuang.")
    df = df.dropna(subset=["Datetime"]).sort_values("Datetime")
    n_ganda = int(df["Datetime"].duplicated().sum())
    if n_ganda:
        pesan["peringatan"].append(f"{n_ganda} waktu tercatat ganda di file; yang terakhir dipakai.")
    df = df.drop_duplicates("Datetime", keep="last")
    kosong = df[TITIK].isna().sum()
    if kosong.any():
        pesan["peringatan"].append(
            "Nilai tekanan kosong: " + ", ".join(f"{t} {n}" for t, n in kosong.items() if n)
            + ". Kekosongan 1 jam diisi interpolasi oleh model; kekosongan lebih panjang membuat jam tersebut "
              "tidak memiliki T².")
    selang = df["Datetime"].diff().dropna()
    loncat = int((selang != pd.Timedelta(hours=1)).sum())
    if loncat:
        pesan["peringatan"].append(f"{loncat} selang waktu tidak sama dengan 1 jam (ada jam yang hilang atau loncat).")
    return df[["Datetime", *TITIK]].reset_index(drop=True), pesan


def baca_tekanan(unggahan):
    try:
        df = _baca_tabel_tekanan(unggahan.getvalue(), unggahan.name)
    except Exception as e:  # noqa: BLE001
        return None, {"galat": [f"Gagal membaca file: {e}"], "peringatan": []}
    return _rapikan_tekanan(df)


def _gabung(lama: pd.DataFrame | None, baru: pd.DataFrame, kunci: str) -> pd.DataFrame:
    if lama is None or lama.empty:
        return baru.sort_values(kunci)
    return (pd.concat([lama, baru], ignore_index=True)
            .drop_duplicates(kunci, keep="last").sort_values(kunci))


def pratinjau_import(df: pd.DataFrame, store: Store) -> pd.DataFrame:
    """Hitung T² untuk jam-jam di file baru seperti setelah disimpan (data lama ikut dipakai sebagai lag)."""
    gabungan = _gabung(store.tekanan[["Datetime", *TITIK]], df, "Datetime")
    mon, _ = model.hitung_monitoring(gabungan, model.muat_model())
    return mon[mon["Datetime"].isin(set(df["Datetime"]))].reset_index(drop=True)


def _catat_riwayat(entri: dict) -> None:
    r = _baca_json(F_RIWAYAT, [])
    r.append({"waktu_import": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), **entri})
    _tulis_json(F_RIWAYAT, r)


def simpan_tekanan(df: pd.DataFrame, batch: str, nama_file: str, mon_baru: pd.DataFrame) -> None:
    _tulis_csv(F_TEKANAN, _gabung(_baca_csv(F_TEKANAN, ["Datetime"]), df.assign(Batch=batch), "Datetime"))
    _catat_riwayat({"periode_data": batch, "file": nama_file, "jam": len(df),
                    "rentang": f"{df['Datetime'].min():%Y-%m-%d %H:%M} s.d. {df['Datetime'].max():%Y-%m-%d %H:%M}",
                    "jam_dengan_T2": len(mon_baru), "sinyal": int(mon_baru["Sinyal"].sum())})
    _segarkan()


def template_tekanan() -> bytes:
    """Template Excel dengan tata letak data PDAM: judul dua baris (Tanggal | Tekanan → Jam + lima titik)."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font

    wb = Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws["A1"], ws["B1"], ws["B2"] = "Tanggal", "Tekanan", "Jam"
    for j, t in enumerate(TITIK, start=3):
        ws.cell(row=2, column=j, value=t)
    ws.merge_cells("A1:A2")
    ws.merge_cells(start_row=1, start_column=2, end_row=1, end_column=2 + len(TITIK))
    for baris in ws.iter_rows(min_row=1, max_row=2):
        for c in baris:
            c.font = Font(bold=True)
            c.alignment = Alignment(horizontal="center", vertical="center")
    for jam in range(24):
        r = 3 + jam
        ws.cell(row=r, column=1, value=datetime(2026, 8, 1)).number_format = "dd/mm/yyyy"
        ws.cell(row=r, column=2, value=time(jam)).number_format = "hh:mm"
    ws.column_dimensions["A"].width = 13
    for j in range(3, 3 + len(TITIK)):
        ws.column_dimensions[ws.cell(row=2, column=j).column_letter].width = 16
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# --------------------------------------------------------------------------- verifikasi

def simpan_verifikasi(kunci: str, status: str, catatan: str, tanggal: str, petugas: str) -> None:
    ver = _baca_csv(F_VERIFIKASI)
    if ver is None:
        ver = pd.DataFrame(columns=KOLOM_VERIFIKASI)
    baris = {"Kunci_Episode": kunci, "Status": status, "Catatan": catatan,
             "Tanggal_Pemeriksaan": tanggal, "Petugas": petugas,
             "Diperbarui": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
    ver = pd.concat([ver[ver["Kunci_Episode"] != kunci], pd.DataFrame([baris])], ignore_index=True)
    _tulis_csv(F_VERIFIKASI, ver)
    log = _baca_csv(F_VERIFIKASI_LOG)
    _tulis_csv(F_VERIFIKASI_LOG, pd.concat([log, pd.DataFrame([baris])], ignore_index=True)
               if log is not None else pd.DataFrame([baris]))
    _segarkan()


def log_verifikasi() -> pd.DataFrame | None:
    return _baca_csv(F_VERIFIKASI_LOG)


# --------------------------------------------------------------------------- backup / pulihkan / reset

def buat_backup() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for n in SEMUA_FILE:
            if _path(n).exists():
                z.write(_path(n), arcname=n)
    return buf.getvalue()


def pulihkan_backup(raw: bytes) -> list[str]:
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        nama = [n for n in z.namelist() if n in SEMUA_FILE]
        if F_TEKANAN not in nama:
            raise ValueError("ZIP ini bukan backup dashboard (tidak ada tekanan.csv).")
        hapus_semua()
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        for n in nama:
            _path(n).write_bytes(z.read(n))
    _segarkan()
    return nama


def hapus_semua() -> None:
    if DATA_DIR.exists():
        for n in SEMUA_FILE:
            _path(n).unlink(missing_ok=True)
    _segarkan()


def ada_data() -> bool:
    return _path(F_TEKANAN).exists()
