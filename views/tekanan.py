import pandas as pd
import streamlit as st

from pdam import analysis as an
from pdam import charts, storage, ui
from pdam.config import TITIK

store = storage.muat_store()
ui.kepala("Monitoring Tekanan", store,
          "Tekanan aktual tiap titik dibandingkan dengan profil rata-rata per jam pada periode referensi (Phase I).")
ui.wajib_data(store, butuh_model=False)

awal, akhir = ui.rentang(store)
tek = an.potong(store.tekanan, awal, akhir)
if tek.empty:
    st.info("Tidak ada data tekanan pada rentang tanggal ini.")
    st.stop()
profil = an.profil_phase1(store)
waktu_sinyal = set(store.monitoring.loc[store.monitoring["Sinyal"], "Datetime"])

f1, f2 = st.columns([1, 2])
titik = f1.selectbox("Titik tekanan", TITIK, key="tek_titik")
jam = f2.slider("Jam dalam sehari", 0, 23, (0, 23), key="tek_jam")

dev = an.deviasi(tek, profil, titik)
dev = dev[dev["Jam"].between(*jam)]

tab1, tab2 = st.tabs(["Per titik", "Lima titik sekaligus"])
with tab1:
    kiri, kanan = st.columns([2.2, 1])
    with kiri:
        st.plotly_chart(charts.tekanan_vs_profil(dev, titik, waktu_sinyal, ui.satuan(store)), key="tek_chart")
    with kanan, st.container(border=True):
        st.subheader("Interpretasi")
        d = dev.dropna(subset=["Selisih"])
        if d.empty:
            st.markdown("Belum dapat dibandingkan dengan profil Phase I.")
        else:
            rata = d["Selisih"].mean()
            arah = "lebih tinggi" if rata > 0 else "lebih rendah"
            st.markdown(f"Pada rentang terpilih, tekanan **{titik}** rata-rata **{arah}** "
                        f"{an.fmt_angka(abs(rata), 3)} dari rerata historis pada jam yang sama.")
            puncak = d.loc[d["Selisih"].abs().idxmax()]
            st.markdown(f"Selisih terbesar: **{an.fmt_angka(puncak['Selisih'], 3)}** pada "
                        f"**{an.fmt_waktu(puncak['Datetime'])}** (≈ {an.fmt_angka(puncak['Z'], 1)} SD dari profil jam itu).")
            z = an.z_semua_titik(tek[tek["Datetime"] == puncak["Datetime"]], profil)
            lain = [t for t in TITIK if t != titik and abs(z[t].iloc[0]) >= 2]
            st.markdown("Pada waktu yang sama, titik lain yang juga menyimpang ≥ 2 SD: "
                        + (", ".join(f"**{t}**" for t in lain) if lain else "tidak ada") + ".")
            if puncak["Datetime"] in waktu_sinyal:
                st.markdown("Waktu tersebut juga merupakan waktu sinyal MEWMA jaringan.")
            n_ekstrem = int((d["Z"].abs() >= 3).sum())
            if n_ekstrem:
                st.warning(f"{n_ekstrem} jam tekanan berbeda tajam (≥ 3 SD) dari profil jam serupa. "
                           "Tindak lanjut: cek sensor, pompa, katup, dan log operasional.", icon=":material/warning:")
        ui.batasan("Pita ± SD bersifat deskriptif, bukan batas kendali.",
                   "Selisih dari profil tidak otomatis berarti gangguan.")

with tab2:
    pilih = st.multiselect("Titik ditampilkan", TITIK, default=TITIK, key="tek_multi")
    tek_jam = tek[tek["Datetime"].dt.hour.between(*jam)]
    eps = an.episode_dalam_rentang(store, awal, akhir)
    st.plotly_chart(charts.lima_tekanan(tek_jam, pilih, eps, satuan=ui.satuan(store)), key="tek_lima")
    st.caption("Arsiran merah muda = rentang episode sinyal MEWMA.")

with st.expander("Tabel data tekanan"):
    st.dataframe(tek, hide_index=True, column_config={
        "Datetime": st.column_config.DatetimeColumn(format="DD MMM YYYY HH:mm"),
        "Status_Model": st.column_config.TextColumn(
            "Status model", help="Referensi Phase I = periode estimasi model (tanpa T²). "
                                 "Tanpa T² = tekanan atau data 24 jam sebelumnya tidak lengkap."),
    })
    st.download_button("Unduh CSV", tek.drop(columns="Status_Model").to_csv(index=False).encode("utf-8"),
                       f"tekanan_{pd.Timestamp(awal):%Y%m%d}_{pd.Timestamp(akhir):%Y%m%d}.csv", "text/csv",
                       icon=":material/download:")
