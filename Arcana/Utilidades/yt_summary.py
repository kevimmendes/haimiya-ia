#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import re
import requests
from typing import Dict, Any


class YTSummary:
    """Resumo de vídeo do YouTube sem chave: pega o título do vídeo e o
    resumo rápido da página (og:description). Para transcrição completa, a
    IA pode pedir a quem escreveu o texto."""

    def resumir(self, url: str) -> Dict[str, Any]:
        if not url:
            return {"url": url, "resumo": "sem url"}
        try:
            r = requests.get(url, timeout=10,
                             headers={"User-Agent": "Mozilla/5.0"})
            r.raise_for_status()
            html = r.text

            def _mg(pat, texto=html, flags=re.I):
                m = re.search(pat, texto, flags)
                return m.group(1).strip() if m else ""

            titulo = _mg(r'<meta\s+property="og:title"\s+content="([^"]+)"') or \
                     _mg(r'<title>([^<]+)</title>')
            descricao = _mg(r'<meta\s+property="og:description"\s+content="([^"]+)"')

            if titulo:
                resumo = f"Título: {titulo}"
                if descricao:
                    resumo += f" | Sinopse: {descricao[:300]}"
                return {"url": url, "resumo": resumo, "titulo": titulo}
            return {"url": url, "resumo": "não consegui ler o vídeo (pode ser privado ou bloqueado)"}
        except Exception as e:
            return {"url": url, "resumo": "não consegui buscar o vídeo agora",
                    "erro": str(e)}