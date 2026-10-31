"""Grafik Plotly. Merah hanya untuk sinyal; warna titik tetap per entitas; satu sumbu y per grafik."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from .analysis import fmt_angka
from .config import WARNA_EPISODE, WARNA_NETRAL, WARNA_PROFIL, WARNA_SINYAL, WARNA_UTAMA, warna_titik

FMT_WAKTU = "%d %b %Y %H:%M"


def _tata(fig: go.Figure, tinggi=380, judul_y=None, legend=True) -> go.Figure:
    fig.update_layout(
        height=tinggi, margin=dict(l=10, r=10, t=30, b=10),
        hovermode="closest", showlegend=legend,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        separators=",.",
    )
    fig.update_yaxes(title_text=judul_y, zeroline=False)
    fig.update_xaxes(hoverformat=FMT_WAKTU)
    return fig


def _arsir_episode(fig: go.Figure, eps: pd.DataFrame | None) -> None:
    if eps is None:
        return
    for _, e in eps.iterrows():
        fig.add_vrect(x0=e["Mulai"] - pd.Timedelta(minutes=30), x1=e["Selesai"] + pd.Timedelta(minutes=30),
                      fillcolor=WARNA_EPISODE, line_width=0, layer="below")


def peta_kendali(mon: pd.DataFrame, ucl: float, eps: pd.DataFrame | None = None,
                 terpilih=None, tinggi=400) -> go.Figure:
    fig = go.Figure()
    _arsir_episode(fig, eps)
    status = mon["Sinyal"].map({True: "Kandidat OOC", False: "Terkendali"})
    episode = mon["Episode"].astype("object").where(mon["Episode"].notna(), "–")
    custom = list(zip(status, (mon["T2_MEWMA"] - ucl).round(3), episode))
    fig.add_trace(go.Scatter(
        x=mon["Datetime"], y=mon["T2_MEWMA"], mode="lines+markers", name="T² MEWMA",
        line=dict(color=WARNA_UTAMA, width=2), marker=dict(size=4, color=WARNA_UTAMA),
        customdata=custom,
        hovertemplate="<b>%{x|" + FMT_WAKTU + "}</b><br>T² = %{y:.3f}<br>Selisih dari UCL = %{customdata[1]:+.3f}"
                      "<br>Status: %{customdata[0]}<br>Episode: %{customdata[2]}<extra></extra>",
    ))
    sig = mon[mon["Sinyal"]]
    if not sig.empty:
        fig.add_trace(go.Scatter(
            x=sig["Datetime"], y=sig["T2_MEWMA"], mode="markers", name="Kandidat OOC (T² > UCL)",
            marker=dict(size=8, color=WARNA_SINYAL, line=dict(width=1.5, color="white")),
            customdata=list(zip(sig["Episode"].astype(int), (sig["T2_MEWMA"] - ucl).round(3))),
            hovertemplate="<b>%{x|" + FMT_WAKTU + "}</b><br>T² = %{y:.3f}<br>Selisih dari UCL = %{customdata[1]:+.3f}"
                          "<br>Status: Kandidat OOC<br>Episode: %{customdata[0]}<extra></extra>",
        ))
    if terpilih is not None:
        baris = mon[mon["Datetime"] == pd.Timestamp(terpilih)]
        if not baris.empty:
            fig.add_trace(go.Scatter(x=baris["Datetime"], y=baris["T2_MEWMA"], mode="markers", name="Waktu terpilih",
                                     marker=dict(size=16, color="rgba(0,0,0,0)", line=dict(width=2.5, color=WARNA_NETRAL)),
                                     hoverinfo="skip"))
    fig.add_hline(y=ucl, line=dict(color=WARNA_NETRAL, width=1.5, dash="dash"),
                  annotation_text=f"UCL {fmt_angka(ucl, 4)} (batas hasil kalibrasi model)",
                  annotation_position="top left", annotation_font_size=11)
    return _tata(fig, tinggi, "Statistik T² MEWMA")


def tekanan_vs_profil(dev: pd.DataFrame, titik: str, waktu_sinyal: set, satuan: str, tinggi=400) -> go.Figure:
    fig = go.Figure()
    if dev["Rata_rata"].notna().any():
        atas = (dev["Rata_rata"] + dev["SD"]).astype(float)
        bawah = (dev["Rata_rata"] - dev["SD"]).astype(float)
        fig.add_trace(go.Scatter(x=dev["Datetime"], y=atas, mode="lines", line=dict(width=0),
                                 hoverinfo="skip", showlegend=False))
        fig.add_trace(go.Scatter(x=dev["Datetime"], y=bawah, mode="lines", line=dict(width=0), fill="tonexty",
                                 fillcolor="rgba(235,104,52,0.13)", name="Rata-rata ± SD Phase I (deskriptif)",
                                 hoverinfo="skip"))
        fig.add_trace(go.Scatter(x=dev["Datetime"], y=dev["Rata_rata"].astype(float), mode="lines",
                                 name="Profil rata-rata per jam Phase I", line=dict(color=WARNA_PROFIL, width=1.5, dash="dot"),
                                 hovertemplate="Profil jam ini: %{y:.3f}<extra></extra>"))
    fig.add_trace(go.Scatter(
        x=dev["Datetime"], y=dev["Tekanan"], mode="lines", name=f"Tekanan aktual {titik}",
        line=dict(color=WARNA_UTAMA, width=2),
        customdata=dev["Selisih"].astype(float).round(3),
        hovertemplate="<b>%{x|" + FMT_WAKTU + "}</b><br>Tekanan = %{y:.3f}<br>Selisih dari profil = %{customdata:+.3f}<extra></extra>",
    ))
    s = dev[dev["Datetime"].isin(waktu_sinyal)]
    if not s.empty:
        fig.add_trace(go.Scatter(x=s["Datetime"], y=s["Tekanan"], mode="markers", name="Waktu sinyal MEWMA jaringan",
                                 marker=dict(size=8, color=WARNA_SINYAL, line=dict(width=1.5, color="white")),
                                 hovertemplate="<b>%{x|" + FMT_WAKTU + "}</b><br>Sinyal MEWMA jaringan<br>Tekanan = %{y:.3f}<extra></extra>"))
    return _tata(fig, tinggi, f"Tekanan ({satuan})" if satuan else "Tekanan")


def semua_tekanan(tek: pd.DataFrame, titik: list[str], semua_titik: list[str] | None = None,
                  eps: pd.DataFrame | None = None, penanda=None, satuan="", tinggi=380) -> go.Figure:
    """Garis tekanan beberapa titik. Warna mengikuti urutan `semua_titik` (titik jaringan) agar konsisten."""
    warna = warna_titik(semua_titik or titik)
    fig = go.Figure()
    _arsir_episode(fig, eps)
    for t in titik:
        fig.add_trace(go.Scatter(x=tek["Datetime"], y=tek[t], mode="lines", name=t,
                                 line=dict(color=warna[t], width=2),
                                 hovertemplate=f"{t}: " + "%{y:.3f}<extra></extra>"))
    if penanda is not None:
        fig.add_vline(x=pd.Timestamp(penanda), line=dict(color=WARNA_NETRAL, width=1.5, dash="dot"))
    return _tata(fig, tinggi, f"Tekanan ({satuan})" if satuan else "Tekanan").update_layout(hovermode="x unified")


def dominan(df: pd.DataFrame, tinggi=None) -> go.Figure:
    d = df.iloc[::-1]
    fig = go.Figure(go.Bar(
        x=d["Episode"], y=d["Titik"], orientation="h", marker=dict(color=WARNA_UTAMA, cornerradius=4),
        text=[f"{v} episode" for v in d["Episode"]], textposition="outside", cliponaxis=False,
        hovertemplate="%{y}: %{x} episode<extra></extra>",
    ))
    fig.update_xaxes(visible=False, range=[0, max(1, d["Episode"].max()) * 1.25])
    return _tata(fig, tinggi or 90 + 34 * len(d), legend=False)


def korelasi(corr: pd.DataFrame, tinggi=None) -> go.Figure:
    teks = [[fmt_angka(v, 3) for v in baris] for baris in corr.values]
    fig = go.Figure(go.Heatmap(
        z=corr.values, x=corr.columns, y=corr.index, zmin=-1, zmax=1, text=teks, texttemplate="%{text}",
        colorscale=[[0, "#e34948"], [0.5, "#f0efec"], [1, "#2a78d6"]],
        colorbar=dict(title="r"), hovertemplate="%{y} – %{x}<br>r = %{text}<extra></extra>",
    ))
    fig.update_yaxes(autorange="reversed")
    return _tata(fig, tinggi or max(320, 120 + 60 * len(corr)), legend=False)


def kontribusi(kon: pd.DataFrame, titik: list[str], tinggi=300) -> go.Figure:
    fig = go.Figure(go.Heatmap(
        z=kon[titik].T.values, x=kon["Datetime"], y=titik,
        colorscale=[[0, "#cde2fb"], [0.5, "#3987e5"], [1, "#0d366b"]],
        colorbar=dict(title="Kontribusi"),
        hovertemplate="%{x|" + FMT_WAKTU + "}<br>%{y}: %{z:.3f}<extra></extra>",
    ))
    fig.update_yaxes(autorange="reversed")
    return _tata(fig, max(tinggi, 100 + 40 * len(titik)), legend=False)
