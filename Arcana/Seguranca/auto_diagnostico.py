#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import psutil
import platform
from datetime import datetime
from typing import Dict, Any


class AutoDiagnostico:
    def executar(self) -> Dict[str, Any]:
        try:
            return {
                "timestamp": datetime.now().isoformat(),
                "sistema": platform.system(),
                "cpu_percent": psutil.cpu_percent(interval=0.1),
                "memoria_percent": psutil.virtual_memory().percent,
                "disco_percent": psutil.disk_usage("/").percent if hasattr(psutil.disk_usage("/"), "percent") else psutil.disk_usage("C:/").percent,
                "status": "ok"
            }
        except Exception as e:
            return {"status": "erro", "erro": str(e)}
