#!/usr/bin/env python
"""
Download Brazilian state boundaries from IBGE and prepare for the Streamlit app.

Usage:
    python scripts/download_geodata.py

Output:
    data/geojson/brazil_states.geojson
"""

import json
import requests
from pathlib import Path

OUTPUT_DIR = Path(__file__).parent.parent / "data" / "geojson"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# IBGE 2-digit code → 2-letter UF abbreviation
IBGE_TO_UF = {
    "11": "RO", "12": "AC", "13": "AM", "14": "RR", "15": "PA",
    "16": "AP", "17": "TO", "21": "MA", "22": "PI", "23": "CE",
    "24": "RN", "25": "PB", "26": "PE", "27": "AL", "28": "SE",
    "29": "BA", "31": "MG", "32": "ES", "33": "RJ", "35": "SP",
    "41": "PR", "42": "SC", "43": "RS", "50": "MS", "51": "MT",
    "52": "GO", "53": "DF",
}

UF_TO_NAME = {
    "RO": "Rondônia",         "AC": "Acre",                "AM": "Amazonas",
    "RR": "Roraima",          "PA": "Pará",                "AP": "Amapá",
    "TO": "Tocantins",        "MA": "Maranhão",            "PI": "Piauí",
    "CE": "Ceará",            "RN": "Rio Grande do Norte", "PB": "Paraíba",
    "PE": "Pernambuco",       "AL": "Alagoas",             "SE": "Sergipe",
    "BA": "Bahia",            "MG": "Minas Gerais",        "ES": "Espírito Santo",
    "RJ": "Rio de Janeiro",   "SP": "São Paulo",           "PR": "Paraná",
    "SC": "Santa Catarina",   "RS": "Rio Grande do Sul",   "MS": "Mato Grosso do Sul",
    "MT": "Mato Grosso",      "GO": "Goiás",               "DF": "Distrito Federal",
}

# IBGE malhas v3 — individual state endpoint (minimum quality = smaller file)
URL_TEMPLATE = (
    "https://servicodados.ibge.gov.br/api/v3/malhas/estados/{code}"
    "?formato=application/vnd.geo+json&qualidade=minima"
)


def main():
    features = []
    print(f"Downloading {len(IBGE_TO_UF)} state boundaries from IBGE …")

    for code, uf in IBGE_TO_UF.items():
        resp = requests.get(URL_TEMPLATE.format(code=code), timeout=30)
        resp.raise_for_status()
        data = resp.json()
        for feature in data.get("features", []):
            feature["properties"]["uf"] = uf
            feature["properties"]["state_name"] = UF_TO_NAME[uf]
            features.append(feature)
        print(f"  {code} → {uf}  ({UF_TO_NAME[uf]})")

    geojson = {"type": "FeatureCollection", "features": features}
    out = OUTPUT_DIR / "brazil_states.geojson"
    out.write_text(json.dumps(geojson, ensure_ascii=False))
    print(f"\nSaved {len(features)} features → {out}")


if __name__ == "__main__":
    main()
