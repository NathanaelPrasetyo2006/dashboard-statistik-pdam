"""Bekukan parameter Model A dari data tekanan Juli 2026 ke `pdam/model_A.json`.

Cukup dijalankan sekali (atau bila peneliti mengganti model). Langkahnya sama dengan notebook
Colab `Jaringan_KM_8.ipynb`; skrip berhenti bila hasil Phase II tidak sama dengan Colab
(57 sinyal, 10 episode, T² maks 73,758, Bangun Reksa dominan 5 episode).

Jalankan:  .venv\\Scripts\\python tools/bekukan_model.py "Data Bersih.xlsx"
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pdam import model, storage  # noqa: E402
from pdam.config import ACUAN_UJI, LAMBDA_MEWMA, PHASE_I, PHASE_II, UCL_MODEL_A  # noqa: E402


def main(path: str) -> None:
    raw = Path(path).read_bytes()
    tekanan, pesan = storage._rapikan_tekanan(storage._baca_tabel_tekanan(raw, Path(path).name))
    if tekanan is None:
        sys.exit("Gagal membaca data: " + "; ".join(pesan["galat"]))

    params = model.latih(tekanan, PHASE_I, PHASE_II, LAMBDA_MEWMA, UCL_MODEL_A)
    params["sumber_data"] = Path(path).name

    mon, kon = model.hitung_monitoring(tekanan, params)
    mon = mon[mon["Datetime"] <= f"{PHASE_II[1]} 23:00"].copy()
    mon["Episode"] = storage.hitung_episode(mon)
    dom = model.titik_dominan(mon, kon)["Titik_Dominan"].value_counts()
    hasil = {"n_observasi": len(mon), "n_sinyal": int(mon["Sinyal"].sum()),
             "n_episode": int(mon["Episode"].nunique()), "maks_t2": round(float(mon["T2_MEWMA"].max()), 3),
             "dominan": (ACUAN_UJI["dominan"][0], int(dom.get(ACUAN_UJI["dominan"][0], 0)))}
    acuan = {k: ACUAN_UJI[k] for k in hasil}
    print("Hasil :", hasil)
    print("Colab :", acuan)
    if hasil != acuan:
        sys.exit("Hasil tidak sama dengan Colab; model_A.json TIDAK ditulis.")

    model.FILE_MODEL.write_text(json.dumps(params, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"Tersimpan: {model.FILE_MODEL}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "Data Bersih.xlsx")
