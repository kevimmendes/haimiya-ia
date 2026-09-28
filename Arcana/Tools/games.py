class Games:
    """Assistente de jogos: pesquisa de guias/dicas/builds, deteccao de jogos instalados,
    analise de screenshots de jogo e ajuda com configuracao/modding."""

    # Processos conhecidos para deteccao
    JOGOS_COMUNS = {
        "cyberpunk2077": "Cyberpunk 2077", "cyberpunk": "Cyberpunk 2077",
        "minecraft.windows": "Minecraft", "minecraft": "Minecraft",
        "cs2": "Counter-Strike 2", "csgo": "CS:GO", "dota2": "Dota 2",
        "valorant": "Valorant", "lol": "League of Legends", "leagueoflegends": "LoL",
        "fortnite": "Fortnite", "pubg": "PUBG", "rdr2": "Red Dead Redemption 2",
        "eldenring": "Elden Ring", "skyrim": "Skyrim", "witcher3": "The Witcher 3",
        "gta5": "GTA V", "gta": "GTA", "apex": "Apex Legends",
        "rust": "Rust", "hades": "Hades", "stardew": "Stardew Valley",
    }

    # Ordem = prioridade. Especificos primeiro, genericos ("como"/"dica") no fim,
    # para "como completo a missao X" cair em quest e nao em dica.
    TEMAS = {
        "tecnico": ["erro", "bug", "crash", "problema", "requisito", "flicker", "lag", "travou", "nao abre"],
        "config": ["configuracao", "config", "grafica", "fps", "desempenho", "opcoes"],
        "mod": ["mods", "mod", "modding"],
        "build": ["builds", "build", "strategy", "estrategia", "setup", "personagem forte"],
        "boss": ["boss", "chefe", "fight", "combate"],
        "quest": ["missao", "quest", "questao", "missões", "tarefa"],
        "item": ["itens", "item", "loot", "onde", "equipamento", "arma"],
        "guia": ["walkthrough", "guia", "tutorial", "completo"],
        "dica": ["dicas", "dica", "como", "ajuda", "conselho", "dicas"],
    }

    def __init__(self, output_callback=None, searcher=None, screen_vision=None):
        self.output_callback = output_callback
        self.searcher = searcher
        self.screen_vision = screen_vision

    def log(self, message):
        if self.output_callback:
            self.output_callback(message)
        else:
            print(message)

    # ======================================================
    # DETECCAO
    # ======================================================
    def jogos_a_correr(self):
        try:
            import psutil
            encontrados = {}
            for p in psutil.process_iter(["name"]):
                nome = (p.info["name"] or "").lower()
                for chave, nome_lindo in self.JOGOS_COMUNS.items():
                    if chave in nome and nome_lindo not in encontrados:
                        encontrados[nome_lindo] = p.info["name"]
            return encontrados
        except Exception as e:
            self.log(f"[GAMES] Erro a detectar processos: {e}")
            return {}

    def jogo_atual(self):
        jogos = self.jogos_a_correr()
        if jogos:
            return list(jogos.keys())[0]
        return None

    # ======================================================
    # PESQUISA INTELIGENTE
    # ======================================================
    def interpretar(self, texto):
        """Identifica o tema de pesquisa a partir do texto do utilizador."""
        t = texto.lower()
        for valor, chaves in self.TEMAS.items():
            for chave in chaves:
                if chave in t:
                    return valor
        return "dica"

    def pesquisa(self, jogo, topico="dica", contexto=""):
        """Monta a query de pesquisa mais eficaz e delega no motor de busca."""
        jogo_limpo = jogo.strip() or "o jogo"
        topicos = {
            "dica": f"{jogo_limpo} dicas como",
            "guia": f"{jogo_limpo} guia completo walkthrough",
            "quest": f"{jogo_limpo} como completar missao",
            "build": f"{jogo_limpo} build completa/setup otimizado",
            "item": f"{jogo_limpo} onde encontrar item",
            "boss": f"{jogo_limpo} como derrotar boss estrategia",
            "config": f"{jogo_limpo} melhor configuracao grafica desempenho",
            "mod": f"{jogo_limpo} mods recomendados",
            "tecnico": f"{jogo_limpo} problema tecnico solucao",
        }
        base = topicos.get(topico, f"{jogo_limpo} {topico}")
        query = f"{base} {contexto}".strip() if contexto else base
        query += " site:youtube.com OR site:reddit.com OR site:ign.com"
        self.log(f"[GAMES] A pesquisar: '{query}'")
        if not self.searcher:
            return "Pesquisa web nao disponivel."
        try:
            return self.searcher(query)
        except Exception as e:
            return f"Falha na pesquisa: {e}"

    def ajuda(self, texto):
        """Ponto de entrada: interpreta o pedido e pesquisa."""
        jogo = texto.strip()
        if not jogo:
            return "Diz-me o nome do jogo."
        # remove artigos iniciais
        for art in ["estou preso", "me ajuda com", "como jogar", "no jogo", "sobre"]:
            jogo = jogo.replace(art, "").strip()
        topico = self.interpretar(texto)
        return self.pesquisa(jogo, topico, texto)

    # ======================================================
    # ANALISE DE SCREENSHOT
    # ======================================================
    def analisar_screenshot(self, descricao=""):
        """Analisa o ecra atual com o modelo de visao, focando em contexto de jogo."""
        if not self.screen_vision:
            return "Modulo de visao nao disponivel."
        self.log("[GAMES] A analisar a tela do jogo...")
        return self.screen_vision.analyze_screen(
            descricao or "Analisa esta imagem de um jogo: identifica o que aparece, o que o jogador precisa fazer, itens, inimigos, menus, erros."
        )

    def ajuda_jogos(self):
        return "Jogos: pesquisa:JOGO:dica | jogos_correr | ajuda:TEXTO | screenshot"
