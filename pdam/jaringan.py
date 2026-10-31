"""Daftar jaringan dan model aktif masing-masing.

- Jaringan bawaan: satu file model peneliti di `pdam/models/<id>.json` (ikut repositori, tidak hilang
  saat Streamlit Cloud dimulai ulang). Titiknya mengikuti file model.
- Jaringan tambahan: dibuat pengelola di dashboard, tercatat di `data/jaringan.json`.
- Model aktif: `data/<id>/model.json` (model otomatis atau model peneliti yang dipasang lewat
  dashboard) bila ada; selain itu model bawaan di `pdam/models/<id>.json`.
"""
from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from .config import DATA_DIR, JARINGAN_AWAL, MODEL_DIR
from .model import baca_model

F_REGISTRI = "jaringan.json"
F_MODEL = "model.json"


@dataclass(frozen=True)
class Jaringan:
    id: str
    nama: str
    titik: tuple[str, ...]
    satuan: str
    bawaan: bool


def _registri() -> dict:
    p = DATA_DIR / F_REGISTRI
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def _tulis_registri(r: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / F_REGISTRI).write_text(json.dumps(r, indent=2, ensure_ascii=False), encoding="utf-8")


def _model_bawaan() -> dict[str, Path]:
    return {p.stem: p for p in sorted(MODEL_DIR.glob("*.json"))} if MODEL_DIR.exists() else {}


def daftar() -> list[Jaringan]:
    reg, hasil = _registri(), []
    for jid, path in _model_bawaan().items():
        m = baca_model(path)
        info = reg.get(jid, {})
        hasil.append(Jaringan(jid, info.get("nama") or m.get("nama_jaringan", jid), tuple(m["titik"]),
                              info.get("satuan", m.get("satuan", "")), True))
    bawaan = {j.id for j in hasil}
    for jid, info in reg.items():
        if jid not in bawaan:
            hasil.append(Jaringan(jid, info["nama"], tuple(info["titik"]), info.get("satuan", ""), False))
    hasil.sort(key=lambda j: (j.id != JARINGAN_AWAL, not j.bawaan, j.nama.lower()))
    return hasil


def ambil(jid: str) -> Jaringan | None:
    return next((j for j in daftar() if j.id == jid), None)


def dir_data(jid: str) -> Path:
    return DATA_DIR / jid


def _id_baru(nama: str) -> str:
    dasar = re.sub(r"[^a-z0-9]+", "_", nama.lower()).strip("_") or "jaringan"
    ada = {j.id for j in daftar()}
    jid, i = dasar, 2
    while jid in ada:
        jid, i = f"{dasar}_{i}", i + 1
    return jid


def tambah(nama: str, titik: list[str], satuan: str = "") -> Jaringan:
    nama = nama.strip()
    if any(j.nama.lower() == nama.lower() for j in daftar()):
        raise ValueError(f"Jaringan bernama '{nama}' sudah ada.")
    titik = [t.strip() for t in titik if t.strip()]
    if len(set(titik)) != len(titik):
        raise ValueError("Nama titik tidak boleh ganda.")
    jid = _id_baru(nama)
    reg = _registri()
    reg[jid] = {"nama": nama, "titik": titik, "satuan": satuan.strip()}
    _tulis_registri(reg)
    return ambil(jid)


def ubah(jid: str, *, nama: str | None = None, satuan: str | None = None, titik: list[str] | None = None) -> None:
    j = ambil(jid)
    reg = _registri()
    info = reg.setdefault(jid, {} if j.bawaan else {"nama": j.nama, "titik": list(j.titik), "satuan": j.satuan})
    if nama is not None:
        info["nama"] = nama.strip()
    if satuan is not None:
        info["satuan"] = satuan.strip()
    if titik is not None:
        if j.bawaan:
            raise ValueError("Titik jaringan bawaan mengikuti file model peneliti.")
        info["titik"] = list(titik)
    _tulis_registri(reg)


def hapus(jid: str) -> None:
    j = ambil(jid)
    if j is None or j.bawaan:
        raise ValueError("Jaringan bawaan tidak dapat dihapus.")
    shutil.rmtree(dir_data(jid), ignore_errors=True)
    reg = _registri()
    reg.pop(jid, None)
    _tulis_registri(reg)


# --------------------------------------------------------------------------- model aktif

def path_model(jid: str) -> Path | None:
    lokal = dir_data(jid) / F_MODEL
    if lokal.exists():
        return lokal
    return _model_bawaan().get(jid)


def model_aktif(jid: str) -> dict | None:
    p = path_model(jid)
    return baca_model(p) if p else None


def ada_model_bawaan(jid: str) -> bool:
    return jid in _model_bawaan()


def model_lokal_ada(jid: str) -> bool:
    return (dir_data(jid) / F_MODEL).exists()


def simpan_model(jid: str, m: dict) -> None:
    dir_data(jid).mkdir(parents=True, exist_ok=True)
    (dir_data(jid) / F_MODEL).write_text(json.dumps(m, indent=1, ensure_ascii=False), encoding="utf-8")


def hapus_model_lokal(jid: str) -> None:
    (dir_data(jid) / F_MODEL).unlink(missing_ok=True)


def tanda_tangan(jid: str) -> tuple:
    """Penanda perubahan registri/model untuk cache."""
    berkas = [DATA_DIR / F_REGISTRI, path_model(jid)]
    return tuple((str(p), p.stat().st_mtime_ns) for p in berkas if p and p.exists())
