import pandas as pd
import streamlit as st

from pdam import analysis as an
from pdam import storage, ui
from pdam.config import INFO_MODEL_BRIEF

store = storage.muat_store()
ui.kepala("Validasi Model", store, "Parameter, kinerja, dan keterbatasan Model A untuk peneliti.")
ui.wajib_data(store)

meta = {**INFO_MODEL_BRIEF, **store.metadata}
ci = meta.get("arl0_ci95") or [None, None]


def kartu(kolom, judul, isi, peringatan=False):
    with kolom.container(border=True):
        st.markdown(f"**{judul}**")
        (st.warning if peringatan else st.markdown)(isi)


c1, c2 = st.columns(2)
kartu(c1, "Model", f"{meta.get('nama_model', '-')}  \n{meta['struktur_model']}")
kartu(c2, "Parameter", f"λ = {an.fmt_angka(meta.get('lambda_mewma'), 1)}; UCL = {an.fmt_angka(store.ucl, 4)}  \n"
                       f"UCL dikalibrasi dengan bootstrap blok {meta.get('bootstrap_blok_jam', '-')} jam")
kartu(c1, "Kinerja", f"ARL₀ validasi = {an.fmt_angka(meta.get('arl0_validasi'))} (target {meta.get('target_arl0', '-')})  \n"
                     f"CI 95% = {an.fmt_angka(ci[0])} – {an.fmt_angka(ci[1])}")
kartu(c2, "Baseline", f"Rata-rata p = {an.fmt_angka(meta['baseline_p_rata_rata'], 5)}; "
                      f"kovarians p = {an.fmt_angka(meta['baseline_p_kovarians'], 5)}")
kartu(c1, "Periode", f"Phase I: {meta.get('periode_phase_i', '-')}  \nPhase II: {meta.get('periode_phase_ii', '-')}  \n"
                     f"Interval: {meta.get('interval_pengamatan', '-')}")
kartu(c2, "Data khusus", meta["data_khusus"], peringatan=True)
kartu(c1, "Peringatan", meta.get("catatan", "Residual Paldam masih berautokorelasi."), peringatan=True)
kartu(c2, "Interpretasi", meta.get("interpretasi", "-"))
st.caption("P-value berasal dari uji bootstrap eksploratif; validasi ARL bersyarat pada residual baseline, bukan validasi eksternal.")

st.subheader("Uji penerimaan (kecocokan dengan hasil Colab)")
uji = pd.DataFrame(an.uji_penerimaan(store))
lulus = int(uji["Lulus"].sum())
(st.success if lulus == len(uji) else st.warning)(
    f"{lulus} dari {len(uji)} kriteria lulus untuk periode Phase II Model A (21–31 Juli 2026).")
uji["Lulus"] = uji["Lulus"].map({True: "✓ Lulus", False: "✗ Tidak"})
st.dataframe(uji.astype({"Acuan": str, "Hasil": str}), hide_index=True)
st.caption("Uji ini selalu memakai periode Phase II Juli 2026 sehingga tidak terpengaruh filter tanggal maupun data periode baru.")

st.subheader("Batasan yang wajib dibaca")
ui.batasan("Kandidat OOC ≠ kebocoran terkonfirmasi.",
           "ARL = hasil validasi bootstrap bersyarat.",
           "Paldam masih memiliki autokorelasi residual.",
           "9 Juli 12.00 adalah pengamatan ekstrem pada Phase I.",
           "Interpolasi 2 nilai harus dapat ditelusuri (lokasinya belum disertakan dalam paket ekspor).",
           "Data bersifat historis per jam, bukan realtime.")

with st.expander("Metadata mentah (metadata_model.json)"):
    st.json(store.metadata)
