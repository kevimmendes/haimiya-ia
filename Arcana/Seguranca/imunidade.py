#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import hashlib
import os
import json
from datetime import datetime
from typing import Dict, Any, List


class SistemaImunidade:
    def __init__(self, path: str = "Arcana/armazen/imunidade.json"):
        self.path = path
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self.data = self._load()

    def _load(self) -> Dict[str, Any]:
        try:
            if os.path.exists(self.path):
                with open(self.path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
        return {"assinaturas": [], "bloqueados": [], "snapshots": []}

    def _save(self):
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=4, ensure_ascii=False)
        except Exception:
            pass

    def calcular_hash(self, arquivo: str) -> str:
        try:
            with open(arquivo, "rb") as f:
                return hashlib.sha256(f.read()).hexdigest()
        except Exception:
            return ""

    def criar_snapshot(self, arquivo: str) -> bool:
        h = self.calcular_hash(arquivo)
        if not h:
            return False
        self.data["snapshots"].append({
            "arquivo": arquivo,
            "hash": h,
            "data": datetime.now().isoformat()
        })
        self._save()
        return True

    def verificar_integridade(self, arquivo: str) -> bool:
        h_atual = self.calcular_hash(arquivo)
        for snap in self.data["snapshots"]:
            if snap["arquivo"] == arquivo:
                return snap["hash"] == h_atual
        return True  # sem snapshot, considera ok
