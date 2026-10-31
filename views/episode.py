import io
from datetime import date

import pandas as pd
import streamlit as st

from pdam import analysis as an
from pdam import charts, storage, ui
from pdam.config import KALIMAT_BATASAN, STATUS_VERIFIKASI

store = ui.muat()
jid = store.jaringan.id
ui.kepala("Investigasi Episode", store,
          "Daftar episode kandidat penyimpangan untuk diperiksa dan diverifikasi PDAM. "
          "Pilih baris tabel untuk membuka detail episode.")
ui.wajib_data(store)

awal, akhir = ui.rentang(store)
eps = an.episode_dalam_rentang(store, awal, akhir).reset_index(drop=True)
if eps.empty:
    st.info("Tidak ada episode pada rentang tanggal ini.")
    st.stop()

status_filter = st.multiselect("Filter status verifikasi", STATUS_VERIFIKASI, key="ep_status")
tabel = eps[eps["Status"].isin(status_filter)] if status_filter else eps
tabel = tabel.reset_index(drop=True)

# Pilihan dari baris tabel atau dari halaman lain (tombol "Buka episode").
sel = st.session_state.get("ep_tabel")
baris_pilih = (sel or {}).get("selection", {}).get("rows", []) if sel else []
if baris_pilih and baris_pilih[0] < len(tabel):
    ep_baris = int(tabel.loc[baris_pilih[0], "Episode"])
    if ep_baris != st.session_state.get("ep_baris_terakhir"):
        st.session_state["ep_baris_terakhir"] = ep_baris
        st.session_state["episode_terpilih"] = ep_baris

kolom = ["Episode", "Mulai", "Selesai", "Jumlah_Jam_Sinyal", "Maksimum_T2", "Titik_Dominan", "Status", "Petugas"]
st.dataframe(tabel[kolom], hide_index=True, key="ep_tabel", on_select="rerun", selection_mode="single-row",
             column_config={
                 "Mulai": st.column_config.DatetimeColumn(format="DD MMM YYYY HH:mm"),
                 "Selesai": st.column_config.DatetimeColumn(format="DD MMM YYYY HH:mm"),
                 "Jumlah_Jam_Sinyal": st.column_config.NumberColumn(
                     "Jam sinyal", help="Banyaknya pengamatan bersinyal, bukan durasi kerusakan terkonfirmasi."),
                 "Maksimum_T2": st.column_config.NumberColumn("T² maks", format="%.3f"),
                 "Titik_Dominan": st.column_config.TextColumn(
                     "Titik dominan", help="Titik dengan rata-rata kontribusi T² terbesar pada jam bersinyal episode."),
                 "Status": "Verifikasi",
             })

c1, c2 = st.columns(2)
c1.download_button("Unduh tabel episode (CSV)", eps.to_csv(index=False).encode("utf-8"), f"episode_verifikasi_{jid}.csv",
                   "text/csv", icon=":material/download:")


def laporan_excel() -> bytes:
    buf = io.BytesIO()
    mon = an.potong(store.monitoring, awal, akhir)
    ringkas = pd.DataFrame({
        "Keterangan": ["Jaringan", "Model", "Jenis data", "Rentang", "UCL", "Jam pengamatan", "Kandidat OOC", "Episode", "Catatan"],
        "Nilai": [f"{store.jaringan.nama} ({', '.join(store.titik)})", ui.label_model(store), "Historis per jam",
                  f"{awal:%d %b %Y} – {akhir:%d %b %Y}", store.ucl, len(mon), int(mon["Sinyal"].sum()), len(eps),
                  "Kandidat OOC bukan kebocoran terkonfirmasi. " + KALIMAT_BATASAN],
    })
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        ringkas.to_excel(xw, sheet_name="Ringkasan", index=False)
        eps.drop(columns=["Kunci_Episode"]).to_excel(xw, sheet_name="Episode", index=False)
        log = storage.log_verifikasi(jid)
        if log is not None:
            log.to_excel(xw, sheet_name="Riwayat verifikasi", index=False)
    return buf.getvalue()


c2.download_button("Unduh laporan (Excel)", laporan_excel(), f"laporan_episode_{jid}.xlsx",
                   "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", icon=":material/description:")

st.divider()

ids = list(eps["Episode"])
if st.session_state.get("episode_terpilih") not in ids:
    st.session_state["episode_terpilih"] = ids[0]
pilih = st.selectbox("Detail episode", ids, key="episode_terpilih",
                     format_func=lambda i: f"Episode {i} — mulai {an.fmt_waktu(eps.loc[eps['Episode'] == i, 'Mulai'].iloc[0])}")
e = eps[eps["Episode"] == pilih].iloc[0]

m1, m2, m3, m4 = st.columns(4)
m1.metric("Mulai", f"{e['Mulai']:%d %b %H:%M}", border=True)
m2.metric("Selesai", f"{e['Selesai']:%d %b %H:%M}", border=True)
m3.metric("Jam sinyal", int(e["Jumlah_Jam_Sinyal"]), border=True,
          help="Banyaknya pengamatan bersinyal, bukan durasi kerusakan terkonfirmasi.")
m4.metric("T² maksimum", an.fmt_angka(e["Maksimum_T2"], 3), border=True, help=f"Pada {an.fmt_waktu(e['Waktu_T2_Maks'])}")

dom = e["Titik_Dominan"] if pd.notna(e["Titik_Dominan"]) and str(e["Titik_Dominan"]).strip() else None
narasi = "Pada periode ini, statistik VARX–MEWMA melewati batas kendali. "
narasi += (f"**{dom}** merupakan titik dengan kontribusi diagnostik dominan. " if dom
           else "Titik dominan tidak dapat ditentukan untuk episode ini. ")
narasi += "Hasil ini menunjukkan perlunya pemeriksaan kondisi operasional, bukan bukti langsung adanya kebocoran."
st.info(narasi, icon=":material/lightbulb:")

a = e["Mulai"] - pd.Timedelta(hours=6)
b = e["Selesai"] + pd.Timedelta(hours=6)
satu = eps[eps["Episode"] == pilih]
g1, g2 = st.columns(2)
with g1:
    st.markdown("**Tekanan semua titik (±6 jam)**")
    jendela = store.tekanan[store.tekanan["Datetime"].between(a, b)]
    st.plotly_chart(charts.semua_tekanan(jendela, store.titik, eps=satu, satuan=ui.satuan(store), tinggi=320), key="ep_tekanan")
with g2:
    st.markdown("**T² MEWMA (±6 jam)**")
    mon_j = store.monitoring[store.monitoring["Datetime"].between(a, b)]
    st.plotly_chart(charts.peta_kendali(mon_j, store.ucl, satu, tinggi=320), key="ep_t2")

st.markdown("**Diagnostik kontribusi per titik**")
kon = store.kontribusi[store.kontribusi["Datetime"].between(a, b)]
if kon.empty:
    st.info("Tidak ada jam dengan T² pada rentang episode ini.")
else:
    st.plotly_chart(charts.kontribusi(kon, store.titik), key="ep_kontribusi")
    st.caption("Kontribusi titik = T² dikurangi T² bila titik itu tidak diikutkan. "
               "Kontribusi diagnostik bukan bukti sebab atau lokasi kebocoran.")

st.subheader("Catatan verifikasi operator")
st.caption("Disimpan terpisah dari hasil statistik; mengubah catatan tidak mengubah hasil analisis.")
if ui.kunci_admin():
    with st.form(f"form_ver_{e['Kunci_Episode']}"):
        f1, f2, f3 = st.columns(3)
        status = f1.selectbox("Status", STATUS_VERIFIKASI, index=STATUS_VERIFIKASI.index(e["Status"])
                              if e["Status"] in STATUS_VERIFIKASI else 0)
        tgl_awal = pd.to_datetime(e["Tanggal_Pemeriksaan"], errors="coerce")
        tanggal = f2.date_input("Tanggal pemeriksaan", value=tgl_awal.date() if pd.notna(tgl_awal) else date.today(),
                                format="DD/MM/YYYY")
        petugas = f3.text_input("Petugas", value=e["Petugas"])
        catatan = st.text_area("Catatan lapangan", value=e["Catatan"],
                               placeholder="Contoh: pengecekan katup zona Bangun Reksa, tidak ditemukan kebocoran.")
        st.caption("Alur: Belum diperiksa → Dalam pemeriksaan → Terkonfirmasi / Tidak terkonfirmasi.")
        if st.form_submit_button("Simpan verifikasi", type="primary", icon=":material/save:"):
            storage.simpan_verifikasi(jid, e["Kunci_Episode"], status, catatan.strip(), tanggal.isoformat(), petugas.strip())
            st.toast(f"Verifikasi episode {pilih} disimpan.")
            st.rerun()
else:
    st.markdown(f"Status: **{e['Status']}** · Petugas: {e['Petugas'] or '–'} · Catatan: {e['Catatan'] or '–'}")

log = storage.log_verifikasi(jid)
if log is not None:
    riwayat = log[log["Kunci_Episode"] == e["Kunci_Episode"]]
    if not riwayat.empty:
        with st.expander(f"Riwayat perubahan ({len(riwayat)})"):
            st.dataframe(riwayat.drop(columns="Kunci_Episode").iloc[::-1], hide_index=True)

st.divider()
st.subheader("Titik dominan per episode")
dom_df, n_terisi = an.hitung_dominan(eps, store.titik)
if n_terisi == 0:
    st.info("Titik dominan tidak dapat ditentukan untuk episode pada rentang ini.")
else:
    st.plotly_chart(charts.dominan(dom_df), key="ep_dominan")
    st.caption(f"Dari {n_terisi} episode yang titik dominannya terisi. Dominansi adalah kontribusi diagnostik terbesar "
               "pada episode, bukan bukti titik penyebab atau kebocoran.")
    if n_terisi < len(eps):
        st.caption(f"{len(eps) - n_terisi} episode belum memiliki titik dominan.")
