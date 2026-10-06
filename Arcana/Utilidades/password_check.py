#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import hashlib
from typing import Dict, Any


class PasswordChecker:
    """Checagem k-anônima com a HIBP (haveibeenpwned). Só envia o prefixo
    SHA-1 da senha, nunca a senha, nem o sufixo do hash."""

    def hash_sha1(self, senha: str) -> str:
        return hashlib.sha1(senha.encode("utf-8")).hexdigest().upper()

    def check(self, senha: str) -> Dict[str, Any]:
        if not senha:
            return {"k_anonimo": False, "vulneravel": None, "motivo": "senha vazia"}
        h = self.hash_sha1(senha)
        prefixo, sufixo = h[:5], h[5:]
        try:
            import requests
            r = requests.get(
                f"https://api.pwnedpasswords.com/range/{prefixo}",
                timeout=6,
                headers={"Accept": "text/plain"},
            )
            r.raise_for_status()
            vazamentos = 0
            for linha in r.text.splitlines():
                sufixo_lista, _, contagem = linha.partition(":")
                if sufixo_lista.upper() == sufixo:
                    vazamentos = int(contagem)
                    break
            return {
                "k_anonimo": True,
                "prefixo": prefixo,
                "vulneravel": vazamentos > 0,
                "vazamentos": vazamentos,
            }
        except Exception as e:
            return {"k_anonimo": True, "prefixo": prefixo,
                    "vulneravel": None, "erro": str(e)}