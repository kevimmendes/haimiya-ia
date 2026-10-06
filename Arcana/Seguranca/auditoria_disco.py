#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
from datetime import datetime
from typing import Dict, Any, List


class AuditoriaDisco:
    def escanear(self, caminho: str = "C:/", limite: int = 100) -> Dict[str, Any]:
        arquivos = []
        try:
            count = 0
            for root, dirs, files in os.walk(caminho):
                for f in files:
                    arquivos.append(os.path.join(root, f))
                    count += 1
                    if count >= limite:
                        return {"caminho": caminho, "total": count, "arquivos": arquivos, "timestamp": datetime.now().isoformat()}
        except Exception as e:
            return {"caminho": caminho, "erro": str(e), "timestamp": datetime.now().isoformat()}
        return {"caminho": caminho, "total": len(arquivos), "arquivos": arquivos, "timestamp": datetime.now().isoformat()}
