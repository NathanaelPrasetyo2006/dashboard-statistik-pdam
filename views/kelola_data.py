from datetime import datetime, timedelta

import pandas as pd
import streamlit as st

from pdam import analysis as an
from pdam import charts, storage, ui
from pdam import jaringan as jr
from pdam.config import MIN_TITIK

store = ui.muat()
J = store.jaringan
jid = J.id

st.title("Kelola Data & Import")
st.markdown(f"Jaringan aktif: **{J.nama}** · {len(J.titik)} titik ({', '.join(J.titik)}) · {ui.label_model(store)}. "
            "Ganti jaringan lewat pilihan di sidebar.")

if not store.kosong:
    t = store.tekanan
    a, b, c = st.columns(3)
    a.metric("Jam data tekanan", len(t), border=True)
    b.metric("Jam dengan T² MEWMA", len(store.monitoring), border=True)
    c.metric("Periode tersimpan", f"{t['Datetime'].min():%d %b %Y} – {t['Datetime'].max():%d %b %Y}", border=True)

tab_import, tab_jaringan, tab_riwayat, tab_backup = st.tabs(
    ["Import data tekanan", "Jaringan & model", "Riwayat", "Backup & reset"])


def tampilkan_pesan(galat=(), peringatan=(), info=()):
    for g in galat:
        st.error(g, icon=":material/block:")
    for p in peringatan:
        st.warning(p, icon=":material/warning:")
    for i in info:
        st.info(i, icon=":material/info:")


def buat_jaringan(nama: str, titik: list[str], satuan: str = "") -> None:
    """Callback tombol: membuat jaringan lalu langsung memilihnya."""
    try:
        baru = jr.tambah(nama, titik, satuan)
    except ValueError as e:
        st.session_state["pesan_jaringan"] = ("error", str(e))
        return
    storage.segarkan()
    ui.pilih_jaringan(baru.id)
    st.session_state["pesan_jaringan"] = ("ok", f"Jaringan {baru.nama} dibuat dan dipilih.")


# --------------------------------------------------------------------------- import

with tab_import:
    st.download_button(f"Unduh template Excel {J.nama}", storage.template_tekanan(store.titik),
                       f"template_tekanan_{jid}.xlsx",
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", icon=":material/download:")
    st.caption("Satu baris per jam. Judul boleh dua baris seperti file data PDAM (`Tanggal` | `Tekanan`, lalu `Jam` dan "
               "nama titik) atau satu baris (`Tanggal`, `Jam`, titik… / `Datetime`, titik…). Tanggal boleh hanya diisi "
               "di jam pertama (sel gabungan). Kolom dicocokkan dengan nama titik jaringan tanpa memperhatikan huruf "
               "besar/kecil dan spasi; titik yang tidak ada di file dianggap kosong.")
    if ui.kunci_admin():
        f = st.file_uploader("File tekanan", type=["xlsx", "xls", "csv"], key=f"up_tekanan_{jid}")
        if f:
            mentah, galat_baca = storage.baca_file(f)
            hasil = storage.rapikan_tekanan(mentah, store.titik, J.nama) if mentah is not None \
                else storage.HasilBaca(None, galat=[galat_baca])
            df = hasil.data
            mon_baru = storage.pratinjau_import(df, store) if df is not None else None

            if df is not None:
                ada = int(df["Datetime"].isin(set(store.tekanan["Datetime"])).sum())
                if ada:
                    hasil.peringatan.append(f"{ada} jam sudah ada di data tersimpan dan akan diganti dengan nilai dari file ini.")
                if not store.kosong:
                    akhir_lama, awal_baru = store.tekanan["Datetime"].max(), df["Datetime"].min()
                    if awal_baru > akhir_lama + pd.Timedelta(hours=1):
                        jeda = (awal_baru - akhir_lama) / pd.Timedelta(hours=1)
                        hasil.info.append(f"Ada jeda {jeda:.0f} jam antara data tersimpan (s.d. {akhir_lama:%d %b %Y %H:%M}) "
                                          f"dan file ini (mulai {awal_baru:%d %b %Y %H:%M}). Jam-jam awal setelah jeda tidak "
                                          "memiliki T² karena model memerlukan tekanan jam-jam sebelumnya.")
                st.markdown(f"**Pratinjau:** {len(df)} jam, {df['Datetime'].min():%d %b %Y %H:%M} – "
                            f"{df['Datetime'].max():%d %b %Y %H:%M}.")
                if store.model is None:
                    st.caption(f"{J.nama} belum memiliki model: data tersimpan dan tampil di grafik tekanan, tetapi T² "
                               "baru dihitung setelah model dilatih atau dipasang di tab **Jaringan & model**.")
                else:
                    st.markdown(f"Setelah disimpan: **{len(mon_baru)}** jam memiliki T², "
                                f"**{int(mon_baru['Sinyal'].sum())}** di antaranya kandidat OOC "
                                f"(T² > UCL {an.fmt_angka(store.ucl, 4)}).")
                    if len(df) > len(mon_baru):
                        st.caption(f"{len(df) - len(mon_baru)} jam tidak memiliki T²: jam pada Phase I (periode "
                                   "referensi model), sebelum awal monitoring, atau dengan tekanan/lag yang tidak lengkap.")
                    if not mon_baru.empty:
                        st.plotly_chart(charts.peta_kendali(mon_baru.assign(Episode=storage.hitung_episode(mon_baru)),
                                                            store.ucl, tinggi=260), key="up_preview")
                with st.expander("Lihat data yang terbaca"):
                    st.dataframe(df, hide_index=True, height=240, column_config={
                        "Datetime": st.column_config.DatetimeColumn(format="DD MMM YYYY HH:mm")})
            tampilkan_pesan(hasil.galat, hasil.peringatan, hasil.info)

            # Kolom yang bukan titik jaringan ini: tambahkan sebagai titik baru, atau buat jaringan baru.
            if hasil.titik_baru and df is not None and not J.bawaan:
                with st.container(border=True):
                    st.markdown(f"**Tambahkan {', '.join(hasil.titik_baru)} sebagai titik baru {J.nama}?**")
                    if store.model is not None:
                        st.caption("Model saat ini dibuat tanpa titik tersebut; setelah titik ditambahkan model perlu "
                                   "dilatih ulang atau diganti model peneliti sebelum T² dapat dihitung lagi.")
                    if st.button("Tambahkan titik", icon=":material/add_location_alt:"):
                        storage.tambah_titik(jid, hasil.titik_baru)
                        st.rerun()
            if df is None and len(hasil.titik_file) >= MIN_TITIK:
                with st.container(border=True):
                    st.markdown(f"**Buat jaringan baru dari file ini** ({len(hasil.titik_file)} titik: "
                                f"{', '.join(hasil.titik_file)})")
                    nama_baru = st.text_input("Nama jaringan baru", key="nama_dari_file")
                    st.button("Buat jaringan & pilih", icon=":material/add:", disabled=not nama_baru.strip(),
                              on_click=buat_jaringan, args=(nama_baru, hasil.titik_file))

            if df is not None:
                nama_default = f"{df['Datetime'].min():%b %Y}"
                batch = st.text_input("Nama periode", value=nama_default, key="up_batch",
                                      help="Label untuk membedakan periode di ringkasan Overview.")
                if st.button("Simpan ke dashboard", type="primary", disabled=bool(hasil.galat), icon=":material/save:"):
                    storage.simpan_tekanan(jid, df, batch.strip() or nama_default, f.name, mon_baru)
                    st.toast(f"Data {J.nama} tersimpan.")
                    st.session_state.pop(ui.KUNCI_RENTANG, None)
                    st.rerun()
    pesan = st.session_state.pop("pesan_jaringan", None)
    if pesan:
        (st.success if pesan[0] == "ok" else st.error)(pesan[1])
    if store.model is not None:
        with st.expander("Bagaimana data diproses?"):
            a1, b1 = an.periode_phase_i(store)
            st.markdown(
                f"1. Parameter model (koefisien VARX + Fourier, rata-rata dan kovarians MEWMA, UCL "
                f"{an.fmt_angka(store.ucl, 4)}, λ = {an.fmt_angka(store.model['lambda_mewma'], 1)}) diestimasi sekali "
                f"dari Phase I ({a1:%d %b} – {b1:%d %b %Y}) dan tidak berubah saat import.\n"
                "2. Nilai kosong yang hanya 1 jam diisi interpolasi waktu, sama seperti di notebook Colab.\n"
                f"3. T² MEWMA dihitung untuk setiap jam sejak {pd.Timestamp(store.model['mulai_monitoring']):%d %b %Y} "
                f"yang memiliki tekanan semua titik dan data {max(store.model['lag'])} jam sebelumnya lengkap. "
                "Statistik MEWMA berlanjut dari jam terakhir data sebelumnya.\n"
                "4. Mengimpor ulang jam yang sudah ada mengganti nilai lama; seluruh statistik dihitung ulang.")

# --------------------------------------------------------------------------- jaringan & model

with tab_jaringan:
    kiri, kanan = st.columns([1, 1.2])
    with kiri, st.container(border=True):
        st.subheader(J.nama)
        st.markdown(f"**Jenis:** {'bawaan (model peneliti di repositori)' if J.bawaan else 'ditambahkan di dashboard'}  \n"
                    f"**Titik ({len(J.titik)}):** {', '.join(J.titik)}  \n**Satuan:** {J.satuan or '–'}")
        if ui.admin_aktif():
            with st.form(f"form_info_{jid}"):
                nama = st.text_input("Nama jaringan", value=J.nama)
                satuan = st.text_input("Satuan tekanan", value=J.satuan, placeholder="mis. bar, m, psi")
                if st.form_submit_button("Simpan", icon=":material/save:"):
                    jr.ubah(jid, nama=nama, satuan=satuan)
                    storage.segarkan()
                    st.rerun()

    with kanan, st.container(border=True):
        st.subheader("Model")
        m = jr.model_aktif(jid)
        if store.status_model == "tidak_cocok":
            st.warning(f"Model aktif memakai titik {', '.join(m['titik'])}, berbeda dengan titik jaringan. "
                       "Latih ulang atau pasang model peneliti yang sesuai.", icon=":material/warning:")
        if m is None:
            st.info("Belum ada model. T² MEWMA belum dapat dihitung.", icon=":material/model_training:")
        else:
            sumber = "Peneliti" if m.get("sumber") == "peneliti" else "Otomatis (dashboard)"
            st.markdown(f"**{m['nama_model']}** · {sumber}  \nPhase I: {m['periode_phase_i'][0]} s.d. "
                        f"{m['periode_phase_i'][1]} · monitoring mulai {m['mulai_monitoring']}  \n"
                        f"UCL {an.fmt_angka(m['ucl'], 4)} · λ = {an.fmt_angka(m['lambda_mewma'], 1)} · dibuat {m.get('dibuat', '–')}")
            if jr.model_lokal_ada(jid) and jr.ada_model_bawaan(jid):
                st.caption("Model ini menggantikan model bawaan repositori untuk jaringan ini.")

    if ui.kunci_admin():
        st.markdown("#### Latih model otomatis")
        st.caption("Struktur model mengikuti Model A Jaringan KM 8 (VARX lag 1, 2, 3, 24 jam + Fourier harian, MEWMA "
                   "λ = 0,1); UCL dikalibrasi dengan bootstrap blok 48 jam untuk ARL₀ = 200. Pilih Phase I: periode "
                   "operasi normal yang menjadi acuan. Monitoring dimulai sehari setelah Phase I berakhir.")
        if store.kosong:
            st.info("Import data tekanan jaringan ini terlebih dahulu.")
        else:
            tmin, tmax = store.tekanan["Datetime"].min().date(), store.tekanan["Datetime"].max().date()
            akhir_default = min(tmin + timedelta(days=19), max(tmin, tmax - timedelta(days=1)))
            rentang = st.date_input("Periode Phase I", value=(tmin, akhir_default), min_value=tmin, max_value=tmax,
                                    format="DD/MM/YYYY", key=f"phase_i_{jid}")
            if isinstance(rentang, (list, tuple)) and len(rentang) == 2:
                phase_i = (rentang[0].isoformat(), rentang[1].isoformat())
                masalah, n_jam = storage.cek_pelatihan(store, phase_i)
                if masalah:
                    tampilkan_pesan(galat=masalah)
                else:
                    st.caption(f"{n_jam} jam lengkap di Phase I dapat dipakai.")
                ganti_peneliti = m is not None and m.get("sumber") == "peneliti"
                yakin = True
                if ganti_peneliti:
                    yakin = st.checkbox("Ganti model peneliti yang sedang aktif dengan model otomatis.", key=f"yakin_latih_{jid}")
                if st.button("Latih model otomatis", type="primary", icon=":material/model_training:",
                             disabled=bool(masalah) or not yakin):
                    with st.spinner("Mengestimasi VARX dan mengkalibrasi UCL…"):
                        hasil_latih = storage.latih_model_otomatis(store, phase_i)
                    st.toast(f"Model otomatis tersimpan. UCL {an.fmt_angka(hasil_latih['ucl'], 4)}, "
                             f"ARL₀ validasi {an.fmt_angka(hasil_latih['validasi']['arl0_validasi'])}.")
                    st.rerun()
            else:
                st.caption("Pilih tanggal awal dan akhir Phase I.")

        st.markdown("#### Pasang model dari peneliti")
        st.caption("File JSON hasil `tools/bekukan_model.py` dari data jaringan ini. Titik di file harus sama dengan titik "
                   "jaringan. Model peneliti menggantikan model otomatis.")
        fm = st.file_uploader("File model (.json)", type=["json"], key=f"up_model_{jid}")
        if fm and st.button("Pasang model", icon=":material/upload:"):
            galat = storage.pasang_model(store, fm.getvalue(), fm.name)
            if galat:
                tampilkan_pesan(galat=galat)
            else:
                st.toast("Model peneliti terpasang.")
                st.rerun()
        if jr.model_lokal_ada(jid):
            label = "Kembalikan ke model bawaan" if jr.ada_model_bawaan(jid) else "Hapus model"
            if st.button(label, icon=":material/undo:"):
                storage.hapus_model_lokal(store)
                st.rerun()

        st.divider()
        st.markdown("#### Tambah jaringan baru")
        with st.form("form_jaringan_baru", clear_on_submit=True):
            nama_baru = st.text_input("Nama jaringan", placeholder="mis. Jaringan Cabang 2")
            satuan_baru = st.text_input("Satuan tekanan (opsional)")
            titik_teks = st.text_area("Nama titik (satu per baris)",
                                      help="Atau kosongkan dan unggah file contoh: titik diambil dari judul kolom.")
            contoh = st.file_uploader("File contoh (opsional)", type=["xlsx", "xls", "csv"])
            if st.form_submit_button("Buat jaringan", icon=":material/add:"):
                titik_baru = [t.strip() for t in titik_teks.splitlines() if t.strip()]
                if not titik_baru and contoh is not None:
                    mentah, _ = storage.baca_file(contoh)
                    titik_baru = storage.kolom_titik(storage._gabung_datetime(mentah)) if mentah is not None else []
                if not nama_baru.strip():
                    st.error("Nama jaringan wajib diisi.")
                elif len(titik_baru) < MIN_TITIK:
                    st.error(f"Diperlukan minimal {MIN_TITIK} titik (tulis nama titik atau unggah file contoh).")
                else:
                    buat_jaringan(nama_baru, titik_baru, satuan_baru)
                    st.rerun()

        if not J.bawaan:
            st.divider()
            st.markdown(f"#### Hapus {J.nama}")
            yakin_hapus = st.checkbox(f"Saya mengerti data, model, dan catatan verifikasi {J.nama} akan dihapus.",
                                      key=f"yakin_hapus_jaringan_{jid}")

            def _hapus_jaringan():
                jr.hapus(jid)
                storage.segarkan()
                ui.pilih_jaringan(jr.daftar()[0].id)

            st.button("Hapus jaringan", icon=":material/delete_forever:", disabled=not yakin_hapus,
                      on_click=_hapus_jaringan)

# --------------------------------------------------------------------------- riwayat

with tab_riwayat:
    if store.riwayat:
        st.dataframe(pd.DataFrame(store.riwayat).iloc[::-1], hide_index=True)
    else:
        st.info(f"Belum ada import untuk {J.nama}.")

# --------------------------------------------------------------------------- backup & reset

with tab_backup:
    st.markdown("Unduh backup secara berkala, terutama bila dashboard dijalankan di Streamlit Community Cloud: "
                "penyimpanan di sana **bisa terhapus** saat aplikasi dimulai ulang. Backup berisi **semua jaringan**: "
                "daftar jaringan, data tekanan, model otomatis/terpasang, catatan verifikasi, dan riwayat.")
    st.download_button("Unduh backup (ZIP)", storage.buat_backup(),
                       f"backup_dashboard_pdam_{datetime.now():%Y%m%d_%H%M}.zip", "application/zip",
                       icon=":material/backup:", disabled=not storage.ada_data())
    if ui.kunci_admin():
        st.divider()
        pulih = st.file_uploader("Pulihkan dari backup", type=["zip"], key="up_backup")
        if pulih and st.button("Pulihkan (data semua jaringan diganti)", icon=":material/settings_backup_restore:"):
            try:
                nama = storage.pulihkan_backup(pulih.getvalue())
                ui.reset_pilihan()
                st.toast(f"Dipulihkan: {len(nama)} file.")
                st.rerun()
            except ValueError as e:
                st.error(str(e))
        st.divider()
        yakin = st.checkbox(f"Saya mengerti data tekanan, catatan verifikasi, dan riwayat {J.nama} akan dihapus "
                            "(daftar titik dan model tetap).", key=f"yakin_hapus_{jid}")
        if st.button(f"Hapus data {J.nama}", disabled=not yakin, icon=":material/delete_forever:"):
            storage.hapus_data(jid)
            st.session_state.pop(ui.KUNCI_RENTANG, None)
            st.rerun()
