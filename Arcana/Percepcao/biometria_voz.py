#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import Dict, Any, Optional


class BiometriaVoz:
    def __init__(self):
        self.perfis = {}

    def registrar(self, usuario: str, audio: Optional[bytes] = None) -> bool:
        self.perfis[usuario] = {"registrado": audio is not None}
        return True

    def verificar(self, usuario: str, audio: Optional[bytes] = None) -> Dict[str, Any]:
        return {"usuario": usuario, "confianca": 0.5, "ok": False}
