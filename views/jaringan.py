import numpy as np
import streamlit as st

from pdam import analysis as an
from pdam import charts, storage, ui
from pdam.config import TITIK

store = storage.muat_store()
ui.kepala("Analisis Jaringan", store, "Hubungan statistik antartitik tekanan pada rentang tanggal terpilih.")
ui.wajib_data(store, butuh_model=False)

awal, akhir = ui.rentang(store)
tek = an.potong(store.tekanan, awal, akhir).dropna(subset=TITIK)
if len(tek) < 3:
    st.info("Data tekanan pada rentang ini terlalu sedikit untuk menghitung korelasi.")
    st.stop()

metode = st.segmented_control("Metode korelasi", ["pearson", "spearman"], default="pearson", required=True,
                              format_func=str.capitalize, key="jar_metode")
corr = tek[TITIK].corr(method=metode)

kiri, kanan = st.columns([1, 1.2])
with kiri:
    st.markdown(f"**Heatmap korelasi 5 × 5** ({len(tek)} jam)")
    st.plotly_chart(charts.korelasi(corr), key="jar_heatmap")
    st.caption("Korelasi tidak menunjukkan arah aliran atau sebab-akibat.")

with kanan:
    segitiga = corr.where(np.triu(np.ones(corr.shape, dtype=bool), k=1)).stack()
    a0, b0 = segitiga.abs().idxmax()
    p1, p2 = st.columns(2)
    a = p1.selectbox("Titik A", TITIK, index=TITIK.index(a0), key="jar_a")
    b = p2.selectbox("Titik B", [t for t in TITIK if t != a],
                     index=[t for t in TITIK if t != a].index(b0) if b0 != a else 0, key="jar_b")
    st.markdown(f"**{a} – {b}**: r = {an.fmt_angka(corr.loc[a, b], 3)}")
    st.plotly_chart(charts.lima_tekanan(tek, [a, b], satuan=ui.satuan(store), tinggi=360), key="jar_pasangan")
    st.caption(f"Pasangan dengan korelasi absolut tertinggi pada rentang ini: {a0} – {b0} "
               f"(r = {an.fmt_angka(corr.loc[a0, b0], 3)}).")

with st.container(border=True):
    st.markdown("**Skema jaringan fisik**")
    st.markdown("Dashboard ini tidak memuat skema jaringan fisik (koordinat, sambungan pipa, arah aliran). "
                "Hubungan antartitik di halaman ini murni statistik dari data tekanan.")
