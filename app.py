"""Dashboard Monitoring Tekanan Jaringan PDAM (VARX–MEWMA).

Jalankan:  streamlit run app.py
"""
import streamlit as st

from pdam import jaringan as jr
from pdam import ui

st.set_page_config(page_title="Dashboard Tekanan PDAM", page_icon=":material/water_drop:", layout="wide")


halaman = {
    "Dashboard": [
        st.Page("views/overview.py", title="01 Overview", icon=":material/dashboard:", default=True),
        st.Page("views/tekanan.py", title="02 Monitoring Tekanan", icon=":material/speed:"),
        st.Page("views/peta_kendali.py", title="03 Peta Kendali MEWMA", icon=":material/monitoring:"),
        st.Page("views/episode.py", title="04 Investigasi Episode", icon=":material/fact_check:"),
        st.Page("views/jaringan.py", title="05 Analisis Jaringan", icon=":material/hub:"),
        st.Page("views/validasi.py", title="06 Validasi Model", icon=":material/verified:"),
    ],
    "Data": [
        st.Page("views/kelola_data.py", title="Kelola Data & Import", icon=":material/database:"),
    ],
}
nav = st.navigation(halaman)

with st.sidebar:
    daftar = jr.daftar()
    ui.terapkan_pilihan_tertunda()
    st.session_state[ui.KUNCI_JARINGAN] = ui.jaringan_aktif()
    st.selectbox("Jaringan", [j.id for j in daftar], key=ui.KUNCI_JARINGAN, on_change=ui.reset_pilihan,
                 format_func={j.id: f"{j.nama} ({len(j.titik)} titik)" for j in daftar}.get,
                 help="Semua halaman menampilkan data jaringan ini. Tambah jaringan di Kelola Data → Jaringan & model.")
    store = ui.muat()
    if not store.kosong:
        tmin, tmax = store.tekanan["Datetime"].min().date(), store.tekanan["Datetime"].max().date()
        nilai = st.session_state.get(ui.KUNCI_RENTANG)
        if not (isinstance(nilai, (list, tuple)) and len(nilai) in (1, 2) and tmin <= nilai[0] <= nilai[-1] <= tmax):
            st.session_state[ui.KUNCI_RENTANG] = (tmin, tmax)
        st.date_input("Rentang tanggal", min_value=tmin, max_value=tmax, key=ui.KUNCI_RENTANG,
                      format="DD/MM/YYYY", help="Berlaku untuk semua halaman. Filter tidak mengubah data sumber.")
        # Lewat callback: state widget hanya boleh diubah sebelum widget digambar.
        st.button("Tampilkan semua data", icon=":material/restart_alt:", width="stretch",
                  on_click=lambda: st.session_state.update({ui.KUNCI_RENTANG: (tmin, tmax)}))
        st.caption(f"Data tersedia {tmin:%d %b %Y} – {tmax:%d %b %Y}")
    ui.form_login()
    st.divider()
    st.caption("Data historis per jam, bukan realtime. Sinyal MEWMA adalah kandidat penyimpangan statistik, "
               "bukan bukti kebocoran.")

nav.run()
