import pandas as pd
import streamlit as st

from pdam import analysis as an
from pdam import ui

store = ui.muat()
ui.kepala("Validasi Model", store, "Parameter, kinerja, dan keterbatasan model jaringan ini untuk peneliti.")
ui.wajib_data(store)

m = store.model
val = m.get("validasi", {})
otomatis = m.get("sumber") != "peneliti"
a1, b1 = an.periode_phase_i(store)


def kartu(kolom, judul, isi, peringatan=False):
    with kolom.container(border=True):
        st.markdown(f"**{judul}**")
        (st.warning if peringatan else st.markdown)(isi)


c1, c2 = st.columns(2)
kartu(c1, "Model", f"{m['nama_model']} · {'model otomatis dashboard' if otomatis else 'model peneliti'}  \n"
                   f"{m['struktur_model']}  \nLag {', '.join(map(str, m['lag']))} jam; "
                   f"Fourier harian k = {', '.join(map(str, m['fourier_k']))}; {len(m['titik'])} titik")
kartu(c2, "Parameter", f"λ = {an.fmt_angka(m['lambda_mewma'], 1)}; UCL = {an.fmt_angka(store.ucl, 4)}  \n"
                       + (f"UCL dikalibrasi untuk ARL₀ = {val['target_arl0']} dengan bootstrap blok "
                          f"{val.get('bootstrap_blok_jam', '–')} jam" if val.get("target_arl0") else "UCL dari peneliti"))
if val.get("arl0_validasi") is not None:
    ci = val.get("arl0_ci95") or [None, None]
    kartu(c1, "Kinerja", f"ARL₀ validasi = {an.fmt_angka(val['arl0_validasi'])} (target {val.get('target_arl0', '–')})  \n"
                         f"CI 95% = {an.fmt_angka(ci[0])} – {an.fmt_angka(ci[1])} "
                         f"({val.get('bootstrap_replikasi', '–')} replikasi bootstrap)")
else:
    kartu(c1, "Kinerja", "ARL₀ validasi tidak tercantum di file model.")
if val.get("baseline_p_rata_rata") is not None:
    kartu(c2, "Stabilitas baseline", f"Uji rata-rata p = {an.fmt_angka(val['baseline_p_rata_rata'], 5)}; "
                                     f"uji kovarians p = {an.fmt_angka(val.get('baseline_p_kovarians'), 5)}")
else:
    kartu(c2, "Stabilitas baseline", "Belum diuji. Uji stabilitas rata-rata dan kovarians Phase I dilakukan peneliti.",
          peringatan=otomatis)
kartu(c1, "Periode", f"Phase I (estimasi model): {a1:%d %b} – {b1:%d %b %Y}  \n"
                     f"Monitoring mulai: {pd.Timestamp(m['mulai_monitoring']):%d %b %Y}  \n"
                     f"Interval 1 jam; {m.get('n_residual_phase_i', '–')} residual Phase I")
interp = m.get("interpolasi_phase_i", [])
kartu(c2, "Data khusus Phase I",
      (f"Interpolasi {len(interp)} nilai: "
       + "; ".join(f"{pd.Timestamp(i['Datetime']):%d %b %H.%M} {i['Titik']}" for i in interp) + ".")
      if interp else "Tidak ada nilai yang diinterpolasi.", peringatan=bool(interp))
catatan = m.get("catatan", [])
if catatan:
    kartu(c1, "Catatan", "  \n".join(catatan), peringatan=True)
kartu(c2, "Interpretasi", "Sinyal menunjukkan penyimpangan statistik multivariat terhadap pola Phase I, "
                          "bukan bukti kebocoran.")
st.caption("P-value berasal dari uji bootstrap eksploratif; validasi ARL bersyarat pada residual baseline, "
           "bukan validasi eksternal."
           + (" ARL₀ model otomatis dihitung dashboard dengan bootstrap blok yang sama seperti notebook Colab."
              if otomatis else " Angka kinerja berasal dari peneliti dan tidak dihitung ulang di dashboard."))

uji = an.uji_penerimaan(store)
if uji is not None:
    acuan = m["acuan_uji"]
    st.subheader("Uji penerimaan (kecocokan dengan hasil peneliti)")
    uji = pd.DataFrame(uji)
    lulus = int(uji["Lulus"].sum())
    (st.success if lulus == len(uji) else st.warning)(
        f"{lulus} dari {len(uji)} kriteria lulus untuk periode {pd.Timestamp(acuan['periode'][0]):%d %b} – "
        f"{pd.Timestamp(acuan['periode'][1]):%d %b %Y}.")
    uji["Lulus"] = uji["Lulus"].map({True: "✓ Lulus", False: "✗ Tidak"})
    st.dataframe(uji.astype({"Acuan": str, "Hasil": str}), hide_index=True)
    st.caption("Dashboard menghitung T² dari data tekanan dengan parameter model yang dibekukan; uji ini memastikan "
               "hasilnya sama dengan hasil peneliti. Periode uji tetap sehingga tidak terpengaruh filter tanggal "
               "maupun data periode baru.")

st.subheader("Batasan yang wajib dibaca")
ui.batasan("Kandidat OOC ≠ kebocoran terkonfirmasi.",
           "ARL = hasil validasi bootstrap bersyarat.",
           *catatan,
           *(["Model otomatis belum melalui pemilihan lag dan diagnostik residual oleh peneliti."] if otomatis else []),
           "Model tidak diestimasi ulang untuk periode baru; perubahan pola operasi jangka panjang dapat "
           "menaikkan jumlah sinyal.",
           "Data bersifat historis per jam, bukan realtime.")

with st.expander("Parameter model (file JSON)"):
    st.json(store.metadata)
