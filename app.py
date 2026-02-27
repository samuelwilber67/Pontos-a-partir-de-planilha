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

st.title("Mapa de Trechos a partir de Planilha (CSV)")

st.markdown(
    """
**O que este app faz**
- Você envia um **CSV** com trechos (nome, extensão e coordenadas em **GMS**).
- O app converte **GMS → graus decimais** e mostra no **mapa interativo**.
- Você pode **exportar KMZ** (Google Earth) com pontos e linhas.

**Formato GMS aceito (robusto)**
- Exemplos válidos:
  - `40° 26' 46" N`
  - `40 26 46 N`
  - `79°58'56"W`
- Direção obrigatória no final: `N`, `S`, `E`, `W`.
"""
)

with st.sidebar:
    st.header("Upload")
    uploaded = st.file_uploader("Envie um arquivo CSV", type=["csv"])

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
    st.info("Envie um CSV para começar.")
    st.stop()

try:
    df = pd.read_csv(uploaded)
except Exception:
    st.error("Não consegui ler o CSV. Verifique separador/encoding e tente novamente.")
    st.stop()

val = validate_df(df)
if not val["valid"]:
    st.error(val["message"])
    st.stop()

# Converte GMS para decimal (lat/lon início/fim)
df = df.copy()
df["inicio_lat_dec"] = df["inicio_lat_gms"].apply(gms_to_decimal)
df["inicio_lon_dec"] = df["inicio_lon_gms"].apply(gms_to_decimal)
df["fim_lat_dec"] = df["fim_lat_gms"].apply(gms_to_decimal)
df["fim_lon_dec"] = df["fim_lon_gms"].apply(gms_to_decimal)

# Falhas de conversão
bad = df[
    df[["inicio_lat_dec", "inicio_lon_dec", "fim_lat_dec", "fim_lon_dec"]].isna().any(axis=1)
]
if not bad.empty:
    st.error(
        "Há coordenadas GMS inválidas (não foi possível converter). "
        "Corrija o CSV e envie novamente. Ex.: `40° 26' 46\" N`."
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
    try:
        kmz_bytes = build_kmz_bytes(df)
        st.download_button(
            label="Baixar KMZ",
            data=kmz_bytes,
            file_name="trechos.kmz",
            mime="application/vnd.google-earth.kmz",
        )
    except Exception:
        st.error("Falha ao gerar KMZ. Verifique os dados e dependências.")
        st.stop()

st.subheader("Mapa")
m = build_folium_map(df)
st_folium(m, use_container_width=True, height=650)
