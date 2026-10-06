#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from datetime import datetime
from typing import Dict, Any


class Tempo:
    def obter_clima(self, cidade: str = "auto") -> Dict[str, Any]:
        return {"cidade": cidade, "status": "indisponivel", "timestamp": datetime.now().isoformat()}

    def obter_moeda(self, base: str = "BRL") -> Dict[str, Any]:
        return {"base": base, "timestamp": datetime.now().isoformat()}
