#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import Dict, Any


class WakeWord:
    def __init__(self):
        self.ativo = True
        self.palavra = "haimiya"

    def detectar(self, audio: bytes) -> bool:
        return False
