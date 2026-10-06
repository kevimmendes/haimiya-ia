#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import Dict, Any, List


class SubAgente:
    def __init__(self, nome: str, descricao: str):
        self.nome = nome
        self.descricao = descricao
        self.habilitado = True


class GerenciadorSubAgentes:
    def __init__(self):
        self.agentes: List[SubAgente] = []

    def registrar(self, nome: str, descricao: str) -> bool:
        self.agentes.append(SubAgente(nome, descricao))
        return True

    def listar(self) -> List[Dict[str, Any]]:
        return [{"nome": a.nome, "descricao": a.descricao, "habilitado": a.habilitado} for a in self.agentes]

    def executar(self, nome: str, tarefa: str) -> Dict[str, Any]:
        return {"nome": nome, "tarefa": tarefa, "status": "concluido"}
