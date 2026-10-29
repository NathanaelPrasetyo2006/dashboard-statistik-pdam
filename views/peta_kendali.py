import pandas as pd
import streamlit as st

from pdam import analysis as an
from pdam import charts, storage, ui
from pdam.config import KALIMAT_BATASAN, TITIK

store = storage.muat_store()
ui.kepala("Peta Kendali MEWMA", store,
          "Statistik T² MEWMA dari residual VARX dibandingkan dengan batas hasil kalibrasi Model A. "
          "**Klik sebuah titik** pada grafik untuk melihat tekanan kelima sensor pada waktu yang sama.")
ui.wajib_data(store)

awal, akhir = ui.rentang(store)
mon = an.potong(store.monitoring, awal, akhir).reset_index(drop=True)
if mon.empty:
    st.info("Tidak ada data monitoring pada rentang tanggal ini.")
    st.stop()
eps = an.episode_dalam_rentang(store, awal, akhir)
ucl = store.ucl
pilihan_waktu = list(mon["Datetime"])

# Ambil klik terbaru dari state grafik sebelum grafik digambar ulang, agar penanda langsung sesuai.
sel = st.session_state.get("pk_chart")
titik_klik = (sel or {}).get("selection", {}).get("points", []) if sel else []
if titik_klik:
    waktu_klik = pd.Timestamp(titik_klik[0]["x"])
    if waktu_klik != st.session_state.get("pk_klik_terakhir"):
        st.session_state["pk_klik_terakhir"] = waktu_klik
        if waktu_klik in pilihan_waktu:
            st.session_state["pk_waktu"] = waktu_klik
if st.session_state.get("pk_waktu") not in pilihan_waktu:
    st.session_state["pk_waktu"] = mon.loc[mon["T2_MEWMA"].idxmax(), "Datetime"]

st.plotly_chart(charts.peta_kendali(mon, ucl, eps, st.session_state["pk_waktu"], tinggi=430),
                key="pk_chart", on_select="rerun", selection_mode="points")
st.caption(f"Garis putus-putus = UCL {an.fmt_angka(ucl, 4)}, batas hasil kalibrasi Model A (bukan ambang keselamatan tekanan). "
           "Titik merah = kandidat OOC; arsiran = rentang episode.")

st.selectbox("Waktu terpilih (atau klik grafik)", pilihan_waktu, key="pk_waktu",
             format_func=lambda t: an.fmt_waktu(t) + ("  • sinyal" if t in set(mon.loc[mon["Sinyal"], "Datetime"]) else ""))
baris = mon[mon["Datetime"] == st.session_state["pk_waktu"]].iloc[0]

kiri, kanan = st.columns([1, 1.3])
with kiri, st.container(border=True):
    t2 = float(baris["T2_MEWMA"])
    st.markdown(f"#### {an.fmt_waktu(baris['Datetime'])}")
    m1, m2 = st.columns(2)
    m1.metric("T² MEWMA", an.fmt_angka(t2, 3))
    m2.metric("Selisih dari UCL", an.fmt_angka(t2 - ucl, 3))
    kalimat, tindak = an.interpretasi_t2(t2, ucl)
    (st.error if baris["Sinyal"] else st.success)(kalimat)
    st.markdown(f"**Tindak lanjut:** {tindak}")
    st.caption(KALIMAT_BATASAN)
    if pd.notna(baris["Episode"]):
        if st.button(f"Buka episode {int(baris['Episode'])}", icon=":material/fact_check:", type="primary"):
            st.session_state["episode_terpilih"] = int(baris["Episode"])
            st.switch_page("views/episode.py")

with kanan:
    st.markdown("**Tekanan lima titik pada waktu yang sama**")
    tek = store.tekanan[store.tekanan["Datetime"] == baris["Datetime"]]
    if tek.empty:
        st.info("Data tekanan untuk waktu ini tidak tersedia.")
    else:
        profil = an.profil_phase1(store)
        tabel = pd.concat([an.deviasi(tek, profil, t).assign(Titik=t) for t in TITIK])
        tabel = tabel[["Titik", "Tekanan", "Rata_rata", "Selisih", "Z"]].rename(
            columns={"Rata_rata": "Profil jam ini (Phase I)", "Z": "Selisih (SD)"})
        st.dataframe(tabel, hide_index=True, column_config={
            c: st.column_config.NumberColumn(format="%.3f") for c in ["Tekanan", "Profil jam ini (Phase I)", "Selisih"]
        } | {"Selisih (SD)": st.column_config.NumberColumn(format="%.2f")})
        st.caption(f"Satuan: {ui.satuan(store)}. Selisih (SD) bersifat deskriptif terhadap profil jam yang sama, bukan batas kendali.")
    jendela = store.tekanan[(store.tekanan["Datetime"] - baris["Datetime"]).abs() <= pd.Timedelta(hours=6)]
    if not jendela.empty:
        st.plotly_chart(charts.lima_tekanan(jendela, penanda=baris["Datetime"], satuan=ui.satuan(store), tinggi=280),
                        key="pk_jendela")
        st.caption("±6 jam di sekitar waktu terpilih; garis titik-titik = waktu terpilih.")

with st.expander("Tabel data monitoring"):
    st.dataframe(mon, hide_index=True, column_config={
        "Datetime": st.column_config.DatetimeColumn(format="DD MMM YYYY HH:mm"),
        "T2_MEWMA": st.column_config.NumberColumn(format="%.4f"),
    })
    st.download_button("Unduh CSV", mon.to_csv(index=False).encode("utf-8"), "mewma_monitoring_terfilter.csv",
                       "text/csv", icon=":material/download:")
