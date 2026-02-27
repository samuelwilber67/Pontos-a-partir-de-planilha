import io
import re
from typing import Dict, Optional, Tuple

import folium
import pandas as pd
import simplekml

FOLIUM_COLORS = [
    "red",
    "blue",
    "green",
    "purple",
    "orange",
    "darkred",
    "cadetblue",
    "darkblue",
    "darkgreen",
    "darkpurple",
    "pink",
    "gray",
    "black",
    "lightblue",
    "lightgreen",
    "lightgray",
]


def validate_df(df: pd.DataFrame) -> Dict[str, str]:
    required = [
        "trecho_nome",
        "extensao",
        "inicio_lat_gms",
        "inicio_lon_gms",
        "fim_lat_gms",
        "fim_lon_gms",
    ]

    missing = [c for c in required if c not in df.columns]
    if missing:
        return {"valid": False, "message": f"Planilha inválida: faltam colunas obrigatórias: {missing}"}

    try:
        df["extensao"] = pd.to_numeric(df["extensao"])
    except Exception:
        return {"valid": False, "message": "Coluna `extensao` precisa ser numérica."}

    coord_cols = ["inicio_lat_gms", "inicio_lon_gms", "fim_lat_gms", "fim_lon_gms"]
    for c in coord_cols:
        if df[c].isna().any():
            return {"valid": False, "message": f"Coluna `{c}` contém valores vazios."}
        df[c] = df[c].astype(str)

    df["trecho_nome"] = df["trecho_nome"].astype(str)
    return {"valid": True, "message": "OK"}


def _normalize_gms_text(s: str) -> str:
    s = s.strip()
    s = s.replace("º", "°")
    s = s.replace("’", "'").replace("′", "'")
    s = s.replace("”", '"').replace("″", '"')
    s = s.replace(",", " ")
    s = re.sub(r"\s+", " ", s)
    return s


def parse_gms(gms: str) -> Optional[Tuple[int, int, float, str]]:
    if not isinstance(gms, str):
        return None

    s = _normalize_gms_text(gms)

    m_dir = re.search(r"\b([NSEW])\b$", s, flags=re.IGNORECASE)
    if not m_dir:
        return None

    direction = m_dir.group(1).upper()
    s_wo_dir = s[: m_dir.start()].strip()

    nums = re.findall(r"[-+]?\d+(?:\.\d+)?", s_wo_dir)
    if len(nums) < 3:
        return None

    try:
        deg = int(float(nums[0]))
        minute = int(float(nums[1]))
        sec = float(nums[2])
    except Exception:
        return None

    if minute < 0 or minute >= 60:
        return None
    if sec < 0 or sec >= 60:
        return None

    return deg, minute, sec, direction


def gms_to_decimal(gms: str) -> Optional[float]:
    parsed = parse_gms(gms)
    if not parsed:
        return None

    deg, minute, sec, direction = parsed
    dec = abs(deg) + (minute / 60.0) + (sec / 3600.0)

    if direction in ("S", "W"):
        dec = -dec

    return dec


def _make_point_label(prefix: str, lat_gms: str, lon_gms: str, trecho_nome: str, extensao) -> str:
    return f"{prefix} {lat_gms}, {lon_gms} - Trecho {trecho_nome} (Extensão: {extensao})"


def build_folium_map(df: pd.DataFrame) -> folium.Map:
    center_lat = pd.concat([df["inicio_lat_dec"], df["fim_lat_dec"]]).mean()
    center_lon = pd.concat([df["inicio_lon_dec"], df["fim_lon_dec"]]).mean()

    m = folium.Map(location=[center_lat, center_lon], zoom_start=11, tiles="OpenStreetMap")

    for i, row in df.reset_index(drop=True).iterrows():
        color = FOLIUM_COLORS[i % len(FOLIUM_COLORS)]
        trecho_nome = row["trecho_nome"]
        extensao = row["extensao"]

        start_label = _make_point_label(
            "Início do Trecho",
            row["inicio_lat_gms"],
            row["inicio_lon_gms"],
            trecho_nome,
            extensao,
        )
        end_label = _make_point_label(
            "Final do Trecho",
            row["fim_lat_gms"],
            row["fim_lon_gms"],
            trecho_nome,
            extensao,
        )

        start_lat, start_lon = row["inicio_lat_dec"], row["inicio_lon_dec"]
        end_lat, end_lon = row["fim_lat_dec"], row["fim_lon_dec"]

        folium.Marker(
            location=[start_lat, start_lon],
            tooltip=start_label,
            popup=start_label,
            icon=folium.Icon(color=color, icon="play", prefix="fa"),
        ).add_to(m)

        folium.Marker(
            location=[end_lat, end_lon],
            tooltip=end_label,
            popup=end_label,
            icon=folium.Icon(color=color, icon="flag-checkered", prefix="fa"),
        ).add_to(m)

        folium.PolyLine(
            locations=[[start_lat, start_lon], [end_lat, end_lon]],
            color=color,
            weight=4,
            opacity=0.8,
            tooltip=f"Trecho {trecho_nome} (Extensão: {extensao})",
        ).add_to(m)

    bounds = []
    for _, row in df.iterrows():
        bounds.append([row["inicio_lat_dec"], row["inicio_lon_dec"]])
        bounds.append([row["fim_lat_dec"], row["fim_lon_dec"]])
    if bounds:
        m.fit_bounds(bounds, padding=(30, 30))

    return m


def build_kmz_bytes(df: pd.DataFrame) -> bytes:
    kml = simplekml.Kml()

    for _, row in df.reset_index(drop=True).iterrows():
        trecho_nome = row["trecho_nome"]
        extensao = row["extensao"]

        start_label = _make_point_label(
            "Início do Trecho",
            row["inicio_lat_gms"],
            row["inicio_lon_gms"],
            trecho_nome,
            extensao,
        )
        end_label = _make_point_label(
            "Final do Trecho",
            row["fim_lat_gms"],
            row["fim_lon_gms"],
            trecho_nome,
            extensao,
        )

        start_lon, start_lat = row["inicio_lon_dec"], row["inicio_lat_dec"]
        end_lon, end_lat = row["fim_lon_dec"], row["fim_lat_dec"]

        p_start = kml.newpoint(name=start_label)
        p_start.coords = [(start_lon, start_lat, 0)]

        p_end = kml.newpoint(name=end_label)
        p_end.coords = [(end_lon, end_lat, 0)]

        ls = kml.newlinestring(name=f"Trecho {trecho_nome} (Extensão: {extensao})")
        ls.coords = [(start_lon, start_lat, 0), (end_lon, end_lat, 0)]

    buf = io.BytesIO()
    kml.savekmz(buf)
    buf.seek(0)
    return buf.read()
