#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import Dict, Any


class Avatar:
    def falar(self, texto: str) -> Dict[str, Any]:
        return {"texto": texto, "status": "ok"}
