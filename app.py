import os
import streamlit as st
import pandas as pd

from streamlit_folium import st_folium

from utils import (
    validate_df,
    gms_to_decimal,
    build_folium_map,
    build_kmz_bytes,
)

st.set_page_config(page_title="Visualizador de Trechos", layout="wide")
st.title("Mapa de Trechos a partir de Planilha (CSV/XLS/XLSX)")

st.markdown(
    """
**O que este app faz**
- Você envia um **CSV**, **XLS** ou **XLSX** com trechos (nome, extensão e coordenadas em **GMS**).
- O app converte **GMS → graus decimais** e mostra no **mapa interativo**.
- Você pode **exportar KMZ** (Google Earth) com pontos e linhas.

**Formato GMS aceito**
- Exemplos:
  - `40° 26' 46" N`
  - `40 26 46 N`
  - `79°58'56"W`
- Direção obrigatória no final: `N`, `S`, `E`, `W`.
"""
)

with st.sidebar:
    st.header("Upload")

    uploaded = st.file_uploader(
        "Envie um arquivo CSV, XLS ou XLSX",
        type=["csv", "xls", "xlsx"],
    )

    st.markdown(
        """
**Colunas obrigatórias**
- `trecho_nome`
- `extensao`
- `inicio_lat_gms`
- `inicio_lon_gms`
- `fim_lat_gms`
- `fim_lon_gms`
"""
    )

if not uploaded:
    st.info("Envie um arquivo para começar.")
    st.stop()

name = (uploaded.name or "").lower()
_, ext = os.path.splitext(name)

try:
    if ext == ".csv":
        df = pd.read_csv(uploaded)
    elif ext == ".xls":
        # Excel antigo
        df = pd.read_excel(uploaded, engine="xlrd")
    elif ext == ".xlsx":
        # Excel moderno
        df = pd.read_excel(uploaded, engine="openpyxl")
    else:
        st.error("Formato não suportado. Envie .csv, .xls ou .xlsx.")
        st.stop()
except Exception:
    st.error(
        "Não consegui ler o arquivo. Verifique se o arquivo está íntegro e se as dependências "
        "estão instaladas (`xlrd` para .xls e `openpyxl` para .xlsx)."
    )
    st.stop()

val = validate_df(df)
if not val["valid"]:
    st.error(val["message"])
    st.stop()

df = df.copy()
df["inicio_lat_dec"] = df["inicio_lat_gms"].apply(gms_to_decimal)
df["inicio_lon_dec"] = df["inicio_lon_gms"].apply(gms_to_decimal)
df["fim_lat_dec"] = df["fim_lat_gms"].apply(gms_to_decimal)
df["fim_lon_dec"] = df["fim_lon_gms"].apply(gms_to_decimal)

bad = df[
    df[["inicio_lat_dec", "inicio_lon_dec", "fim_lat_dec", "fim_lon_dec"]].isna().any(axis=1)
]
if not bad.empty:
    st.error(
        "Há coordenadas GMS inválidas (não foi possível converter). "
        "Corrija a planilha e envie novamente. Ex.: `40° 26' 46\" N`."
    )
    st.write("Linhas com erro:")
    st.dataframe(bad)
    st.stop()

col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("Prévia dos dados")
    st.dataframe(
        df[
            [
                "trecho_nome",
                "extensao",
                "inicio_lat_gms",
                "inicio_lon_gms",
                "fim_lat_gms",
                "fim_lon_gms",
            ]
        ]
    )

with col2:
    st.subheader("Exportação")
    kmz_bytes = build_kmz_bytes(df)
    st.download_button(
        label="Baixar KMZ",
        data=kmz_bytes,
        file_name="trechos.kmz",
        mime="application/vnd.google-earth.kmz",
    )

st.subheader("Mapa")
m = build_folium_map(df)
st_folium(m, use_container_width=True, height=650)
