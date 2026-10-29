# Jalankan sebagai SEL TERAKHIR pada notebook Colab Model A.
# Tidak mengestimasi ulang VARX/MEWMA; hanya mengekspor hasil yang sudah ada.
import json, zipfile
from pathlib import Path
import numpy as np
import pandas as pd

OUT = Path('/content/dashboard_model_A')
OUT.mkdir(parents=True, exist_ok=True)
TITIK = ['IPA KM 8','Bangun Reksa','Simpang Prumnas','Ojek Maxi','Paldam']
UCL_FINAL = 22.5640  # batas kalibrasi bootstrap blok 48 jam, dari hasil Model A

# Hindari memakai variabel hasil eksplorasi awal (hasil_mewma, grafik, UCL_arl).
required = ['hasil_final', 'ringkasan_episode']
missing = [name for name in required if name not in globals()]
if missing:
    raise RuntimeError('Objek belum tersedia: ' + ', '.join(missing) + '. Jalankan sel Model A final terlebih dahulu.')

hf = hasil_final.copy()
if not {'Datetime','T2_MEWMA'}.issubset(hf.columns):
    raise ValueError('hasil_final harus memiliki Datetime dan T2_MEWMA')
hf['Datetime'] = pd.to_datetime(hf['Datetime'])
hf = hf.sort_values('Datetime').reset_index(drop=True)
hf['Sinyal'] = hf['T2_MEWMA'].astype(float) > UCL_FINAL
hf['UCL'] = UCL_FINAL
# Bangun ulang ID episode agar tetap konsisten dan tidak bergantung pada objek sementara.
starts = hf['Sinyal'] & (~hf['Sinyal'].shift(fill_value=False) | hf['Datetime'].diff().gt(pd.Timedelta(hours=1)))
hf['Episode'] = starts.cumsum().where(hf['Sinyal']).astype('Int64')

# Pemeriksaan angka historis final (gagal jika hasil tercampur dengan versi eksploratif)
n_alarm = int(hf['Sinyal'].sum())
n_episode = int(hf['Episode'].nunique())
if (n_alarm,n_episode) != (57,10):
    raise ValueError(f'Keluaran tidak cocok dengan Model A final: {n_alarm} sinyal, {n_episode} episode; diharapkan 57 dan 10. Periksa hasil_final dan UCL.')

hf[['Datetime','T2_MEWMA','UCL','Sinyal','Episode']].to_csv(OUT/'mewma_monitoring.csv',index=False)

# Tekanan aktual: gunakan objek data/df yang mengandung Datetime dan kelima kolom titik.
source = None
for candidate in ['data','df']:
    obj = globals().get(candidate)
    if isinstance(obj,pd.DataFrame) and set(TITIK).issubset(obj.columns):
        source = obj.copy()
        break
if source is None:
    raise ValueError('Tidak menemukan DataFrame data/df dengan lima kolom tekanan.')
if 'Datetime' not in source.columns:
    if {'Tanggal','Jam'}.issubset(source.columns):
        source['Datetime'] = pd.to_datetime(source['Tanggal'].astype(str)+' '+source['Jam'].astype(str),errors='coerce')
    else:
        raise ValueError('Data tekanan perlu kolom Datetime atau pasangan Tanggal + Jam.')
source['Datetime'] = pd.to_datetime(source['Datetime'])
pressure = source[['Datetime']+TITIK].dropna(subset=['Datetime']).sort_values('Datetime')
pressure.to_csv(OUT/'tekanan_aktual.csv',index=False)

# Tabel episode dihitung ulang dari hasil final agar semua durasi dan puncak konsisten.
episodes = (hf.loc[hf['Sinyal']].groupby('Episode',observed=True)
    .agg(Mulai=('Datetime','min'),Selesai=('Datetime','max'),
         Jumlah_Jam_Sinyal=('Sinyal','sum'),Maksimum_T2=('T2_MEWMA','max'))
    .reset_index())
# Dominansi dari ringkasan_episode hanya jika pasangan waktu awal cocok.
re = ringkasan_episode.copy()
if {'Mulai','Titik Dominan'}.issubset(re.columns):
    re['Mulai'] = pd.to_datetime(re['Mulai'])
    episodes = episodes.merge(re[['Mulai','Titik Dominan']].drop_duplicates('Mulai'),on='Mulai',how='left')
episodes['Status_Verifikasi'] = 'Belum diverifikasi'
episodes.to_csv(OUT/'episode_monitoring.csv',index=False)

# Kontribusi diagnostik: ekspor hanya jika objek jelas dan dapat diverifikasi.
# JANGAN merekayasa kontribusi dari tekanan mentah.
contrib_candidates = ['kontribusi_df','hasil_kontribusi','kontribusi']
found = False
for candidate in contrib_candidates:
    obj = globals().get(candidate)
    if isinstance(obj,pd.DataFrame) and set(TITIK).issubset(obj.columns) and 'Datetime' in obj.columns:
        obj[['Datetime']+TITIK].to_csv(OUT/'kontribusi_diagnostik.csv',index=False)
        found = True
        break
if not found:
    (OUT/'KONTRIBUSI_BELUM_TERSEDIA.txt').write_text(
        'Cari DataFrame kontribusi kondisional final di notebook; ekspor Datetime dan lima kolom titik. Jangan gunakan heatmap gambar sebagai sumber angka.\n',encoding='utf-8')

metadata = {
    'nama_model':'VARX–MEWMA Model A',
    'jenis_data':'Historis, bukan realtime',
    'periode_phase_i':'2026-07-01 sampai 2026-07-20',
    'periode_phase_ii':'2026-07-21 sampai 2026-07-31',
    'interval_pengamatan':'1 jam',
    'lambda_mewma':0.1,
    'bootstrap_blok_jam':48,
    'ucl':UCL_FINAL,
    'target_arl0':200,
    'arl0_validasi':194.07,
    'arl0_ci95':[182.47,205.66],
    'jumlah_kandidat_ooc':n_alarm,
    'jumlah_episode':n_episode,
    'interpretasi':'Sinyal menunjukkan penyimpangan statistik multivariat; bukan bukti kebocoran atau kerusakan yang terkonfirmasi.',
    'catatan':'Residual Paldam masih menunjukkan autokorelasi; pengamatan ekstrem 9 Juli 12.00 memerlukan verifikasi operasional.'
}
(OUT/'metadata_model.json').write_text(json.dumps(metadata,indent=2,ensure_ascii=False),encoding='utf-8')

print('BERHASIL. File:',*[p.name for p in OUT.iterdir()],sep='\n - ')
print('Pemeriksaan: ',n_alarm,'sinyal;',n_episode,'episode')
zip_path = Path('/content/dashboard_model_A.zip')
with zipfile.ZipFile(zip_path,'w',zipfile.ZIP_DEFLATED) as z:
    for p in OUT.iterdir(): z.write(p,arcname=p.name)
print('ZIP:',zip_path)
from google.colab import files
files.download(str(zip_path))
