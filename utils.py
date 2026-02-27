import io
import re
import zipfile
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

import pandas as pd
import folium


# ----------------------------
# Modelos / tipos auxiliares
# ----------------------------

@dataclass
class CoordGMS:
    """Representa uma coordenada em GMS + hemisfério, preservando o texto original."""
    graus: float
    minutos: float
    segundos: float
    hemisferio: str  # N, S, E, W
    original: str    # string original (para tooltip)

    def to_decimal(self) -> float:
        val = abs(self.graus) + (self.minutos / 60.0) + (self.segundos / 3600.0)
        if self.hemisferio.upper() in ("S", "W"):
            val *= -1.0
        return val


@dataclass
class Trecho:
    nome: str
    extensao: float
    inicio_lat: CoordGMS
    inicio_lon: CoordGMS
    fim_lat: CoordGMS
    fim_lon: CoordGMS


# ----------------------------
# Parsing de GMS
# ----------------------------

_GMS_RE = re.compile(
    r"""
    ^\s*
    (?P<deg>-?\d+(?:\.\d+)?)\s*(?:°|º|d|deg)?\s*[, ]*\s*
    (?P<min>\d+(?:\.\d+)?)\s*(?:'|’|m|min)?\s*[, ]*\s*
    (?P<sec>\d+(?:\.\d+)?)\s*(?:"|”|''|s|sec)?\s*
    (?P<hem>[NSEW])?
    \s*$
    """,
    re.IGNORECASE | re.VERBOSE,
)

_HEM_RE = re.compile(r"\b([NSEW])\b", re.IGNORECASE)


def _normalize_gms_string(value: str) -> str:
    """Normaliza aspas e símbolos comuns para facilitar parsing."""
    s = str(value).strip()
    s = s.replace("”", '"').replace("“", '"').replace("´", "'").replace("’", "'")
    s = s.replace("º", "°")
    # Alguns CSVs vêm com duplas aspas escapadas
    s = s.replace("''", '"')
    return s


def parse_gms(value: str, default_hemisphere: Optional[str] = None) -> CoordGMS:
    """
    Aceita formatos como:
      - 40° 26' 46" N
      - 40 26 46 N
      - 40,26,46 N
      - 40 26 46 (hemisfério inferido por default_hemisphere)
    """
    if value is None or (isinstance(value, float) and pd.isna(value)):
        raise ValueError("Coordenada vazia.")

    raw = _normalize_gms_string(str(value))

    # Tenta extrair hemisfério de qualquer lugar da string
    hem_match = _HEM_RE.search(raw)
    hem = hem_match.group(1).upper() if hem_match else (default_hemisphere.upper() if default_hemisphere else None)

    # Remove o hemisfério antes do parse principal, se necessário
    raw_no_hem = re.sub(r"\b[NSEW]\b", "", raw, flags=re.IGNORECASE).strip()

    m = _GMS_RE.match(raw_no_hem if hem else raw)
    if not m:
        # Tentativa extra: separar por espaços/virgulas e pegar 3 números
        tokens = re.split(r"[,\s]+", raw_no_hem if hem else raw)
        nums = []
        for t in tokens:
            if re.fullmatch(r"-?\d+(?:\.\d+)?", t):
                nums.append(t)
        if len(nums) >= 3:
            deg, minute, sec = nums[0], nums[1], nums[2]
        else:
            raise ValueError(f"Formato GMS não reconhecido: '{value}'")
    else:
        deg = m.group("deg")
        minute = m.group("min")
        sec = m.group("sec")
        hem = hem or (m.group("hem").upper() if m.group("hem") else None)

    if hem is None:
        raise ValueError(f"Hemisfério ausente (N/S/E/W) em: '{value}'")

    g = float(deg)
    mi = float(minute)
    se = float(sec)

    if mi < 0 or mi >= 60 or se < 0 or se >= 60:
        raise ValueError(f"Minutos/segundos fora do intervalo em: '{value}'")

    # Preserva uma forma “bonita” para tooltip
    original_fmt = format_gms_for_label(g, mi, se, hem)

    return CoordGMS(graus=g, minutos=mi, segundos=se, hemisferio=hem, original=original_fmt)


def format_gms_for_label(g: float, m: float, s: float, hem: str) -> str:
    g_abs = abs(g)
    return f"{int(round(g_abs))}° {int(round(m))}' {float(s):.0f}'' {hem.upper()}"


# ----------------------------
# Validação / leitura do CSV
# ----------------------------

EXPECTED_COLUMNS = [
    "Nome do Trecho",
    "Extensão do Trecho",
    "Início Lat (GMS)",
    "Início Lon (GMS)",
    "Fim Lat (GMS)",
    "Fim Lon (GMS)",
]


def validate_columns(df: pd.DataFrame) -> None:
    missing = [c for c in EXPECTED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(
            "Colunas ausentes no arquivo: "
            + ", ".join(missing)
            + ".\n\n"
            + "Colunas esperadas:\n- "
            + "\n- ".join(EXPECTED_COLUMNS)
        )


def parse_trechos(df: pd.DataFrame) -> List[Trecho]:
    """
    Converte o DataFrame em lista de Trecho, validando linha a linha.
    """
    validate_columns(df)

    trechos: List[Trecho] = []
    errors: List[str] = []

    for idx, row in df.iterrows():
        line = idx + 2  # considerando cabeçalho na linha 1
        try:
            nome = str(row["Nome do Trecho"]).strip()
            if not nome:
                raise ValueError("Nome do Trecho vazio.")

            extensao = float(row["Extensão do Trecho"])

            inicio_lat = parse_gms(row["Início Lat (GMS)"], default_hemisphere="S")
            inicio_lon = parse_gms(row["Início Lon (GMS)"], default_hemisphere="W")
            fim_lat = parse_gms(row["Fim Lat (GMS)"], default_hemisphere="S")
            fim_lon = parse_gms(row["Fim Lon (GMS)"], default_hemisphere="W")

            trechos.append(
                Trecho(
                    nome=nome,
                    extensao=extensao,
                    inicio_lat=inicio_lat,
                    inicio_lon=inicio_lon,
                    fim_lat=fim_lat,
                    fim_lon=fim_lon,
                )
            )
        except Exception as e:
            errors.append(f"Linha {line}: {e}")

    if errors:
        # Mostra até 20 para não poluir a UI
        msg = "Foram encontrados erros ao ler o arquivo:\n- " + "\n- ".join(errors[:20])
        if len(errors) > 20:
            msg += f"\n- ... e mais {len(errors) - 20} erro(s)."
        raise ValueError(msg)

    if not trechos:
        raise ValueError("Nenhum trecho válido foi encontrado no arquivo.")

    return trechos


# ----------------------------
# Mapa (Folium)
# ----------------------------

def _color_palette() -> List[str]:
    # Paleta simples e bem distinta
    return [
        "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
        "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf",
        "#00A6FB", "#F25F5C", "#70C1B3", "#FFE066", "#50514F",
    ]


def build_map(trechos: List[Trecho], tiles: str = "OpenStreetMap") -> folium.Map:
    # Centraliza no primeiro trecho (início)
    first = trechos[0]
    center = (first.inicio_lat.to_decimal(), first.inicio_lon.to_decimal())
    m = folium.Map(location=center, zoom_start=12, tiles=tiles, control_scale=True)

    palette = _color_palette()

    for i, t in enumerate(trechos):
        color = palette[i % len(palette)]

        inicio = (t.inicio_lat.to_decimal(), t.inicio_lon.to_decimal())
        fim = (t.fim_lat.to_decimal(), t.fim_lon.to_decimal())

        tooltip_inicio = (
            f"Início do Trecho {t.inicio_lat.original}, {t.inicio_lon.original} - Trecho {t.nome} "
            f"(Extensão: {t.extensao})"
        )
        tooltip_fim = (
            f"Final do Trecho {t.fim_lat.original}, {t.fim_lon.original} - Trecho {t.nome} "
            f"(Extensão: {t.extensao})"
        )

        # Marcadores
        folium.CircleMarker(
            location=inicio,
            radius=6,
            color=color,
            fill=True,
            fill_color=color,
            fill_opacity=0.9,
            tooltip=tooltip_inicio,
            popup=tooltip_inicio,
        ).add_to(m)

        folium.CircleMarker(
            location=fim,
            radius=6,
            color=color,
            fill=True,
            fill_color=color,
            fill_opacity=0.9,
            tooltip=tooltip_fim,
            popup=tooltip_fim,
        ).add_to(m)

        # Linha conectando início -> fim (associação lógica do trecho)
        folium.PolyLine(
            locations=[inicio, fim],
            color=color,
            weight=3,
            opacity=0.8,
            tooltip=f"Trecho {t.nome} (Extensão: {t.extensao})",
        ).add_to(m)

    folium.LayerControl(collapsed=True).add_to(m)
    return m


# ----------------------------
# Exportação KMZ (KML + zip)
# ----------------------------

def export_kmz(trechos: List[Trecho], kmz_name: str = "trechos.kmz") -> Tuple[bytes, str]:
    """
    Gera um KMZ em memória (bytes) com:
      - Pasta por trecho
      - Placemark início e fim
      - LineString ligando início-fim
    Retorna (bytes, filename).
    """
    try:
        import simplekml
    except Exception as e:
        raise RuntimeError(
            "Dependência 'simplekml' não encontrada. Inclua no requirements.txt: simplekml>=1.3.6"
        ) from e

    kml = simplekml.Kml()
    palette = _color_palette()

    for i, t in enumerate(trechos):
        color_hex = palette[i % len(palette)]
        # KML usa AABBGGRR; vamos forçar alpha FF e converter #RRGGBB
        rrggbb = color_hex.lstrip("#")
        aabbggrr = "ff" + rrggbb[4:6] + rrggbb[2:4] + rrggbb[0:2]

        folder = kml.newfolder(name=t.nome)

        ini_lat = t.inicio_lat.to_decimal()
        ini_lon = t.inicio_lon.to_decimal()
        fim_lat = t.fim_lat.to_decimal()
        fim_lon = t.fim_lon.to_decimal()

        desc_common = f"Trecho: {t.nome}\nExtensão: {t.extensao}"

        p_ini = folder.newpoint(
            name=f"Início - {t.nome}",
            coords=[(ini_lon, ini_lat)],
        )
        p_ini.description = (
            f"Início do Trecho {t.inicio_lat.original}, {t.inicio_lon.original}\n{desc_common}"
        )

        p_fim = folder.newpoint(
            name=f"Final - {t.nome}",
            coords=[(fim_lon, fim_lat)],
        )
        p_fim.description = (
            f"Final do Trecho {t.fim_lat.original}, {t.fim_lon.original}\n{desc_common}"
        )

        ls = folder.newlinestring(
            name=f"Linha - {t.nome}",
            coords=[(ini_lon, ini_lat), (fim_lon, fim_lat)],
        )
        ls.description = desc_common
        ls.style.linestyle.color = aabbggrr
        ls.style.linestyle.width = 3

    kml_bytes = kml.kml().encode("utf-8")

    # Empacota como KMZ (ZIP com doc.kml)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("doc.kml", kml_bytes)

    return buf.getvalue(), kmz_name


# ----------------------------
# Exemplo de CSV (para download)
# ----------------------------

def sample_dataframe() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Nome do Trecho": "Rio Claro",
                "Extensão do Trecho": 1.25,
                "Início Lat (GMS)": "22° 54' 10'' S",
                "Início Lon (GMS)": "47° 03' 12'' W",
                "Fim Lat (GMS)": "22° 54' 45'' S",
                "Fim Lon (GMS)": "47° 02' 40'' W",
            },
            {
                "Nome do Trecho": "Córrego Azul",
                "Extensão do Trecho": 0.80,
                "Início Lat (GMS)": "22 55 05 S",
                "Início Lon (GMS)": "47 04 20 W",
                "Fim Lat (GMS)": "22 55 40 S",
                "Fim Lon (GMS)": "47 03 55 W",
            },
        ]
    )
