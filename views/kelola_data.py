from datetime import datetime

import pandas as pd
import streamlit as st

from pdam import analysis as an
from pdam import charts, storage, ui

store = storage.muat_store()
st.title("Kelola Data & Import")
st.markdown("Import data tekanan per jam untuk periode baru. Data baru **digabung dengan data sebelumnya**, lalu "
            "statistik T² MEWMA, sinyal, episode, dan kontribusi titik dihitung otomatis dengan Model A yang "
            "sudah dibekukan (UCL dan parameter model tidak berubah).")

if not store.kosong:
    m, t = store.monitoring, store.tekanan
    a, b, c = st.columns(3)
    a.metric("Jam data tekanan", len(t), border=True)
    b.metric("Jam dengan T² MEWMA", len(m), border=True)
    c.metric("Periode tersimpan", f"{t['Datetime'].min():%d %b %Y} – {t['Datetime'].max():%d %b %Y}", border=True)

tab_import, tab_riwayat, tab_backup = st.tabs(["Import data tekanan", "Riwayat import", "Backup & reset"])


def tampilkan_pesan(galat, peringatan, info=()):
    for g in galat:
        st.error(g, icon=":material/block:")
    for p in peringatan:
        st.warning(p, icon=":material/warning:")
    for i in info:
        st.info(i, icon=":material/info:")


with tab_import:
    st.download_button("Unduh template Excel", storage.template_tekanan(), "template_tekanan.xlsx",
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", icon=":material/download:")
    st.caption("Format sama dengan file data PDAM: judul dua baris (`Tanggal` | `Tekanan`, lalu `Jam` dan lima titik: "
               "IPA KM 8, Bangun Reksa, Simpang Prumnas, Ojek Maxi, Paldam), satu baris per jam. "
               "Tanggal boleh hanya diisi di jam pertama (sel gabungan). File CSV atau Excel dengan kolom "
               "`Datetime` + lima titik juga diterima.")
    if ui.kunci_admin():
        f = st.file_uploader("File tekanan", type=["xlsx", "xls", "csv"], key="up_tekanan")
        if f:
            df, pesan = storage.baca_tekanan(f)
            info = []
            mon_baru = pd.DataFrame(columns=["Datetime", "T2_MEWMA", "UCL", "Sinyal"])
            if df is not None and not df.empty:
                ada = int(df["Datetime"].isin(set(store.tekanan["Datetime"])).sum())
                if ada:
                    pesan["peringatan"].append(f"{ada} jam sudah ada di data tersimpan dan akan diganti dengan nilai dari file ini.")
                if not store.kosong:
                    akhir_lama = store.tekanan["Datetime"].max()
                    awal_baru = df["Datetime"].min()
                    if awal_baru > akhir_lama + pd.Timedelta(hours=1):
                        jeda = (awal_baru - akhir_lama) / pd.Timedelta(hours=1)
                        info.append(f"Ada jeda {jeda:.0f} jam antara data tersimpan (s.d. {akhir_lama:%d %b %Y %H:%M}) "
                                    f"dan file ini (mulai {awal_baru:%d %b %Y %H:%M}). 24 jam pertama setelah jeda "
                                    "tidak memiliki T² karena model memerlukan tekanan 24 jam sebelumnya.")
                mon_baru = storage.pratinjau_import(df, store)
                tanpa = len(df) - len(mon_baru)
                st.markdown(f"**Pratinjau:** {len(df)} jam, {df['Datetime'].min():%d %b %Y %H:%M} – "
                            f"{df['Datetime'].max():%d %b %Y %H:%M}. Setelah disimpan: **{len(mon_baru)}** jam memiliki T², "
                            f"**{int(mon_baru['Sinyal'].sum())}** di antaranya kandidat OOC (T² > UCL {an.fmt_angka(store.ucl, 4)}).")
                if tanpa:
                    st.caption(f"{tanpa} jam tidak memiliki T²: jam pada Phase I (periode referensi model) atau jam "
                               "dengan tekanan/lag 24 jam yang tidak lengkap.")
                if not mon_baru.empty:
                    st.plotly_chart(charts.peta_kendali(mon_baru.assign(Episode=storage.hitung_episode(mon_baru)),
                                                        store.ucl, tinggi=260), key="up_preview")
                with st.expander("Lihat data yang terbaca"):
                    st.dataframe(df, hide_index=True, height=240, column_config={
                        "Datetime": st.column_config.DatetimeColumn(format="DD MMM YYYY HH:mm")})
            elif df is not None:
                pesan["galat"].append("File tidak berisi baris data.")
            tampilkan_pesan(pesan["galat"], pesan["peringatan"], info)
            nama_default = f"{df['Datetime'].min():%b %Y}" if df is not None and not df.empty else "Periode baru"
            batch = st.text_input("Nama periode", value=nama_default, key="up_batch",
                                  help="Label untuk membedakan periode di ringkasan Overview.")
            if st.button("Simpan ke dashboard", type="primary", disabled=df is None or bool(pesan["galat"]),
                         icon=":material/save:"):
                storage.simpan_tekanan(df, batch.strip() or nama_default, f.name, mon_baru)
                st.toast("Data tersimpan. Semua halaman sekarang memakai data gabungan.")
                st.session_state.pop(ui.KUNCI_RENTANG, None)
                st.rerun()
    with st.expander("Bagaimana data diproses?"):
        a1, b1 = store.metadata["periode_phase_i"]
        a2, _ = store.metadata["periode_phase_ii"]
        st.markdown(
            f"1. Parameter Model A (koefisien VARX + Fourier, rata-rata dan kovarians MEWMA, UCL "
            f"{an.fmt_angka(store.ucl, 4)}, λ = {an.fmt_angka(store.metadata['lambda_mewma'], 1)}) diestimasi "
            f"sekali dari Phase I ({pd.Timestamp(a1):%d %b} – {pd.Timestamp(b1):%d %b %Y}) dan tidak berubah saat import.\n"
            "2. Nilai kosong yang hanya 1 jam diisi interpolasi waktu, sama seperti di notebook Colab.\n"
            f"3. T² MEWMA dihitung untuk setiap jam sejak {pd.Timestamp(a2):%d %b %Y} yang memiliki lima tekanan dan "
            "data 24 jam sebelumnya lengkap. Statistik MEWMA berlanjut dari jam terakhir data sebelumnya.\n"
            "4. Mengimpor ulang jam yang sudah ada mengganti nilai lama; seluruh statistik dihitung ulang.")

with tab_riwayat:
    if store.riwayat:
        st.dataframe(pd.DataFrame(store.riwayat).iloc[::-1], hide_index=True)
    else:
        st.info("Belum ada import.")

with tab_backup:
    st.markdown("Unduh backup secara berkala, terutama bila dashboard dijalankan di Streamlit Community Cloud: "
                "penyimpanan di sana **bisa terhapus** saat aplikasi dimulai ulang. Backup berisi data tekanan, "
                "catatan verifikasi, dan riwayat import.")
    st.download_button("Unduh backup (ZIP)", storage.buat_backup(),
                       f"backup_dashboard_pdam_{datetime.now():%Y%m%d_%H%M}.zip", "application/zip",
                       icon=":material/backup:", disabled=not storage.ada_data())
    if ui.kunci_admin():
        st.divider()
        pulih = st.file_uploader("Pulihkan dari backup", type=["zip"], key="up_backup")
        if pulih and st.button("Pulihkan (data saat ini diganti)", icon=":material/settings_backup_restore:"):
            try:
                nama = storage.pulihkan_backup(pulih.getvalue())
                st.session_state.pop(ui.KUNCI_RENTANG, None)
                st.toast("Dipulihkan: " + ", ".join(nama))
                st.rerun()
            except ValueError as e:
                st.error(str(e))
        st.divider()
        yakin = st.checkbox("Saya mengerti semua data dan catatan verifikasi akan dihapus.", key="yakin_hapus")
        if st.button("Hapus semua data", disabled=not yakin, icon=":material/delete_forever:"):
            storage.hapus_semua()
            st.session_state.pop(ui.KUNCI_RENTANG, None)
            st.rerun()
