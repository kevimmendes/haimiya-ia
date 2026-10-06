#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import Dict, Any


class Receitas:
    def buscar(self, ingrediente: str) -> Dict[str, Any]:
        return {"ingrediente": ingrediente, "sugestao": "receita nao encontrada no cache"}
