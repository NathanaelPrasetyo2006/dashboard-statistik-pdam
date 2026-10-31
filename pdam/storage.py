"""Penyimpanan data dashboard per jaringan: import tekanan, penerapan model, verifikasi, dan backup.

Setiap jaringan punya folder `data/<id>/` berisi data tekanan (`tekanan.csv`), catatan operator, riwayat
import, dan (opsional) model lokal. Statistik T², sinyal, episode, dan kontribusi selalu dihitung ulang dari
tekanan dengan model aktif jaringan tersebut, sehingga hasilnya tidak bisa diubah tangan. Catatan verifikasi
disimpan terpisah (`verifikasi.csv`) dan tidak pernah menyentuh hasil analisis.
"""
from __future__ import annotations

import io
import json
import numbers
import re
import shutil
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st

from . import jaringan as jr
from . import model
from .config import DATA_DIR, JARINGAN_AWAL, MIN_HARI_PHASE_I, STATUS_VERIFIKASI

F_TEKANAN = "tekanan.csv"
F_VERIFIKASI = "verifikasi.csv"
F_VERIFIKASI_LOG = "verifikasi_log.csv"
F_RIWAYAT = "riwayat_import.json"
FILE_DATA = [F_TEKANAN, F_VERIFIKASI, F_VERIFIKASI_LOG, F_RIWAYAT]

KOLOM_VERIFIKASI = ["Kunci_Episode", "Status", "Catatan", "Tanggal_Pemeriksaan", "Petugas", "Diperbarui"]

STATUS_ADA_T2 = "Ada T²"
STATUS_PHASE_I = "Referensi Phase I"
STATUS_TANPA_T2 = "Tanpa T² (data tidak lengkap)"
STATUS_TANPA_MODEL = "Tanpa T² (belum ada model)"

KOLOM_WAKTU = {"datetime", "waktu", "timestamp", "tanggaljam", "tanggal", "jam", "tgl"}


# --------------------------------------------------------------------------- util kolom

def _k(name) -> str:
    return re.sub(r"[^a-z0-9]", "", str(name).lower())


ALIAS_WAKTU = {"datetime": "Datetime", "waktu": "Datetime", "timestamp": "Datetime", "tanggaljam": "Datetime",
               "tanggal": "Tanggal", "tgl": "Tanggal", "jam": "Jam"}


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

    Contoh format PDAM: baris 1 `Tanggal | Tekanan` (sel gabungan), baris 2 `Jam | <titik 1> | <titik 2> | ...`.
    Baris judul = baris pertama yang memuat kolom waktu (`Jam`, `Datetime`, `Waktu`); nama kolom yang kosong
    di baris itu diambil dari baris di atasnya (mis. `Tanggal` yang selnya digabung dua baris).
    """
    df = _baca_tabel(raw, nama, header=None).dropna(how="all").reset_index(drop=True)
    judul = next((i for i in range(min(len(df), 10))
                  if any(_k(v) in {"jam", "datetime", "waktu", "timestamp", "tanggaljam"} for v in df.iloc[i])), 0)
    nama_kolom = []
    for j in range(df.shape[1]):
        atas = df.iloc[judul::-1, j].dropna()
        nama_kolom.append(str(atas.iloc[0]).strip() if not atas.empty else f"Kolom_{j + 1}")
    data = df.iloc[judul + 1:].reset_index(drop=True)
    data.columns = nama_kolom
    data = data.loc[:, ~pd.Index(nama_kolom).duplicated()]
    return data.rename(columns={c: ALIAS_WAKTU.get(_k(c), c) for c in data.columns})


def kolom_titik(df: pd.DataFrame) -> list[str]:
    """Kolom yang berisi angka tekanan: selain kolom waktu, kolom tanpa judul, dan kolom teks."""
    hasil = []
    for c in df.columns:
        if _k(c) in KOLOM_WAKTU or c in ("Datetime", "Tanggal", "Jam") or str(c).startswith("Kolom_"):
            continue
        isi = df[c].dropna()
        if not isi.empty and _ke_angka(isi).notna().mean() >= 0.5:
            hasil.append(str(c).strip())
    return hasil


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

def _path(jid: str, nama: str) -> Path:
    return jr.dir_data(jid) / nama


def _baca_csv(jid: str, nama: str, tanggal=()) -> pd.DataFrame | None:
    p = _path(jid, nama)
    if not p.exists():
        return None
    df = pd.read_csv(p)
    for c in tanggal:
        if c in df.columns:
            df[c] = pd.to_datetime(df[c], errors="coerce")
    return df


def _tulis_csv(jid: str, nama: str, df: pd.DataFrame) -> None:
    jr.dir_data(jid).mkdir(parents=True, exist_ok=True)
    df.to_csv(_path(jid, nama), index=False)


def _baca_json(jid: str, nama: str, default):
    p = _path(jid, nama)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default


def _tulis_json(jid: str, nama: str, obj) -> None:
    jr.dir_data(jid).mkdir(parents=True, exist_ok=True)
    _path(jid, nama).write_text(json.dumps(obj, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def _pindahkan_tata_letak_lama() -> None:
    """Data versi lama (satu jaringan, file langsung di data/) dipindah ke folder jaringan awal."""
    for n in FILE_DATA:
        lama = DATA_DIR / n
        if lama.exists():
            jr.dir_data(JARINGAN_AWAL).mkdir(parents=True, exist_ok=True)
            shutil.move(str(lama), str(_path(JARINGAN_AWAL, n)))


# --------------------------------------------------------------------------- episode

def hitung_episode(mon: pd.DataFrame) -> pd.Series:
    """Nomor episode = rangkaian sinyal berurutan per jam (aturan yang sama dengan notebook Colab)."""
    s = mon["Sinyal"].astype(bool)
    mulai = s & (~s.shift(fill_value=False) | mon["Datetime"].diff().gt(pd.Timedelta(hours=1)))
    return mulai.cumsum().where(s).astype("Int64")


def kunci_episode(mulai: pd.Timestamp) -> str:
    return pd.Timestamp(mulai).strftime("%Y-%m-%d %H:%M")


def _tabel_episode(mon: pd.DataFrame, kon: pd.DataFrame, ver: pd.DataFrame, titik: list[str]) -> pd.DataFrame:
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
    dom = model.titik_dominan(mon, kon, titik).astype({"Episode": int})
    ep = ep.merge(dom, on="Episode", how="left")
    ep = ep.merge(ver, on="Kunci_Episode", how="left")
    ep["Status"] = ep["Status"].fillna(STATUS_VERIFIKASI[0])
    for c in ["Catatan", "Petugas", "Tanggal_Pemeriksaan", "Diperbarui"]:
        ep[c] = ep[c].fillna("")
    return ep


# --------------------------------------------------------------------------- store

@dataclass
class Store:
    jaringan: jr.Jaringan
    model: dict | None                # model aktif yang cocok dengan titik jaringan (None = belum ada)
    status_model: str                 # "ada" | "belum" | "tidak_cocok"
    monitoring: pd.DataFrame          # Datetime, T2_MEWMA, UCL, Sinyal, Batch, Episode
    tekanan: pd.DataFrame             # Datetime, titik…, Batch, Status_Model
    episodes: pd.DataFrame
    kontribusi: pd.DataFrame          # Datetime, titik… (T² − T² tanpa titik itu)
    riwayat: list = field(default_factory=list)

    @property
    def titik(self) -> list[str]:
        return list(self.jaringan.titik)

    @property
    def kosong(self) -> bool:
        return self.tekanan.empty

    @property
    def ada_model(self) -> bool:
        return self.model is not None

    @property
    def metadata(self) -> dict:
        if self.model is None:
            return {}
        return {k: v for k, v in self.model.items() if k not in ("koefisien", "sigma_z", "mu0", "profil_phase_i")}

    @property
    def ucl(self) -> float | None:
        return float(self.model["ucl"]) if self.model else None

    @property
    def profil(self) -> pd.DataFrame | None:
        return pd.DataFrame(self.model["profil_phase_i"]) if self.model else None


def _signature(jid: str) -> tuple:
    berkas = tuple((n, _path(jid, n).stat().st_mtime_ns if _path(jid, n).exists() else 0) for n in FILE_DATA)
    return berkas + jr.tanda_tangan(jid)


def _status_model(tek: pd.DataFrame, mon: pd.DataFrame, m: dict | None) -> pd.Series:
    if m is None:
        return pd.Series(STATUS_TANPA_MODEL, index=tek.index)
    a, b = m["periode_phase_i"]
    fase1 = tek["Datetime"].between(pd.Timestamp(a), pd.Timestamp(b) + pd.Timedelta(hours=23))
    status = pd.Series(STATUS_TANPA_T2, index=tek.index)
    status[fase1] = STATUS_PHASE_I
    status[tek["Datetime"].isin(set(mon["Datetime"]))] = STATUS_ADA_T2
    return status


@st.cache_data(show_spinner="Menghitung statistik MEWMA…", max_entries=8)
def _muat(jid: str, sig: tuple, data_dir: str) -> Store:
    j = jr.ambil(jid)
    titik = list(j.titik)
    m = jr.model_aktif(jid)
    status = "belum" if m is None else ("ada" if set(m["titik"]) == set(titik) else "tidak_cocok")
    if status != "ada":
        m = None

    tek = _baca_csv(jid, F_TEKANAN, ["Datetime"])
    if tek is None:
        tek = pd.DataFrame({"Datetime": pd.Series(dtype="datetime64[ns]"), "Batch": pd.Series(dtype=object)})
    for t in titik:
        if t not in tek.columns:
            tek[t] = float("nan")
    tek = tek[["Datetime", *titik, "Batch"]].sort_values("Datetime").reset_index(drop=True)

    if m is not None:
        mon, kon = model.hitung_monitoring(tek, m)
    else:
        mon, kon = model._kosong(titik)
    mon = mon.merge(tek[["Datetime", "Batch"]], on="Datetime", how="left")
    mon["Episode"] = hitung_episode(mon) if not mon.empty else pd.Series(dtype="Int64")
    tek["Status_Model"] = _status_model(tek, mon, m)

    ver = _baca_csv(jid, F_VERIFIKASI)
    if ver is None:
        ver = pd.DataFrame(columns=KOLOM_VERIFIKASI)
    ver = ver.astype({c: "object" for c in KOLOM_VERIFIKASI})
    eps = _tabel_episode(mon, kon, ver, titik)
    return Store(j, m, status, mon, tek, eps, kon, _baca_json(jid, F_RIWAYAT, []))


def muat_store(jid: str) -> Store:
    _pindahkan_tata_letak_lama()
    if jr.ambil(jid) is None:
        jid = JARINGAN_AWAL
    return _muat(jid, _signature(jid), str(DATA_DIR))


def segarkan():
    _muat.clear()


# --------------------------------------------------------------------------- import tekanan

@dataclass
class HasilBaca:
    data: pd.DataFrame | None                       # Datetime + titik jaringan (titik yang tidak ada = NaN)
    galat: list = field(default_factory=list)
    peringatan: list = field(default_factory=list)
    info: list = field(default_factory=list)
    titik_file: list = field(default_factory=list)  # semua kolom tekanan di file (nama asli)
    titik_baru: list = field(default_factory=list)  # kolom tekanan di file yang bukan titik jaringan


def baca_file(unggahan) -> tuple[pd.DataFrame | None, str | None]:
    try:
        return _baca_tabel_tekanan(unggahan.getvalue(), unggahan.name), None
    except Exception as e:  # noqa: BLE001
        return None, f"Gagal membaca file: {e}"


def rapikan_tekanan(df: pd.DataFrame, titik: list[str], nama_jaringan: str) -> HasilBaca:
    hasil = HasilBaca(None)
    df = _gabung_datetime(df.copy())
    if "Datetime" not in df.columns:
        hasil.galat.append("Kolom waktu tidak ditemukan. Gunakan `Tanggal` + `Jam` (lihat template) atau `Datetime`.")
        return hasil
    hasil.titik_file = kolom_titik(df)
    peta = {_k(t): t for t in titik}
    ganti = {c: peta[_k(c)] for c in hasil.titik_file if _k(c) in peta}
    hasil.titik_baru = [c for c in hasil.titik_file if _k(c) not in peta]
    if not ganti:
        hasil.galat.append(f"Tidak ada kolom yang cocok dengan titik {nama_jaringan} ({', '.join(titik)}). "
                           f"Kolom tekanan di file: {', '.join(hasil.titik_file) or '–'}. File ini kemungkinan milik "
                           "jaringan lain: pilih jaringan yang sesuai di sidebar atau tambahkan jaringan baru.")
        return hasil
    df = df.rename(columns=ganti)
    hilang = [t for t in titik if t not in df.columns]
    if hilang:
        hasil.peringatan.append(f"Kolom {', '.join(hilang)} tidak ada di file; nilainya dianggap kosong sehingga "
                                "jam-jam di file ini tidak memiliki T².")
        for t in hilang:
            df[t] = float("nan")
    if hasil.titik_baru:
        hasil.info.append(f"Kolom {', '.join(hasil.titik_baru)} bukan titik {nama_jaringan} dan tidak disimpan.")
    for t in titik:
        df[t] = _ke_angka(df[t])
    n_waktu = int(df["Datetime"].isna().sum())
    if n_waktu:
        hasil.peringatan.append(f"{n_waktu} baris tanpa tanggal/jam yang valid dibuang.")
    df = df.dropna(subset=["Datetime"]).sort_values("Datetime")
    if df.empty:
        hasil.galat.append("File tidak berisi baris data dengan tanggal/jam yang valid.")
        return hasil
    n_ganda = int(df["Datetime"].duplicated().sum())
    if n_ganda:
        hasil.peringatan.append(f"{n_ganda} waktu tercatat ganda di file; yang terakhir dipakai.")
    df = df.drop_duplicates("Datetime", keep="last")
    kosong = df[[t for t in titik if t not in hilang]].isna().sum()
    if kosong.any():
        hasil.peringatan.append(
            "Nilai tekanan kosong: " + ", ".join(f"{t} {n}" for t, n in kosong.items() if n)
            + ". Kekosongan 1 jam diisi interpolasi oleh model; kekosongan lebih panjang membuat jam tersebut "
              "tidak memiliki T².")
    loncat = int((df["Datetime"].diff().dropna() != pd.Timedelta(hours=1)).sum())
    if loncat:
        hasil.peringatan.append(f"{loncat} selang waktu tidak sama dengan 1 jam (ada jam yang hilang atau loncat).")
    hasil.data = df[["Datetime", *titik]].reset_index(drop=True)
    return hasil


def _gabung(lama: pd.DataFrame | None, baru: pd.DataFrame, kunci: str) -> pd.DataFrame:
    if lama is None or lama.empty:
        return baru.sort_values(kunci)
    return (pd.concat([lama, baru], ignore_index=True)
            .drop_duplicates(kunci, keep="last").sort_values(kunci))


def pratinjau_import(df: pd.DataFrame, store: Store) -> pd.DataFrame:
    """Hitung T² untuk jam-jam di file baru seperti setelah disimpan (data lama ikut dipakai sebagai lag)."""
    if store.model is None:
        return model._kosong(store.titik)[0]
    gabungan = _gabung(store.tekanan[["Datetime", *store.titik]], df, "Datetime")
    mon, _ = model.hitung_monitoring(gabungan, store.model)
    return mon[mon["Datetime"].isin(set(df["Datetime"]))].reset_index(drop=True)


def _catat_riwayat(jid: str, entri: dict) -> None:
    r = _baca_json(jid, F_RIWAYAT, [])
    r.append({"waktu": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), **entri})
    _tulis_json(jid, F_RIWAYAT, r)


def simpan_tekanan(jid: str, df: pd.DataFrame, batch: str, nama_file: str, mon_baru: pd.DataFrame) -> None:
    _tulis_csv(jid, F_TEKANAN, _gabung(_baca_csv(jid, F_TEKANAN, ["Datetime"]), df.assign(Batch=batch), "Datetime"))
    _catat_riwayat(jid, {"kegiatan": "Import tekanan", "periode_data": batch, "file": nama_file, "jam": len(df),
                         "rentang": f"{df['Datetime'].min():%Y-%m-%d %H:%M} s.d. {df['Datetime'].max():%Y-%m-%d %H:%M}",
                         "jam_dengan_T2": len(mon_baru), "sinyal": int(mon_baru["Sinyal"].sum())})
    segarkan()


def tambah_titik(jid: str, titik_baru: list[str]) -> None:
    j = jr.ambil(jid)
    jr.ubah(jid, titik=[*j.titik, *titik_baru])
    _catat_riwayat(jid, {"kegiatan": "Tambah titik", "file": ", ".join(titik_baru)})
    segarkan()


def template_tekanan(titik: list[str]) -> bytes:
    """Template Excel dengan tata letak data PDAM: judul dua baris (Tanggal | Tekanan → Jam + titik)."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font

    wb = Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws["A1"], ws["B1"], ws["B2"] = "Tanggal", "Tekanan", "Jam"
    for j, t in enumerate(titik, start=3):
        ws.cell(row=2, column=j, value=t)
    ws.merge_cells("A1:A2")
    ws.merge_cells(start_row=1, start_column=2, end_row=1, end_column=2 + len(titik))
    for baris in ws.iter_rows(min_row=1, max_row=2):
        for c in baris:
            c.font = Font(bold=True)
            c.alignment = Alignment(horizontal="center", vertical="center")
    for jam in range(24):
        r = 3 + jam
        ws.cell(row=r, column=1, value=datetime(2026, 8, 1)).number_format = "dd/mm/yyyy"
        ws.cell(row=r, column=2, value=time(jam)).number_format = "hh:mm"
    ws.column_dimensions["A"].width = 13
    for j in range(3, 3 + len(titik)):
        ws.column_dimensions[ws.cell(row=2, column=j).column_letter].width = 16
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# --------------------------------------------------------------------------- model per jaringan

def cek_pelatihan(store: Store, phase_i) -> tuple[list[str], int]:
    return model.cek_kelayakan(store.tekanan, store.titik, phase_i, min_hari=MIN_HARI_PHASE_I)


def latih_model_otomatis(store: Store, phase_i) -> dict:
    jid = store.jaringan.id
    mulai = (pd.Timestamp(phase_i[1]) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    m = model.latih(store.tekanan, store.titik, phase_i, mulai, sumber="otomatis",
                    nama_model=f"Model otomatis {store.jaringan.nama}")
    m["catatan"] = ["Model otomatis: struktur lag dan Fourier mengikuti Model A Jaringan KM 8 dan belum "
                    "divalidasi peneliti (diagnostik residual, pemilihan lag)."]
    jr.simpan_model(jid, m)
    _catat_riwayat(jid, {"kegiatan": "Latih model otomatis",
                         "rentang": f"Phase I {phase_i[0]} s.d. {phase_i[1]}", "file": f"UCL {m['ucl']:.4f}"})
    segarkan()
    return m


def pasang_model(store: Store, raw: bytes, nama_file: str) -> list[str]:
    """Pasang file model dari peneliti. Hasil: daftar galat (kosong = berhasil)."""
    try:
        m = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        return [f"File bukan JSON yang valid: {e}"]
    galat = model.periksa_model(m)
    if galat:
        return galat
    if set(m["titik"]) != set(store.titik):
        return [f"Titik di file model ({', '.join(m['titik'])}) tidak sama dengan titik {store.jaringan.nama} "
                f"({', '.join(store.titik)})."]
    m.setdefault("sumber", "peneliti")
    m.setdefault("nama_model", f"Model {store.jaringan.nama}")
    m.setdefault("struktur_model", "VARX + Fourier harian → residual → MEWMA")
    m.setdefault("validasi", {})
    m.setdefault("catatan", [])
    m.setdefault("interpolasi_phase_i", [])
    jr.simpan_model(store.jaringan.id, m)
    _catat_riwayat(store.jaringan.id, {"kegiatan": "Pasang model peneliti", "file": nama_file})
    segarkan()
    return []


def hapus_model_lokal(store: Store) -> None:
    jr.hapus_model_lokal(store.jaringan.id)
    _catat_riwayat(store.jaringan.id, {"kegiatan": "Hapus model lokal"})
    segarkan()


# --------------------------------------------------------------------------- verifikasi

def simpan_verifikasi(jid: str, kunci: str, status: str, catatan: str, tanggal: str, petugas: str) -> None:
    ver = _baca_csv(jid, F_VERIFIKASI)
    if ver is None:
        ver = pd.DataFrame(columns=KOLOM_VERIFIKASI)
    baris = {"Kunci_Episode": kunci, "Status": status, "Catatan": catatan,
             "Tanggal_Pemeriksaan": tanggal, "Petugas": petugas,
             "Diperbarui": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
    ver = pd.concat([ver[ver["Kunci_Episode"] != kunci], pd.DataFrame([baris])], ignore_index=True)
    _tulis_csv(jid, F_VERIFIKASI, ver)
    log = _baca_csv(jid, F_VERIFIKASI_LOG)
    _tulis_csv(jid, F_VERIFIKASI_LOG, pd.concat([log, pd.DataFrame([baris])], ignore_index=True)
               if log is not None else pd.DataFrame([baris]))
    segarkan()


def log_verifikasi(jid: str) -> pd.DataFrame | None:
    return _baca_csv(jid, F_VERIFIKASI_LOG)


# --------------------------------------------------------------------------- backup / pulihkan / reset

def buat_backup() -> bytes:
    """Semua jaringan: registri, data tekanan, verifikasi, riwayat, dan model lokal."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        if DATA_DIR.exists():
            for p in sorted(DATA_DIR.rglob("*")):
                if p.is_file():
                    z.write(p, arcname=p.relative_to(DATA_DIR).as_posix())
    return buf.getvalue()


def pulihkan_backup(raw: bytes) -> list[str]:
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        nama = [n for n in z.namelist() if not n.endswith("/") and ".." not in Path(n).parts]
        lama = [n for n in nama if n in FILE_DATA]   # backup versi satu jaringan
        if not lama and not any(Path(n).name == F_TEKANAN or n == jr.F_REGISTRI for n in nama):
            raise ValueError("ZIP ini bukan backup dashboard (tidak ada tekanan.csv atau jaringan.json).")
        if DATA_DIR.exists():
            shutil.rmtree(DATA_DIR)
        for n in nama:
            tujuan = jr.dir_data(JARINGAN_AWAL) / n if n in lama else DATA_DIR / n
            tujuan.parent.mkdir(parents=True, exist_ok=True)
            tujuan.write_bytes(z.read(n))
    segarkan()
    return nama


def hapus_data(jid: str) -> None:
    """Hapus data tekanan, verifikasi, dan riwayat satu jaringan (model dan daftar titik tetap)."""
    for n in FILE_DATA:
        _path(jid, n).unlink(missing_ok=True)
    segarkan()


def ada_data() -> bool:
    return DATA_DIR.exists() and any(p.is_file() for p in DATA_DIR.rglob("*"))
