# utils.py
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd


# ----------------------------
# Parsing de coordenadas (GMS -> graus decimais)
# ----------------------------

_DMS_REGEX = re.compile(
    r"""
    ^\s*
    (?P<deg>[+-]?\d+(?:[.,]\d+)?)      # graus
    (?:\s*[°\s]\s*|\s+)?
    (?P<min>\d+(?:[.,]\d+)?)?         # minutos (opcional)
    (?:\s*[\'’′\s]\s*|\s+)?
    (?P<sec>\d+(?:[.,]\d+)?)?         # segundos (opcional)
    (?:\s*(?:\"|”|″)\s*)?
    (?P<hem>[NSEWnsew])?              # hemisfério (opcional)
    \s*$
    """,
    re.VERBOSE,
)


def _to_float(x: str) -> float:
    return float(x.replace(",", "."))


def parse_dms(dms_str: Any, expected: str) -> Optional[float]:
    """
    Converte coordenadas em GMS (DMS) para graus decimais.

    Aceita variações como:
    - 40° 26' 46'' N
    - 40 26 46 N
    - 40:26:46N
    - 40°26'46\"N
    - 40 26 N (sem segundos)
    - 40 N (apenas graus)

    Regras:
    - Se houver hemisfério (N/S/E/W), ele define o sinal.
    - Se não houver hemisfério, aceita sinal negativo/positivo em graus.
    - expected deve ser "lat" ou "lon" para validar hemisférios.
    """
    if dms_str is None or (isinstance(dms_str, float) and pd.isna(dms_str)):
        return None

    s = str(dms_str).strip()
    if not s:
        return None

    # normaliza separadores comuns
    s = s.replace(":", " ")
    s = s.replace("º", "°")
    s = re.sub(r"\s+", " ", s)

    m = _DMS_REGEX.match(s)
    if not m:
        return None

    deg_raw = m.group("deg")
    min_raw = m.group("min")
    sec_raw = m.group("sec")
    hem_raw = m.group("hem")

    deg = _to_float(deg_raw)
    minutes = _to_float(min_raw) if min_raw is not None else 0.0
    seconds = _to_float(sec_raw) if sec_raw is not None else 0.0
    hem = hem_raw.upper() if hem_raw else None

    # valida faixas
    if minutes < 0 or minutes >= 60 or seconds < 0 or seconds >= 60:
        return None

    decimal = abs(deg) + (minutes / 60.0) + (seconds / 3600.0)

    # sinal por hemisfério (se existir), senão pelo sinal em deg
    if hem:
        if expected == "lat" and hem not in ("N", "S"):
            return None
        if expected == "lon" and hem not in ("E", "W"):
            return None
        if hem in ("S", "W"):
            decimal = -decimal
    else:
        if deg < 0:
            decimal = -decimal

    # valida range final
    if expected == "lat" and not (-90 <= decimal <= 90):
        return None
    if expected == "lon" and not (-180 <= decimal <= 180):
        return None

    return decimal


# ----------------------------
# Limpeza/validação do CSV
# ----------------------------

EXPECTED_COLUMNS = {
    "nome_trecho": ["nome_trecho", "trecho", "nome", "nome do trecho"],
    "extensao": ["extensao", "extensão", "comprimento", "length", "km", "m"],
    "lat_inicio": ["lat_inicio", "latitude_inicio", "lat ini", "inicio_lat", "lat start"],
    "lon_inicio": ["lon_inicio", "longitude_inicio", "lon ini", "inicio_lon", "lon start"],
    "lat_fim": ["lat_fim", "latitude_fim", "lat fim", "fim_lat", "lat end"],
    "lon_fim": ["lon_fim", "longitude_fim", "lon fim", "fim_lon", "lon end"],
}


@dataclass
class CleanResult:
    df: pd.DataFrame
    errors: List[Dict[str, Any]]


def _normalize_header(h: str) -> str:
    h = str(h).strip().lower()
    h = h.replace("\ufeff", "")  # BOM
    h = re.sub(r"\s+", " ", h)
    return h


def _coerce_extensao(x: Any) -> Optional[float]:
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return None
    if isinstance(x, (int, float)) and not pd.isna(x):
        return float(x)

    s = str(x).strip()
    if not s:
        return None

    # extrai o primeiro número (aceita "12,3 km", "1000m", etc.)
    m = re.search(r"[+-]?\d+(?:[.,]\d+)?", s)
    if not m:
        return None
    try:
        return float(m.group(0).replace(",", "."))
    except ValueError:
        return None


def standardize_dataframe(df_raw: pd.DataFrame) -> pd.DataFrame:
    """
    Tenta padronizar as colunas para:
    nome_trecho, extensao, lat_inicio, lon_inicio, lat_fim, lon_fim

    Estratégia:
    1) Se tiver cabeçalho com nomes reconhecíveis -> mapeia por nomes
    2) Caso contrário -> assume A..F por posição (primeiras 6 colunas)
    """
    df = df_raw.copy()

    # Se o CSV veio com header, pandas tende a ter colunas nomeadas (strings)
    # Se vier sem header, colunas serão inteiros (0..n-1).
    has_string_header = all(isinstance(c, str) for c in df.columns)

    if has_string_header:
        norm_cols = {_normalize_header(c): c for c in df.columns}
        mapping: Dict[str, str] = {}

        for target, aliases in EXPECTED_COLUMNS.items():
            found = None
            for a in aliases:
                a_norm = _normalize_header(a)
                if a_norm in norm_cols:
                    found = norm_cols[a_norm]
                    break
            if found:
                mapping[target] = found

        if len(mapping) == 6:
            df = df.rename(columns={mapping[k]: k for k in mapping})
            return df[list(mapping.keys())]

    # fallback por posição A..F
    if df.shape[1] < 6:
        raise ValueError("O arquivo precisa ter pelo menos 6 colunas (A–F).")

    df = df.iloc[:, :6].copy()
    df.columns = ["nome_trecho", "extensao", "lat_inicio", "lon_inicio", "lat_fim", "lon_fim"]
    return df


def clean_data(df_raw: pd.DataFrame) -> CleanResult:
    """
    Valida e converte dados. Linhas inválidas são ignoradas e registradas em errors.
    Retorna df limpo com colunas originais + colunas *_dd (graus decimais).
    """
    df_std = standardize_dataframe(df_raw)

    clean_rows: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []

    for i, row in df_std.iterrows():
        linha = int(i) + 1  # 1-based para ser mais amigável

        nome = row.get("nome_trecho")
        if nome is None or (isinstance(nome, float) and pd.isna(nome)) or str(nome).strip() == "":
            errors.append({"linha": linha, "erro": "nome_trecho vazio"})
            continue
        nome = str(nome).strip()

        ext = _coerce_extensao(row.get("extensao"))
        if ext is None:
            errors.append({"linha": linha, "erro": "extensao inválida"})
            continue

        lat_i = row.get("lat_inicio")
        lon_i = row.get("lon_inicio")
        lat_f = row.get("lat_fim")
        lon_f = row.get("lon_fim")

        lat_i_dd = parse_dms(lat_i, expected="lat")
        lon_i_dd = parse_dms(lon_i, expected="lon")
        lat_f_dd = parse_dms(lat_f, expected="lat")
        lon_f_dd = parse_dms(lon_f, expected="lon")

        if any(v is None for v in (lat_i_dd, lon_i_dd, lat_f_dd, lon_f_dd)):
            errors.append({"linha": linha, "erro": "coordenadas GMS inválidas ou fora de faixa"})
            continue

        clean_rows.append(
            {
                "nome_trecho": nome,
                "extensao": ext,
                "lat_inicio": str(lat_i).strip(),
                "lon_inicio": str(lon_i).strip(),
                "lat_fim": str(lat_f).strip(),
                "lon_fim": str(lon_f).strip(),
                "lat_inicio_dd": lat_i_dd,
                "lon_inicio_dd": lon_i_dd,
                "lat_fim_dd": lat_f_dd,
                "lon_fim_dd": lon_f_dd,
            }
        )

    df_clean = pd.DataFrame(clean_rows)
    return CleanResult(df=df_clean, errors=errors)
