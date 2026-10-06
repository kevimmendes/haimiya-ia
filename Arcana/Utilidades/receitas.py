#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import Dict, Any


class Receitas:
    """Receitas da TheMealDB (gratuita, sem chave) com fallback próprio."""

    def buscar(self, ingrediente: str) -> Dict[str, Any]:
        if not ingrediente:
            return {"ingrediente": "", "sugestao": "diz um ingrediente para eu procurar"}
        try:
            import requests
            r = requests.get(
                "https://www.themealdb.com/api/json/v1/1/filter.php",
                params={"i": ingrediente},
                timeout=8,
            )
            r.raise_for_status()
            refeicoes = (r.json().get("meals") or [])[:3]
            if not refeicoes:
                return {"ingrediente": ingrediente,
                        "sugestao": "nao achei receita com esse ingrediente"}
            return {
                "ingrediente": ingrediente,
                "sugestao": "; ".join(m.get("strMeal", "?") for m in refeicoes),
                "detalhe": f"https://www.themealdb.com/api/json/v1/1/lookup.php?i={refeicoes[0]['idMeal']}",
            }
        except Exception as e:
            return {"ingrediente": ingrediente,
                    "sugestao": "não consegui buscar receitas agora",
                    "erro": str(e)}