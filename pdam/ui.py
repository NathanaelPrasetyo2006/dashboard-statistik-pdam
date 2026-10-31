"""Komponen tampilan yang dipakai banyak halaman."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from .config import SATUAN_TEKANAN
from .storage import Store

KUNCI_RENTANG = "rentang_global"


def satuan(store: Store) -> str:
    return SATUAN_TEKANAN


def rentang(store: Store):
    nilai = st.session_state.get(KUNCI_RENTANG)
    if isinstance(nilai, (list, tuple)) and len(nilai) in (1, 2):
        # Saat pengguna baru memilih tanggal awal, rentang diperlakukan sebagai satu hari.
        return pd.Timestamp(nilai[0]), pd.Timestamp(nilai[-1])
    waktu = store.tekanan["Datetime"]
    return waktu.min().normalize(), waktu.max().normalize()


def kepala(judul: str, store: Store, keterangan: str | None = None) -> None:
    st.title(judul)
    if store.kosong:
        return
    a, b = rentang(store)
    unit = f" · tekanan dalam {satuan(store)}" if satuan(store) else ""
    st.caption(f"**DATA HISTORIS PER JAM** · {store.metadata['nama_model']} "
               f"({store.metadata['struktur_model']}) · Rentang tampilan {a:%d %b %Y} – {b:%d %b %Y}{unit}")
    if keterangan:
        st.markdown(keterangan)


def wajib_data(store: Store, butuh_model=True) -> None:
    if store.kosong:
        st.info("Belum ada data tekanan. Import file Excel tekanan per jam di halaman **Kelola Data**.",
                icon=":material/upload_file:")
        st.page_link("views/kelola_data.py", label="Buka Kelola Data", icon=":material/database:")
        st.stop()
    if butuh_model and store.monitoring.empty:
        a, _ = store.metadata["periode_phase_ii"]
        st.info(f"Belum ada jam dengan statistik T² MEWMA. T² dihitung untuk data sejak {pd.Timestamp(a):%d %b %Y} "
                "(awal Phase II) dengan lima tekanan dan data 24 jam sebelumnya lengkap.", icon=":material/info:")
        st.stop()


def batasan(*poin: str) -> None:
    st.caption("  \n".join(f"⚠ {p}" for p in poin))


def _kata_sandi() -> str | None:
    try:
        return st.secrets.get("ADMIN_PASSWORD")
    except Exception:  # noqa: BLE001 - tidak ada secrets.toml = mode lokal tanpa kata sandi
        return None


def perlu_login() -> bool:
    return _kata_sandi() is not None


def admin_aktif() -> bool:
    return not perlu_login() or st.session_state.get("admin", False)


def form_login() -> None:
    if not perlu_login():
        return
    if st.session_state.get("admin"):
        st.caption("Masuk sebagai pengelola data.")
        if st.button("Keluar", icon=":material/logout:"):
            st.session_state["admin"] = False
            st.rerun()
        return
    with st.popover("Masuk pengelola", icon=":material/lock:"):
        sandi = st.text_input("Kata sandi", type="password")
        if st.button("Masuk"):
            if sandi == _kata_sandi():
                st.session_state["admin"] = True
                st.rerun()
            else:
                st.error("Kata sandi salah.")


def kunci_admin(pesan="Hanya pengelola data yang dapat melakukan perubahan. Masuk lewat tombol di sidebar.") -> bool:
    """True bila boleh mengubah data; bila tidak, tampilkan pesan."""
    if admin_aktif():
        return True
    st.info(pesan, icon=":material/lock:")
    return False
