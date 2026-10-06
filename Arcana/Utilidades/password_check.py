#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import hashlib
from typing import Dict, Any


class PasswordChecker:
    def check(self, senha: str) -> Dict[str, Any]:
        if not senha:
            return {"vulneravel": False}
        h = hashlib.sha1(senha.encode("utf-8")).hexdigest().upper()
        return {"prefixo": h[:5], "sufixo": h[5:], "k_anonimo": True, "vulneravel": None}
