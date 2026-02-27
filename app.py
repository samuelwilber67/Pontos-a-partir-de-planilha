# app.py
from __future__ import annotations

import hashlib
from typing import Tuple

import folium
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

from utils import clean_data

REQUIREMENTS_TXT = """streamlit
pandas
folium
streamlit-folium
"""


def _color_for_trecho(nome_trecho: str) -> str:
    """
    Gera uma cor HEX estável por trecho (mesmo nome -> mesma cor),
    para manter consistência visual.
    """
    h = hashlib.md5(nome_trecho.encode("utf-8")).hexdigest()
    # pega 6 hex chars para formar #RRGGBB
    return f"#{h[:6]}"


def _center_from_df(df: pd.DataFrame) -> Tuple[float, float]:
    lat_mean = pd.concat([df["lat_inicio_dd"], df["lat_fim_dd"]]).mean()
    lon_mean = pd.concat([df["lon_inicio_dd"], df["lon_fim_dd"]]).mean()
    return float(lat_mean), float(lon_mean)


def _add_point(
    m: folium.Map,
    lat: float,
    lon: float,
    color_hex: str,
    tooltip_text: str,
    popup_html: str,
):
    folium.CircleMarker(
        location=(lat, lon),
        radius=6,
        color=color_hex,
        fill=True,
        fill_color=color_hex,
        fill_opacity=0.95,
        tooltip=tooltip_text,
        popup=folium.Popup(popup_html, max_width=450),
    ).add_to(m)


st.set_page_config(page_title="Mapa de Trechos (GMS → Decimal)", layout="wide")

st.title("Mapa de Trechos (CSV com coordenadas em GMS)")

st.markdown(
    """
Envie um **CSV** com 6 colunas (A–F) ou com cabeçalho equivalente:

- **A:** Nome do Trecho  
- **B:** Extensão do Trecho (numérico)  
- **C:** Latitude Início (GMS)  
- **D:** Longitude Início (GMS)  
- **E:** Latitude Fim (GMS)  
- **F:** Longitude Fim (GMS)

**Formatos de GMS aceitos (exemplos):**
- `40° 26' 46'' N`
- `40 26 46 N`
- `40:26:46N`
- `-23 33 12` (sem hemisfério, usando sinal)

**Hemisférios:**
- Latitude: `N` ou `S`
- Longitude: `E` ou `W`
"""
)

with st.expander("requirements.txt (copie e cole no seu repositório)", expanded=False):
    st.code(REQUIREMENTS_TXT, language="text")

col_left, col_right = st.columns([1, 2], gap="large")

with col_left:
    uploaded = st.file_uploader("Upload do arquivo CSV", type=["csv"])

    draw_line = st.checkbox("Desenhar linha ligando início e fim", value=True)
    fit_bounds = st.checkbox("Ajustar zoom para enquadrar todos os pontos", value=True)

    st.caption(
        "Dica: se seu CSV tiver cabeçalho, o app tenta reconhecer nomes comuns. "
        "Se não tiver, ele assume as colunas A–F por posição."
    )

with col_right:
    if not uploaded:
        st.info("Faça o upload do CSV para visualizar os trechos no mapa.")
        st.stop()

    try:
        # tenta ler com header; se falhar, lê sem header
        try:
            df_raw = pd.read_csv(uploaded)
        except Exception:
            uploaded.seek(0)
            df_raw = pd.read_csv(uploaded, header=None)

        result = clean_data(df_raw)
        df = result.df
        errors = result.errors

        st.subheader("Resumo do processamento")
        st.write(
            f"Linhas válidas: **{len(df)}** | Linhas ignoradas: **{len(errors)}**"
        )

        if errors:
            st.warning("Algumas linhas foram ignoradas por erros de formatação.")
            st.dataframe(pd.DataFrame(errors), use_container_width=True, hide_index=True)

        if df.empty:
            st.error("Nenhuma linha válida encontrada. Verifique o formato das colunas e das coordenadas.")
            st.stop()

        st.subheader("Prévia dos dados limpos")
        st.dataframe(
            df[
                [
                    "nome_trecho",
                    "extensao",
                    "lat_inicio",
                    "lon_inicio",
                    "lat_fim",
                    "lon_fim",
                    "lat_inicio_dd",
                    "lon_inicio_dd",
                    "lat_fim_dd",
                    "lon_fim_dd",
                ]
            ],
            use_container_width=True,
            hide_index=True,
        )

        center_lat, center_lon = _center_from_df(df)
        m = folium.Map(location=(center_lat, center_lon), zoom_start=6, control_scale=True)

        bounds = []

        for _, row in df.iterrows():
            nome = row["nome_trecho"]
            ext = row["extensao"]
            color = _color_for_trecho(nome)

            # rótulos exigidos (inclui GMS original + nome do trecho + extensão)
            inicio_label = (
                f"Início do Trecho {row['lat_inicio']}, {row['lon_inicio']} - Trecho {nome} "
                f"(Extensão: {ext})"
            )
            fim_label = (
                f"Final do Trecho {row['lat_fim']}, {row['lon_fim']} - Trecho {nome} "
                f"(Extensão: {ext})"
            )

            # popup um pouco mais “legível” (sem perder o padrão)
            inicio_popup = (
                f"<b>Início do Trecho</b><br>"
                f"{row['lat_inicio']}, {row['lon_inicio']}<br>"
                f"<b>Trecho:</b> {nome}<br>"
                f"<b>Extensão:</b> {ext}"
            )
            fim_popup = (
                f"<b>Final do Trecho</b><br>"
                f"{row['lat_fim']}, {row['lon_fim']}<br>"
                f"<b>Trecho:</b> {nome}<br>"
                f"<b>Extensão:</b> {ext}"
            )

            lat_i, lon_i = row["lat_inicio_dd"], row["lon_inicio_dd"]
            lat_f, lon_f = row["lat_fim_dd"], row["lon_fim_dd"]

            _add_point(
                m,
                lat=lat_i,
                lon=lon_i,
                color_hex=color,
                tooltip_text=inicio_label,
                popup_html=inicio_popup,
            )
            _add_point(
                m,
                lat=lat_f,
                lon=lon_f,
                color_hex=color,
                tooltip_text=fim_label,
                popup_html=fim_popup,
            )

            bounds.extend([(lat_i, lon_i), (lat_f, lon_f)])

            if draw_line:
                folium.PolyLine(
                    locations=[(lat_i, lon_i), (lat_f, lon_f)],
                    color=color,
                    weight=3,
                    opacity=0.9,
                    tooltip=f"Trecho {nome} (Extensão: {ext})",
                ).add_to(m)

        if fit_bounds and bounds:
            m.fit_bounds(bounds)

        st.subheader("Mapa")
        st_folium(m, use_container_width=True, height=650)

    except Exception as e:
        st.error(f"Erro ao processar o arquivo: {e}")
