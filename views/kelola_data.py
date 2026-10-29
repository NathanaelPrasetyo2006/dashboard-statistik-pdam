from datetime import datetime

import pandas as pd
import streamlit as st

from pdam import analysis as an
from pdam import charts, storage, ui

store = storage.muat_store()
st.title("Kelola Data & Import")
st.markdown("Import data periode baru untuk melanjutkan pemantauan. Data baru **digabung dengan data sebelumnya**, "
            "sehingga statistik, episode, dan grafik di semua halaman langsung mencakup seluruh periode.")

if not store.kosong:
    m = store.monitoring
    a, b, c = st.columns(3)
    a.metric("Jam dengan T² MEWMA", len(m), border=True)
    b.metric("Jam data tekanan", len(store.tekanan), border=True)
    c.metric("Periode tersimpan",
             f"{m['Datetime'].min():%d %b %Y} – {m['Datetime'].max():%d %b %Y}" if not m.empty else "–", border=True)

tab_model, tab_mentah, tab_riwayat, tab_backup = st.tabs(
    ["Import hasil model", "Import tekanan mentah", "Riwayat import", "Backup & reset"])


def tampilkan_pesan(galat, peringatan, info):
    for g in galat:
        st.error(g, icon=":material/block:")
    for p in peringatan:
        st.warning(p, icon=":material/warning:")
    for i in info:
        st.info(i, icon=":material/info:")


with tab_model:
    st.markdown("Unggah **ZIP hasil ekspor Colab** (`dashboard_model_A.zip`) atau file-file di dalamnya: "
                "`mewma_monitoring.csv` (wajib), `tekanan_aktual.csv`, `episode_monitoring.csv`, "
                "`kontribusi_diagnostik.csv`, `metadata_model.json`.")
    if ui.kunci_admin():
        unggah = st.file_uploader("File hasil model", type=["zip", "csv", "json", "xlsx"], accept_multiple_files=True,
                                  key="up_model")
        mode = st.radio("Cara menyimpan", ["tambah", "ganti"], horizontal=True, key="up_mode",
                        format_func={"tambah": "Tambahkan ke data sebelumnya (periode lanjutan)",
                                     "ganti": "Ganti seluruh hasil model"}.get,
                        help="'Ganti' menghapus hasil model lama (monitoring, tekanan, episode, kontribusi, metadata). "
                             "Catatan verifikasi tetap disimpan.")
        if unggah:
            pk = storage.baca_paket(unggah)
            storage.cek_terhadap_store(pk, store, mode)
            if pk.monitoring is not None and not pk.galat:
                mon = pk.monitoring
                st.markdown(f"**Pratinjau:** {len(mon)} jam, {mon['Datetime'].min():%d %b %Y %H:%M} – "
                            f"{mon['Datetime'].max():%d %b %Y %H:%M}, {int(mon['Sinyal'].sum())} sinyal, "
                            f"UCL {an.fmt_angka(mon['UCL'].iloc[0], 4)}. File dikenali: {', '.join(pk.file_dikenali)}.")
                pratinjau = mon.assign(Episode=storage.hitung_episode(mon))
                st.plotly_chart(charts.peta_kendali(pratinjau, float(mon["UCL"].iloc[0]), tinggi=260), key="up_preview")
            tampilkan_pesan(pk.galat, pk.peringatan, pk.info)
            nama_default = (pk.monitoring["Datetime"].min().strftime("%b %Y")
                            if pk.monitoring is not None and not pk.monitoring.empty else "Periode baru")
            batch = st.text_input("Nama periode", value=nama_default, key="up_batch",
                                  help="Label untuk membedakan periode di ringkasan Overview.")
            if st.button("Simpan ke dashboard", type="primary", disabled=bool(pk.galat), icon=":material/save:"):
                storage.simpan_paket(pk, mode, batch.strip() or nama_default)
                st.toast("Data tersimpan. Semua halaman sekarang memakai data gabungan.")
                st.session_state.pop(ui.KUNCI_RENTANG, None)
                st.rerun()
    with st.expander("Bagaimana menyiapkan data periode baru?"):
        st.markdown(
            "1. Peneliti menjalankan **Model A yang sudah dibekukan** (koefisien VARX, Fourier, UCL 22,5640, λ = 0,1) "
            "pada data tekanan periode baru di Google Colab.\n"
            "2. Jalankan sel ekspor. Untuk periode baru, pemeriksaan `(57, 10)` di skrip ekspor harus dilewati karena "
            "jumlah sinyal tentu berbeda; UCL **tidak boleh** diubah.\n"
            "3. Unggah ZIP-nya di sini dengan mode *Tambahkan ke data sebelumnya*. Dashboard menolak paket dengan "
            "UCL atau λ berbeda agar hasil model yang berlainan tidak tercampur.")

with tab_mentah:
    st.markdown("Unggah data tekanan lima titik (CSV/Excel) yang **belum** diproses model. Data ini langsung "
                "tampil di Monitoring Tekanan dan Analisis Jaringan (dibandingkan dengan profil Phase I), "
                "tetapi **tidak** memiliki T² MEWMA sampai hasil modelnya diimpor di tab sebelah.")
    st.download_button("Unduh template CSV", storage.template_tekanan(), "template_tekanan.csv", "text/csv",
                       icon=":material/download:")
    st.caption("Kolom: `Datetime` (atau `Tanggal` + `Jam`) dan lima titik: IPA KM 8, Bangun Reksa, Simpang Prumnas, "
               "Ojek Maxi, Paldam. Pemisah `,` atau `;` dan desimal koma diterima.")
    if ui.kunci_admin():
        f = st.file_uploader("File tekanan", type=["csv", "xlsx", "xls"], key="up_mentah")
        if f:
            df, pesan = storage.baca_tekanan_mentah(f)
            if df is not None:
                ada = df["Datetime"].isin(set(store.tekanan["Datetime"])).sum()
                if ada:
                    pesan["peringatan"].append(f"{int(ada)} waktu sudah ada dan akan diganti dengan nilai dari file ini.")
                st.markdown(f"**Pratinjau:** {len(df)} baris, {df['Datetime'].min():%d %b %Y %H:%M} – "
                            f"{df['Datetime'].max():%d %b %Y %H:%M}.")
                st.dataframe(df.head(48), hide_index=True, height=240)
            tampilkan_pesan(pesan["galat"], pesan["peringatan"], [])
            batch = st.text_input("Nama periode", value=f"Tekanan {datetime.now():%d %b %Y}", key="mentah_batch")
            if st.button("Simpan tekanan", type="primary", disabled=df is None or bool(pesan["galat"]),
                         icon=":material/save:"):
                storage.simpan_tekanan_mentah(df, batch.strip(), f.name)
                st.toast("Data tekanan tersimpan.")
                st.session_state.pop(ui.KUNCI_RENTANG, None)
                st.rerun()

with tab_riwayat:
    if store.riwayat:
        st.dataframe(pd.DataFrame(store.riwayat).iloc[::-1], hide_index=True)
    else:
        st.info("Belum ada import.")

with tab_backup:
    st.markdown("Unduh backup secara berkala, terutama bila dashboard dijalankan di Streamlit Community Cloud: "
                "penyimpanan di sana **bisa terhapus** saat aplikasi dimulai ulang. Backup berisi semua data "
                "termasuk catatan verifikasi.")
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
