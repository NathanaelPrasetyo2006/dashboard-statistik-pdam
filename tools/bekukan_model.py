"""Bekukan model peneliti untuk satu jaringan ke `pdam/models/<id>.json` (menjadi jaringan bawaan dashboard).

Langkahnya sama dengan notebook Colab `Jaringan_KM_8.ipynb`: VARX + Fourier diestimasi dari Phase I,
lalu rata-rata & kovarians MEWMA. Titik diambil dari judul kolom file. UCL diberikan peneliti (`--ucl`)
atau, bila dikosongkan, dikalibrasi dengan bootstrap blok seperti notebook (ARL₀ = 200).

Jaringan KM 8 (cukup nama file; hasil diperiksa terhadap Colab: 57 sinyal, 10 episode, T² maks 73,758,
Bangun Reksa dominan pada 5 episode; bila berbeda, file TIDAK ditulis):
    .venv\\Scripts\\python tools/bekukan_model.py "Data Bersih.xlsx"

Jaringan lain:
    .venv\\Scripts\\python tools/bekukan_model.py data.xlsx --id cabang2 --nama "Jaringan Cabang 2" \\
        --phase-i 2027-01-01 2027-01-20 [--mulai-monitoring 2027-01-21] [--ucl 18.5] [--satuan bar] \\
        [--catatan "Residual titik X masih berautokorelasi."]
"""
import argparse
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pdam import model, storage  # noqa: E402
from pdam.config import MODEL_DIR  # noqa: E402

PRESET_KM8 = {
    "id": "km8",
    "nama": "Jaringan KM 8",
    "phase_i": ["2026-07-01", "2026-07-20"],
    "mulai_monitoring": "2026-07-21",
    "ucl": 22.5640,
    "satuan": "",
    "validasi": {"arl0_validasi": 194.07, "arl0_ci95": [182.47, 205.66],
                 "baseline_p_rata_rata": 0.13293, "baseline_p_kovarians": 0.38481},
    "catatan": ["Residual Paldam masih berautokorelasi.",
                "9 Juli 12.00 adalah pengamatan ekstrem pada Phase I."],
    "acuan_uji": {"periode": ["2026-07-21", "2026-07-31"], "n_observasi": 264, "n_sinyal": 57, "n_episode": 10,
                  "maks_t2": 73.758, "dominan": ["Bangun Reksa", 5]},
}


def ringkas_phase_ii(tekanan, m, titik, periode):
    mon, kon = model.hitung_monitoring(tekanan, m)
    mon = mon[mon["Datetime"].between(pd.Timestamp(periode[0]), pd.Timestamp(periode[1]) + pd.Timedelta(hours=23))]
    mon = mon.assign(Episode=storage.hitung_episode(mon))
    dom = model.titik_dominan(mon, kon, titik)["Titik_Dominan"].value_counts()
    return {"n_observasi": len(mon), "n_sinyal": int(mon["Sinyal"].sum()), "n_episode": int(mon["Episode"].nunique()),
            "maks_t2": round(float(mon["T2_MEWMA"].max()), 3), "dominan": dom}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("file")
    ap.add_argument("--id")
    ap.add_argument("--nama")
    ap.add_argument("--phase-i", nargs=2, metavar=("AWAL", "AKHIR"))
    ap.add_argument("--mulai-monitoring")
    ap.add_argument("--ucl", type=float)
    ap.add_argument("--satuan", default="")
    ap.add_argument("--catatan", action="append", default=[])
    arg = ap.parse_args()

    preset = PRESET_KM8 if arg.id in (None, "km8") else {}
    jid = arg.id or preset["id"]
    nama = arg.nama or preset.get("nama")
    phase_i = arg.phase_i or preset.get("phase_i")
    if not (nama and phase_i):
        sys.exit("Untuk jaringan selain KM 8, isi --id, --nama, dan --phase-i.")
    mulai = arg.mulai_monitoring or preset.get("mulai_monitoring") or \
        (pd.Timestamp(phase_i[1]) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    ucl = arg.ucl if arg.ucl is not None else preset.get("ucl")

    df, galat = storage.baca_file(type("F", (), {"name": Path(arg.file).name,
                                                  "getvalue": lambda self: Path(arg.file).read_bytes()})())
    if df is None:
        sys.exit(galat)
    titik = storage.kolom_titik(storage._gabung_datetime(df.copy()))
    hasil = storage.rapikan_tekanan(df, titik, nama)
    if hasil.galat:
        sys.exit("; ".join(hasil.galat))
    print("Titik:", ", ".join(titik))
    masalah, n = model.cek_kelayakan(hasil.data, titik, phase_i)
    if masalah:
        sys.exit("; ".join(masalah))

    m = model.latih(hasil.data, titik, phase_i, mulai, ucl=ucl, sumber="peneliti", nama_model=f"Model {nama}")
    m["nama_jaringan"], m["satuan"], m["sumber_data"] = nama, arg.satuan or preset.get("satuan", ""), Path(arg.file).name
    m["validasi"].update(preset.get("validasi", {}))
    m["catatan"] = preset.get("catatan", []) + arg.catatan
    if jid == "km8":
        m["nama_model"] = "Model A"

    acuan = preset.get("acuan_uji")
    if acuan:
        r = ringkas_phase_ii(hasil.data, m, titik, acuan["periode"])
        nama_dom, n_dom = acuan["dominan"]
        cocok = {"n_observasi": r["n_observasi"], "n_sinyal": r["n_sinyal"], "n_episode": r["n_episode"],
                 "maks_t2": r["maks_t2"], "dominan": [nama_dom, int(r["dominan"].get(nama_dom, 0))]}
        print("Hasil :", cocok)
        print("Colab :", {k: v for k, v in acuan.items() if k != "periode"})
        if any(cocok[k] != acuan[k] for k in cocok):
            sys.exit("Hasil tidak sama dengan Colab; file model TIDAK ditulis.")
        m["acuan_uji"] = acuan

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    tujuan = MODEL_DIR / f"{jid}.json"
    tujuan.write_text(json.dumps(m, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"UCL {m['ucl']:.4f} · {m['n_residual_phase_i']} residual Phase I · tersimpan: {tujuan}")


if __name__ == "__main__":
    main()
