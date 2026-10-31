"""Komponen tampilan yang dipakai banyak halaman."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from . import jaringan as jr
from . import storage
from .config import JARINGAN_AWAL
from .storage import Store

KUNCI_RENTANG = "rentang_global"
KUNCI_JARINGAN = "jaringan_aktif"


# Pilihan yang bergantung pada titik/episode jaringan; dibuang saat jaringan diganti.
KUNCI_PER_JARINGAN = ["tek_titik", "tek_multi", "jar_a", "jar_b", "episode_terpilih", "ep_baris_terakhir",
                      "pk_waktu", "pk_klik_terakhir", KUNCI_RENTANG]


def reset_pilihan() -> None:
    for k in KUNCI_PER_JARINGAN:
        st.session_state.pop(k, None)


def pilih_jaringan(jid: str) -> None:
    """Pilih jaringan dari halaman mana pun; diterapkan app.py sebelum pilihan sidebar digambar."""
    st.session_state["jaringan_berikut"] = jid


def terapkan_pilihan_tertunda() -> None:
    jid = st.session_state.pop("jaringan_berikut", None)
    if jid:
        st.session_state[KUNCI_JARINGAN] = jid
        reset_pilihan()


def jaringan_aktif() -> str:
    jid = st.session_state.get(KUNCI_JARINGAN, JARINGAN_AWAL)
    return jid if jr.ambil(jid) else JARINGAN_AWAL


def muat() -> Store:
    """Store untuk jaringan yang dipilih di sidebar."""
    return storage.muat_store(jaringan_aktif())


def satuan(store: Store) -> str:
    return store.jaringan.satuan


def rentang(store: Store):
    nilai = st.session_state.get(KUNCI_RENTANG)
    if isinstance(nilai, (list, tuple)) and len(nilai) in (1, 2):
        # Saat pengguna baru memilih tanggal awal, rentang diperlakukan sebagai satu hari.
        return pd.Timestamp(nilai[0]), pd.Timestamp(nilai[-1])
    waktu = store.tekanan["Datetime"]
    return waktu.min().normalize(), waktu.max().normalize()


def label_model(store: Store) -> str:
    if store.model is None:
        return "belum ada model"
    sumber = "model peneliti" if store.model.get("sumber") == "peneliti" else "model otomatis"
    return f"{store.model['nama_model']} ({sumber})"


def kepala(judul: str, store: Store, keterangan: str | None = None) -> None:
    st.title(judul)
    if store.kosong:
        return
    a, b = rentang(store)
    unit = f" · tekanan dalam {satuan(store)}" if satuan(store) else ""
    st.caption(f"**DATA HISTORIS PER JAM** · {store.jaringan.nama} · {len(store.titik)} titik · {label_model(store)} · "
               f"Rentang tampilan {a:%d %b %Y} – {b:%d %b %Y}{unit}")
    if store.model is not None and store.model.get("sumber") != "peneliti":
        st.caption("⚠ Model otomatis belum divalidasi peneliti; gunakan hasilnya sebagai indikasi awal.")
    if keterangan:
        st.markdown(keterangan)


def _ke_kelola(label="Buka Kelola Data"):
    st.page_link("views/kelola_data.py", label=label, icon=":material/database:")


def wajib_data(store: Store, butuh_model=True) -> None:
    if store.kosong:
        st.info(f"Belum ada data tekanan untuk **{store.jaringan.nama}**. Import file Excel tekanan per jam di "
                "halaman **Kelola Data**.", icon=":material/upload_file:")
        _ke_kelola()
        st.stop()
    if not butuh_model:
        return
    if store.status_model == "tidak_cocok":
        st.warning(f"Model aktif {store.jaringan.nama} memakai titik yang berbeda dengan daftar titik jaringan "
                   "(titik jaringan berubah setelah model dibuat). Latih ulang model atau pasang model peneliti "
                   "di **Kelola Data → Jaringan & model**.", icon=":material/warning:")
        _ke_kelola()
        st.stop()
    if store.model is None:
        st.info(f"**{store.jaringan.nama}** belum memiliki model, sehingga statistik T² MEWMA belum dapat dihitung. "
                "Latih model otomatis atau pasang model dari peneliti di **Kelola Data → Jaringan & model**. "
                "Data tekanan tetap dapat dilihat di Monitoring Tekanan dan Analisis Jaringan.",
                icon=":material/model_training:")
        _ke_kelola()
        st.stop()
    if store.monitoring.empty:
        a = pd.Timestamp(store.model["mulai_monitoring"])
        st.info(f"Belum ada jam dengan statistik T² MEWMA. T² dihitung untuk data sejak {a:%d %b %Y} dengan tekanan "
                f"semua titik dan data {max(store.model['lag'])} jam sebelumnya lengkap.", icon=":material/info:")
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
