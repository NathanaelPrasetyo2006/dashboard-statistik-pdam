import pandas as pd
import streamlit as st

from pdam import analysis as an
from pdam import storage, ui

store = storage.muat_store()
ui.kepala("Validasi Model", store, "Parameter, kinerja, dan keterbatasan Model A untuk peneliti.")
ui.wajib_data(store)

meta = store.metadata
ci = meta["arl0_ci95"]


def periode(fase):
    a, b = an.periode_phase(store, fase)
    return f"{a:%d %b} – {b:%d %b %Y}"


def kartu(kolom, judul, isi, peringatan=False):
    with kolom.container(border=True):
        st.markdown(f"**{judul}**")
        (st.warning if peringatan else st.markdown)(isi)


interpolasi = "; ".join(f"{pd.Timestamp(i['Datetime']):%d %b %H.%M} {i['Titik']}" for i in meta["interpolasi_phase_i"])
c1, c2 = st.columns(2)
kartu(c1, "Model", f"{meta['nama_model']}  \n{meta['struktur_model']}  \n"
                   f"Lag {', '.join(map(str, meta['lag']))} jam; Fourier harian k = {', '.join(map(str, meta['fourier_k']))}")
kartu(c2, "Parameter", f"λ = {an.fmt_angka(meta['lambda_mewma'], 1)}; UCL = {an.fmt_angka(store.ucl, 4)}  \n"
                       f"UCL dikalibrasi untuk ARL₀ = {meta['target_arl0']} dengan bootstrap blok "
                       f"{meta['bootstrap_blok_jam']} jam")
kartu(c1, "Kinerja", f"ARL₀ validasi = {an.fmt_angka(meta['arl0_validasi'])} (target {meta['target_arl0']})  \n"
                     f"CI 95% = {an.fmt_angka(ci[0])} – {an.fmt_angka(ci[1])} "
                     f"({meta['bootstrap_replikasi']} replikasi bootstrap)")
kartu(c2, "Stabilitas baseline", f"Uji rata-rata p = {an.fmt_angka(meta['baseline_p_rata_rata'], 5)}; "
                                 f"uji kovarians p = {an.fmt_angka(meta['baseline_p_kovarians'], 5)}")
kartu(c1, "Periode", f"Phase I (estimasi model): {periode('i')}  \nPhase II (monitoring awal): {periode('ii')}  \n"
                     f"Interval: {meta['interval_pengamatan']}; {meta['n_residual_phase_i']} residual Phase I")
kartu(c2, "Data khusus", f"Interpolasi {len(meta['interpolasi_phase_i'])} nilai: {interpolasi}.  \n"
                         "9 Juli 12.00 adalah pengamatan ekstrem pada Phase I.", peringatan=True)
kartu(c1, "Peringatan", "Residual Paldam masih berautokorelasi.", peringatan=True)
kartu(c2, "Interpretasi", "Sinyal menunjukkan penyimpangan statistik multivariat terhadap pola Phase I, "
                          "bukan bukti kebocoran.")
st.caption("P-value berasal dari uji bootstrap eksploratif; validasi ARL bersyarat pada residual baseline, "
           "bukan validasi eksternal. Angka kinerja dan stabilitas berasal dari notebook Colab dan tidak dihitung "
           "ulang di dashboard.")

st.subheader("Uji penerimaan (kecocokan dengan hasil Colab)")
uji = pd.DataFrame(an.uji_penerimaan(store))
lulus = int(uji["Lulus"].sum())
(st.success if lulus == len(uji) else st.warning)(
    f"{lulus} dari {len(uji)} kriteria lulus untuk Phase II ({periode('ii')}).")
uji["Lulus"] = uji["Lulus"].map({True: "✓ Lulus", False: "✗ Tidak"})
st.dataframe(uji.astype({"Acuan": str, "Hasil": str}), hide_index=True)
st.caption("Dashboard menghitung ulang T² dari data tekanan dengan parameter model yang dibekukan; uji ini memastikan "
           "hasilnya sama dengan notebook Colab. Uji selalu memakai Phase II sehingga tidak terpengaruh filter "
           "tanggal maupun data periode baru.")

st.subheader("Batasan yang wajib dibaca")
ui.batasan("Kandidat OOC ≠ kebocoran terkonfirmasi.",
           "ARL = hasil validasi bootstrap bersyarat.",
           "Paldam masih memiliki autokorelasi residual.",
           "9 Juli 12.00 adalah pengamatan ekstrem pada Phase I.",
           "Model tidak diestimasi ulang untuk periode baru; perubahan pola operasi jangka panjang dapat "
           "menaikkan jumlah sinyal.",
           "Data bersifat historis per jam, bukan realtime.")

with st.expander("Parameter model (model_A.json)"):
    st.json({k: v for k, v in meta.items()})
