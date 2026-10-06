#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import requests
from typing import Dict, Any, Optional


class GeradorImagens:
    """Gera imagens pela PollinationsAI (gratuita, sem chave) e guarda em
    Arcana/armazen/imagens. Se falhar ou estiver offline, avisa em vez de
    travar."""

    def gerar(self, prompt: str, modelo: str = "flux", saida: Optional[str] = None) -> Dict[str, Any]:
        if not prompt:
            return {"prompt": "", "status": "sem prompt"}
        try:
            url = f"https://image.pollinations.ai/prompt/{(prompt or '').strip()[:300]}"
            r = requests.get(url, params={"width": 1024, "height": 1024,
                                          "seed": 42, "model": modelo,
                                          "nologo": "true"},
                             timeout=60)
            r.raise_for_status()
            caminho = saida or os.path.join("Arcana", "armazen", "imagens",
                                            f"img_{abs(hash(prompt)) % 1000000}.png")
            os.makedirs(os.path.dirname(caminho) or ".", exist_ok=True)
            with open(caminho, "wb") as f:
                f.write(r.content)
            return {"prompt": prompt, "status": "ok", "caminho": caminho,
                    "bytes": len(r.content)}
        except Exception as e:
            return {"prompt": prompt, "status": "erro", "erro": str(e)}