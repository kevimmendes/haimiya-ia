#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import Dict, Any


class ControleMouseTeclado:
    def __init__(self):
        self.habilitado = True

    def mover(self, x: int, y: int) -> bool:
        return True

    def clicar(self, x: int, y: int, botao: str = "left") -> bool:
        return True

    def digitar(self, texto: str) -> bool:
        return True

    def atalho(self, teclas: str) -> bool:
        return True
