"""Komponen tampilan yang dipakai banyak halaman."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from .storage import Store

KUNCI_RENTANG = "rentang_global"


def satuan(store: Store) -> str:
    return store.metadata.get("satuan_tekanan") or "satuan sesuai sensor"


def rentang(store: Store):
    nilai = st.session_state.get(KUNCI_RENTANG)
    if isinstance(nilai, (list, tuple)) and len(nilai) in (1, 2):
        # Saat pengguna baru memilih tanggal awal, rentang diperlakukan sebagai satu hari.
        return pd.Timestamp(nilai[0]), pd.Timestamp(nilai[-1])
    waktu = store.monitoring["Datetime"] if not store.monitoring.empty else store.tekanan["Datetime"]
    return waktu.min().normalize(), waktu.max().normalize()


def kepala(judul: str, store: Store, keterangan: str | None = None) -> None:
    st.title(judul)
    if store.kosong:
        return
    jenis = store.metadata.get("jenis_data", "Historis, bukan realtime")
    a, b = rentang(store)
    st.caption(f"**{jenis.upper()}** · {store.metadata.get('nama_model', 'Model')} · "
               f"Rentang tampilan {a:%d %b %Y} – {b:%d %b %Y} · resolusi "
               f"{store.metadata.get('interval_pengamatan', '1 jam')} · tekanan dalam {satuan(store)}")
    if "SINTETIS" in jenis.upper():
        st.warning("Data yang sedang dimuat adalah **data sintetis untuk uji coba**, bukan hasil Model A. "
                   "Ganti dengan paket ekspor Colab di halaman Kelola Data.", icon=":material/science:")
    if keterangan:
        st.markdown(keterangan)


def wajib_data(store: Store, butuh_model=True) -> None:
    kosong = store.monitoring.empty if butuh_model else store.kosong
    if kosong:
        st.info("Belum ada data hasil model. Import paket `dashboard_model_A.zip` hasil ekspor Colab "
                "di halaman **Kelola Data** terlebih dahulu.", icon=":material/upload_file:")
        st.page_link("views/kelola_data.py", label="Buka Kelola Data", icon=":material/database:")
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
