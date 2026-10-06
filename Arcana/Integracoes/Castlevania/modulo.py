#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import Dict, Any


class CastlevaniaModule:
    def __init__(self):
        self.ativo = False
        self.contexto = {}

    def ativar(self):
        self.ativo = True

    def desativar(self):
        self.ativo = False

    def processar(self, texto: str) -> Dict[str, Any]:
        if not self.ativo:
            return {"ativado": False}
        return {"ativado": True, "resposta_tema": texto}
