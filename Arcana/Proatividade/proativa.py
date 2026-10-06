#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import os
from datetime import datetime
from typing import Dict, Any, List


class SistemaProativo:
    def __init__(self, path: str = "Arcana/armazen/proativo.json"):
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
        return {"sugestoes": [], "lembretes": [], "ativado": True}

    def _save(self):
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=4, ensure_ascii=False)
        except Exception:
            pass

    def sugerir(self, conteudo: str) -> bool:
        self.data["sugestoes"].append({"texto": conteudo, "data": datetime.now().isoformat()})
        self._save()
        return True

    def listar_sugestoes(self, limit: int = 5) -> List[Dict[str, Any]]:
        return self.data["sugestoes"][-limit:]
