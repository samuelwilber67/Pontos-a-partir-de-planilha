import io

import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

from utils import (
    EXPECTED_COLUMNS,
    build_map,
    export_kmz,
    parse_trechos,
    sample_dataframe,
)

st.set_page_config(page_title="Trechos em Mapa (GMS → Decimal)", layout="wide")

st.title("Visualizador de Trechos (CSV) – Mapa + Exportação KMZ")

st.write(
    "Faça upload de um CSV com trechos (início/fim em GMS). "
    "O app mostra os pontos no mapa e permite exportar um KMZ para Google Earth."
)

with st.expander("Formato esperado do CSV (colunas obrigatórias)", expanded=True):
    st.write("O arquivo deve conter exatamente estas colunas (nomes iguais):")
    st.code("\n".join(EXPECTED_COLUMNS), language="text")

    st.write("Você pode baixar um CSV de exemplo para testar:")
    df_ex = sample_dataframe()
    csv_bytes = df_ex.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="Baixar CSV de exemplo",
        data=csv_bytes,
        file_name="exemplo_trechos.csv",
        mime="text/csv",
    )

uploaded = st.file_uploader("Upload do CSV", type=["csv"])

if not uploaded:
    st.stop()

try:
    # Lê CSV com tolerância a separadores comuns
    content = uploaded.getvalue()
    # Tenta UTF-8; se falhar, tenta latin-1
    try:
        df = pd.read_csv(io.BytesIO(content))
    except UnicodeDecodeError:
        df = pd.read_csv(io.BytesIO(content), encoding="latin-1")

    trechos = parse_trechos(df)

    col1, col2 = st.columns([2, 1])

    with col2:
        st.subheader("Exportação")
        kmz_bytes, kmz_filename = export_kmz(trechos, kmz_name="trechos.kmz")
        st.download_button(
            label="Baixar KMZ",
            data=kmz_bytes,
            file_name=kmz_filename,
            mime="application/vnd.google-earth.kmz",
        )

        st.caption("O KMZ contém pontos (início/fim) e a linha de cada trecho.")

    with col1:
        st.subheader("Mapa interativo")
        m = build_map(trechos, tiles="OpenStreetMap")
        st_folium(m, width=None, height=650)

except Exception as e:
    st.error("Não foi possível processar o arquivo.")
    st.exception(e)
