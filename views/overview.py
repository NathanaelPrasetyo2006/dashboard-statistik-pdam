import plotly.graph_objects as go
import streamlit as st

from pdam import analysis as an
from pdam import charts, storage, ui
from pdam.config import KALIMAT_BATASAN, TITIK, WARNA_SINYAL

store = storage.muat_store()
ui.kepala("Overview", store)
ui.wajib_data(store)

awal, akhir = ui.rentang(store)
mon = an.potong(store.monitoring, awal, akhir)
eps = an.episode_dalam_rentang(store, awal, akhir)
n_obs, n_sinyal = len(mon), int(mon["Sinyal"].sum())
proporsi = n_sinyal / n_obs * 100 if n_obs else 0

k1, k2, k3, k4 = st.columns(4)
k1.metric("Kandidat OOC", n_sinyal, border=True,
          help="Jumlah jam dengan T² MEWMA > UCL. 'Kandidat' karena belum diverifikasi di lapangan.")
k2.metric("Episode", len(eps), border=True,
          help="Rangkaian jam bersinyal yang berurutan dihitung sebagai satu episode.")
k3.metric("Proporsi sinyal", f"{an.fmt_angka(proporsi)}%", border=True,
          help=f"{n_sinyal} dari {n_obs} jam pengamatan. Ini proporsi kandidat sinyal, bukan estimasi tingkat kebocoran.")
k4.metric("Titik dipantau", len(TITIK), border=True, help=", ".join(TITIK))

kiri, kanan = st.columns([2.2, 1])
with kiri:
    st.subheader(f"Peta kendali MEWMA ({n_obs} titik waktu)")
    if mon.empty:
        st.info("Tidak ada data monitoring pada rentang tanggal ini.")
    else:
        st.plotly_chart(charts.peta_kendali(mon, store.ucl, eps, tinggi=360), key="ov_chart")
with kanan:
    with st.container(border=True):
        st.subheader("Interpretasi ringkas")
        st.markdown(an.narasi_overview(eps, awal, akhir))
        st.caption(f"{n_sinyal}/{n_obs} = {an.fmt_angka(proporsi)}% adalah proporsi kandidat sinyal, "
                   f"bukan estimasi tingkat kebocoran. {KALIMAT_BATASAN}")
        if st.button("Lihat episode", icon=":material/arrow_forward:", type="primary", width="stretch"):
            st.switch_page("views/episode.py")
        belum = int((~eps["Status"].isin(["Terkonfirmasi", "Tidak terkonfirmasi"])).sum()) if not eps.empty else 0
        if belum:
            st.markdown(f"**{belum}** episode belum selesai diverifikasi.")

tek = an.potong(store.tekanan, awal, akhir)
belum_model = int((tek["Status_Model"] == "Belum diproses").sum()) if not tek.empty else 0
if belum_model:
    st.info(f"{belum_model} jam data tekanan pada rentang ini belum memiliki statistik T² MEWMA "
            "(diimpor sebagai tekanan mentah). Data tersebut tampil di Monitoring Tekanan dan Analisis Jaringan, "
            "tetapi tidak masuk peta kendali sampai hasil modelnya diimpor.", icon=":material/info:")

st.subheader("Perkembangan antarperiode")
c1, c2 = st.columns([1.4, 1])
with c1:
    harian = mon.assign(Tanggal=mon["Datetime"].dt.normalize()).groupby("Tanggal")["Sinyal"].sum().reset_index()
    fig = go.Figure(go.Bar(x=harian["Tanggal"], y=harian["Sinyal"], marker=dict(color=WARNA_SINYAL, cornerradius=4),
                           hovertemplate="%{x|%d %b %Y}: %{y} jam sinyal<extra></extra>"))
    fig.update_layout(height=260, margin=dict(l=10, r=10, t=30, b=10), title=dict(text="Jam bersinyal per hari", font_size=14))
    st.plotly_chart(fig, key="ov_harian")
with c2:
    ringkas = (mon.groupby("Batch", sort=False)
               .agg(Mulai=("Datetime", "min"), Selesai=("Datetime", "max"), Jam=("Datetime", "count"),
                    Sinyal=("Sinyal", "sum"), Episode=("Episode", "nunique"))
               .reset_index())
    ringkas["Proporsi (%)"] = (ringkas["Sinyal"] / ringkas["Jam"] * 100).round(2)
    st.markdown("**Ringkasan per periode import**")
    st.dataframe(ringkas, hide_index=True, column_config={
        "Mulai": st.column_config.DatetimeColumn(format="DD MMM YYYY HH:mm"),
        "Selesai": st.column_config.DatetimeColumn(format="DD MMM YYYY HH:mm"),
    })
    st.caption("Setiap import menjadi satu periode. Episode yang melintasi batas dua periode terhitung di keduanya.")
