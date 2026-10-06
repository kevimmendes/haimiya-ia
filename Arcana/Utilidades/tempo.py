#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import requests
from datetime import datetime
from typing import Dict, Any


class Tempo:
    """Clima (Open-Meteo, sem chave) e câmbio (exchangerate.host, sem chave).

    Tudo com fallback silencioso: se a internet ou a API falhar, devolve o
    que conseguir montar em vez de rebentar o cérebro da IA.
    """

    def __init__(self, timeout: int = 6):
        self.timeout = timeout

    def obter_clima(self, cidade: str = "", lat: float = None, lon: float = None) -> Dict[str, Any]:
        base = {"cidade": cidade or "desconhecida", "timestamp": datetime.now().isoformat()}
        try:
            if lat is None or lon is None:
                if cidade:
                    geo = requests.get(
                        "https://geocoding-api.open-meteo.com/v1/search",
                        params={"name": cidade, "count": 1},
                        timeout=self.timeout,
                    )
                    geo.raise_for_status()
                    resultados = geo.json().get("results") or []
                    if not resultados:
                        base["status"] = "cidade nao encontrada"
                        return base
                    lat = resultados[0]["latitude"]
                    lon = resultados[0]["longitude"]
                    base["cidade"] = resultados[0].get("name", cidade)
                else:
                    base["status"] = "sem localizacao"
                    return base

            r = requests.get(
                "https://api.open-meteo.com/v1/forecast",
                params={"latitude": lat, "longitude": lon,
                        "current_weather": "true"},
                timeout=self.timeout,
            )
            r.raise_for_status()
            dados = r.json().get("current_weather", {})
            base.update({
                "status": "ok",
                "temperatura_c": dados.get("temperature"),
                "vento_kmh": dados.get("windspeed"),
                "carencia": dados.get("weathercode"),
            })
        except Exception as e:
            base["status"] = "indisponivel"
            base["erro"] = str(e)
        return base

    def obter_moeda(self, base: str = "BRL") -> Dict[str, Any]:
        saida = {"base": base.upper(), "timestamp": datetime.now().isoformat()}
        try:
            r = requests.get(
                "https://open.er-api.com/v6/latest/" + saida["base"],
                timeout=self.timeout,
            )
            r.raise_for_status()
            dashes = r.json().get("rates")
            if dashes:
                saida["status"] = "ok"
                saida["taxas"] = {"USD": dashes.get("USD"),
                                  "EUR": dashes.get("EUR"),
                                  "BRL": dashes.get("BRL")}
        except Exception as e:
            saida["status"] = "indisponivel"
            saida["erro"] = str(e)
        return saida