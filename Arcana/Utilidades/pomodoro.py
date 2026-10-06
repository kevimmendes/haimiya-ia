#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import time
from typing import Dict, Any


class Pomodoro:
    def __init__(self):
        self.ativo = False
        self.inicio = 0
        self.duracao = 25 * 60

    def iniciar(self, minutos: int = 25) -> Dict[str, Any]:
        self.duracao = minutos * 60
        self.inicio = time.time()
        self.ativo = True
        return {"status": "iniciado", "minutos": minutos}

    def status(self) -> Dict[str, Any]:
        if not self.ativo:
            return {"status": "parado"}
        restante = max(0, self.duracao - (time.time() - self.inicio))
        return {"status": "ativo", "restante_segundos": int(restante)}
