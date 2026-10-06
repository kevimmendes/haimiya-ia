#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import Dict, Any


class PatchValidator:
    def validar(self, patch: str) -> Dict[str, Any]:
        if not patch or len(patch.strip()) == 0:
            return {"valido": False, "motivo": "patch vazio"}
        perigos = ["rm -rf", "format", "shutdown", "del /f /s"]
        for p in perigos:
            if p.lower() in patch.lower():
                return {"valido": False, "motivo": f"comando perigoso detectado: {p}"}
        return {"valido": True, "motivo": "ok"}
