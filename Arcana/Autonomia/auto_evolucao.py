#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import os
import hashlib
from datetime import datetime
from typing import Dict, Any, List, Optional


class AutoEvolucao:
    def __init__(self, path: str = "Arcana/armazen/evolucao.json"):
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
        return {"historico": [], "habilitado": False, "requere_aprovacao": True}

    def _save(self):
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=4, ensure_ascii=False)
        except Exception:
            pass

    def registrar_sugestao(self, arquivo: str, descricao: str, codigo: Optional[str] = None) -> str:
        sid = hashlib.sha256(f"{arquivo}{descricao}{datetime.now().isoformat()}".encode("utf-8")).hexdigest()[:16]
        self.data["historico"].append({
            "id": sid,
            "arquivo": arquivo,
            "descricao": descricao,
            "codigo": codigo,
            "status": "pendente",
            "data": datetime.now().isoformat()
        })
        self._save()
        return sid

    def aprovar(self, sid: str) -> bool:
        for h in self.data["historico"]:
            if h["id"] == sid:
                h["status"] = "aprovado"
                h["aprovado_em"] = datetime.now().isoformat()
                self._save()
                return True
        return False

    def listar_pendentes(self) -> List[Dict[str, Any]]:
        return [h for h in self.data["historico"] if h.get("status") == "pendente"]
