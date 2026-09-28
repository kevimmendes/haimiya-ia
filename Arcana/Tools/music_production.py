class MusicProduction:
    """Assistente de produção musical: teoria, arranjo, mixagem, masterizacao e organizacao.

    A teoria e calculada localmente (sem depender de API) para ser rapida e exata.
    Para marcas, presets, mods e software especifico usa a pesquisa web ja existente no projeto.
    """

    NOTAS = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

    ESCALAS = {
        "maior": [0, 2, 4, 5, 7, 9, 11],
        "menor": [0, 2, 3, 5, 7, 8, 10],
        "harmonica": [0, 2, 4, 5, 7, 8, 11],
        "melodica": [0, 2, 3, 5, 7, 9, 11],
        "dorica": [0, 2, 3, 5, 7, 9, 10],
        "mixolidia": [0, 2, 4, 5, 7, 9, 10],
        "lidia": [0, 2, 4, 6, 7, 9, 11],
        "pentatonica_maior": [0, 2, 4, 7, 9],
        "pentatonica_menor": [0, 3, 5, 7, 10],
        "blues": [0, 3, 5, 6, 7, 10],
        "fenix": [0, 2, 4, 5, 7, 9, 11],
        "menor_harmonica": [0, 2, 3, 5, 7, 8, 11],
        "locria": [0, 1, 3, 5, 6, 8, 10],
    }

    # Progressoes classicas por numero romano
    PROGRESSOES = {
        "pop": ["I", "V", "vi", "IV"],
        "sad": ["vi", "IV", "I", "V"],
        "epico": ["i", "VI", "III", "VII"],
        "rock": ["I", "V", "vi", "IV"],
        "rnb": ["ii", "V", "I", "vi"],
        "lofi": ["i", "VII", "VI", "VII"],
        "cinematico": ["i", "VI", "III", "VII"],
        "soul": ["I", "vi", "ii", "V"],
        "funk": ["i", "IV", "i", "VI"],
        "gospel": ["I", "IV", "I", "V"],
    }

    QUALIDADE_ACORDE = {
        (0, 4, 7): "", (0, 3, 7): "m", (0, 3, 6): "dim", (0, 4, 8): "aug",
        (0, 4, 7, 11): "maj7", (0, 3, 7, 10): "m7", (0, 4, 7, 10): "7",
        (0, 3, 7, 11): "mMaj7", (0, 3, 6, 10): "m7b5",
    }

    ESTRUTURAS = {
        "pop": ["Intro", "Verso 1", "Pre-refrão", "Refrão", "Verso 2", "Pre-refrão", "Refrão", "Ponte", "Refrão final"],
        "trap": ["Intro", "Verso 1", "Hook", "Verso 2", "Hook", "Ponte", "Refrão final", "Outro"],
        "lofi": ["Intro", "Verso 1", "Refrão", "Verso 2", "Refrão", "Ponte", "Outro"],
        "rock": ["Intro", "Verso 1", "Refrão", "Verso 2", "Refrão", "Solo", "Refrão final"],
        "electronica": ["Intro", "Build", "Drop", "Break", "Drop 2", "Outro"],
        "reggaeton": ["Intro", "Verso", "Refrão", "Hook", "Ponte", "Refrão final"],
        "default": ["Intro", "A", "B", "A", "B", "Ponte", "B", "Final"],
    }

    # Alvos de loudness por plataforma
    LOUDNESS_PLATAFORMA = {
        "spotify": "-14 LUFS", "apple music": "-16 LUFS", "youtube": "-14 LUFS",
        "tiktok": "-14 LUFS", "instagram": "-14 LUFS", "soundcloud": "-14 LUFS",
        "bandcamp": "-9 LUFS (ou -14)", "radio": "-9 a -11 LUFS",
    }

    def __init__(self, output_callback=None, searcher=None, file_system=None):
        self.output_callback = output_callback
        self.searcher = searcher
        self.file_system = file_system

    def log(self, message):
        if self.output_callback:
            self.output_callback(message)
        else:
            print(message)

    # ======================================================
    # TEORIA
    # ======================================================
    def _para_indice(self, nota):
        n = nota.strip().upper().replace("DOM", "").replace("DOB", "").strip()
        if n in self.NOTAS:
            return self.NOTAS.index(n)
        for i, x in enumerate(self.NOTAS):
            if x == n:
                return i
        natural = {"D": "D#", "E": "F", "B": "C", "F#": "GB", "C#": "DB", "D#": "EB", "G#": "AB", "A#": "BB"}
        if n in natural:
            return self.NOTAS.index(natural[n])
        return 0

    def escala(self, tonica="C", tipo="menor"):
        intervalos = self.ESCALAS.get(tipo.lower().replace(" ", "_"), self.ESCALAS["menor"])
        base = self._para_indice(tonica)
        notas = [self.NOTAS[(base + i) % 12] for i in intervalos]
        return f"Escala {tipo} de {tonica.upper()}: {' - '.join(notas)}"

    def acorde(self, tonica="C", tipo="menor", septima=False):
        intervalos = self.ESCALAS.get(tipo.lower().replace(" ", "_"), self.ESCALAS["menor"])
        base = self._para_indice(tonica)
        graus = [intervalos[0], intervalos[2], intervalos[4]]
        if septima and len(intervalos) > 6:
            graus.append(intervalos[6])
        notas = [self.NOTAS[(base + i) % 12] for i in graus]
        qualidade = self.QUALIDADE_ACORDE.get(tuple(sorted(graus)), "")
        return f"Acorde {tonica.upper()}{qualidade}: {' - '.join(notas)}"

    def acorde_por_grau(self, tonica="C", tipo="menor", grau=1):
        intervalos = self.ESCALAS.get(tipo.lower().replace(" ", "_"), self.ESCALAS["menor"])
        base = self._para_indice(tonica)
        g = max(1, min(grau, len(intervalos))) - 1
        raiz = self.NOTAS[(base + intervalos[g]) % 12]
        return self.acorde(raiz, "maior" if tipo.lower().startswith("maior") else "menor")

    def _acorde_no_grau(self, base, intervalos, g):
        """Monta o acorde empilhando tercas na escala e deduz a qualidade real.

        Necessario porque o caso do numeral romano nao determina a qualidade:
        em menor natural os graus III, VI e VII sao maiores.
        """
        g = g % len(intervalos)
        raiz = intervalos[g]
        # tons do acorde: graus g, g+2 e g+4 (tercas empilhadas na escala)
        offsets = sorted({(intervalos[(g + s) % len(intervalos)] - raiz) % 12 for s in (0, 2, 4)})
        if len(offsets) < 3:
            return self.NOTAS[(base + raiz) % 12]
        segunda, terceira = offsets[1], offsets[2]
        if (segunda, terceira) == (4, 7):
            qualidade = ""
        elif (segunda, terceira) == (3, 6):
            qualidade = "dim"
        elif (segunda, terceira) == (4, 8):
            qualidade = "aug"
        else:
            qualidade = "m"
        return f"{self.NOTAS[(base + raiz) % 12]}{qualidade}"

    def progressao(self, tom="C", tipo="menor", genero="pop"):
        prog = self.PROGRESSOES.get(genero.lower(), self.PROGRESSOES["pop"])
        base = self._para_indice(tom)
        intervalos = self.ESCALAS.get(tipo.lower().replace(" ", "_"), self.ESCALAS["menor"])
        GRAUS = {"I": 0, "II": 1, "III": 2, "IV": 3, "V": 4, "VI": 5, "VII": 6}
        saida = []
        for num in prog:
            g = GRAUS.get(num.upper(), 0)
            saida.append(self._acorde_no_grau(base, intervalos, g))
        return f"Progressao {genero} em {tom.upper()} ({tipo}): {' - '.join(saida)}"

    def nota_frequencia(self, nota="A", oitava=4):
        base = self._para_indice(nota)
        # A4 = 440Hz
        indice_a4 = self.NOTAS.index("A")
        semitons = (base - indice_a4) + (oitava - 4) * 12
        freq = 440 * (2 ** (semitons / 12))
        return f"{nota.upper()}{oitava} = {freq:.2f} Hz"

    def tom_para_hz(self, nota, frequencia=440.0):
        base = self._para_indice(nota)
        indice_a4 = self.NOTAS.index("A")
        semitons = (base - indice_a4) + 0
        af = frequencia * (2 ** (semitons / 12))
        return f"{nota.upper()} a {frequencia:.1f} Hz = afinacao {af:.1f} Hz"

    def bpm_tempo(self, bpm=120, compasso=4, barras=32):
        seg_por_compasso = compasso * (60.0 / max(1, bpm))
        total = seg_por_compasso * barras
        return f"A {bpm} BPM, {barras} compassos de {compasso}/4 = {seg_por_compasso:.1f}s por compasso, {int(total)}s ({total/60:.1f} min) no total"

    def estrutura(self, genero="pop", bpm=120, compasso=4):
        partes = self.ESTRUTURAS.get(genero.lower(), self.ESTRUTURAS["default"])
        seg_c = compasso * (60.0 / max(1, bpm))
        linhas = [f"Estrutura sugerida para {genero} a {bpm} BPM ({compasso}/4):"]
        pos = 0.0
        for parte in partes:
            barras = 8 if any(k in parte.lower() for k in ["intro", "outro", "ponte", "solo", "break"]) else 4
            linhas.append(f"  {parte} - {barras} compassos ({barras*seg_c:.0f}s) | comeca em {int(pos)}s")
            pos += barras * seg_c
        linhas.append(f"Total: {partes.__len__()} secoes, ~{int(pos)}s ({pos/60:.1f} min)")
        return "\n".join(linhas)

    def letra_melodia(self, estrutura_cancao=None):
        return (
            "Para escrever a letra, mapeia a melodia em secoes:\n"
            "- INTRO (instrumental)\n- VERSO 1 (historia/contexto)\n- PRE/REFRAO (gancho emocional)\n"
            "- VERSO 2 (desenvolvimento)\n- PONTE (mudanca de perspetiva)\n- REFRAO FINAL (resolucao)\n"
            "Dica: mantem a mesma frase ritmica entre verso e refraino para o gancho pegar."
        )

    def ajuda_teoria(self):
        return (
            "Musica - Teoria: escala:TONICA:menor | acorde:TONICA:menor | progressao:TONICA:menor:genero | "
            "estrutura:genero:BPM | nota:TONICA | afinar:TONICA:HZ | bpm:BPM:compasso:barras | letra"
        )

    # ======================================================
    # PRODUCAO / MIX / MASTER
    # ======================================================
    def chain_mix(self, fonte="voz"):
        chains = {
            "voz": [
                "HPF 80-100 Hz (remove rumble)",
                "Subtrativa: cortar 200-400 Hz se estiver abafada (ataca 3-5 dB)",
                "Presenca 3-6 kHz para artigo (2-4 dB)",
                "Air 10-12 kHz para brilho (1-2 dB)",
                "Compressao: ratio 3:1, ataque 10-20 ms, release auto",
                "De-esser: 5-8 kHz se sibilante",
            ],
            "baixo": [
                "HPF 30-40 Hz (limpar sub)",
                "Compressao glue: ratio 2:1, attack 10 ms",
                "Saturacao leve para harmonicos",
                "Cortar 800 Hz se competir com a voz",
            ],
            "bateria": [
                "HPF 30 Hz no kick, 200 Hz no resto",
                "Compressao no room mics para glue",
                "Sidechain: pad e bass ligam no kick",
                "Saturacao no bus de master leve",
            ],
            "sintetizador": [
                "Cortar 100-200 Hz se amontoar",
                "Reverb curto (1-2s) para nao lavar",
                "Pan pelo espectro (baixo centro, agudo laterais)",
            ],
            "violao": [
                "HPF 80-120 Hz",
                "Ataque dinamico para picking",
                "Reverb curto com pre-delay 20-40ms",
            ],
        }
        passos = chains.get(fonte.lower(), chains["voz"])
        linhas = [f"Chain de mixagem sugerida para {fonte}:"]
        linhas += [f"  {i+1}. {p}" for i, p in enumerate(passos)]
        return "\n".join(linhas)

    def chain_master(self, genero="pop", plataforma="spotify"):
        alvo = self.LOUDNESS_PLATAFORMA.get(plataforma.lower(), "-14 LUFS")
        linhas = [f"Masterizacao - alvo {plataforma} ({alvo}):"]
        linhas += [
            "  1. Em ordem: corte de graves (<20 Hz)",
            "  2. Saturação subtil (1-3 dB GR) para coerência",
            "  3. EQ corretiva (masking entre 200 Hz-3 kHz)",
            f"  4. Compressor glue: ratio 2:1, attack 30-50 ms",
            f"  5. Loudness: chegar a {alvo} (medir, não chutear)",
            "  6. True peak: max -1 dBTP (evita distorção)",
            "  7. Dither 16-bit se exportando para CD",
        ]
        if genero.lower() in ["trap", "edm", "eletronica"]:
            linhas.append("  Dica: lado B mais largo, centro focuses nas kicks/snares.")
        elif genero.lower() in ["lofi", "chill"]:
            linhas.append("  Dica: master mais escuro e baixa-mid cut, sabor de vinil.")
        return "\n".join(linhas)

    def compressor(self, fonte="voz", ratio=3, ataque=15, release=100):
        return (
            f"Compressor - {fonte}: ratio {ratio}:1, ataque {ataque} ms, release {release} ms.\n"
            f"  Regra: reduza o gain de 2-4 dB. Se aguentar mais que 6 dB, ta a esmagar.\n"
            f"  Ordem: HPF -> EQ -> Compressor -> De-esser -> Reverb/Delay"
        )

    def reverb_delay(self, tipo="plate", tempo_bpm=120):
        delay_tempo = 60.0 / max(1, tempo_bpm)
        if tipo.lower() in ["plate", "placa"]:
            return f"Reverb plate: pre-delay 20-40ms, decay 1.8-2.5s, high-cut 6 kHz, mix 15-25% (voz), 35% (ambiente)"
        if tipo.lower() in ["hall", "sala"]:
            return f"Reverb hall: pre-delay 30ms, decay 2.5-4s, mix 20% (voz) / 50% (instrumental)"
        if tipo.lower() in ["room", "salao"]:
            return f"Reverb room: decay 0.6-1s, mix 10-15% - bom para tecla/bateria seca"
        if tipo.lower() in ["delay", "eco"]:
            return (f"Delay: tempo = {delay_tempo:.3f}s (1/4 de {tempo_bpm} BPM), feedback 20-35%, "
                    f"filtro passa-baixa 3-4 kHz, ping-pong para largura")
        if tipo.lower() in ["chorus", "coro"]:
            return "Chorus: depth 3-6 ms, rate 0.3-1 Hz, mix 15-30% - thickening em pads/guitarras"
        return f"Reverb delay: pre-delay 20ms, delay 1/4 = {delay_tempo:.3f}s, mix 20%"

    def organizacao(self, pasta):
        if not self.file_system:
            return "Sem acesso ao sistema de ficheiros."
        tipos = {
            "samples": [".wav", ".aiff", ".mp3", ".flp", ".mid", ".midi"],
            "projetos": [".rpp", ".als", ".flp", ".logicx", ".xps", ".mproj", ".als"],
            "presets": [".fxp", ".fxb", ".vstpreset", ".preset", ".pgtx"],
            "bounces": [".mp3", ".wav"],
        }
        linhas = [f"Organizacao de {pasta}:"]
        for categoria, exts in tipos.items():
            encontrados = []
            for e in exts:
                encontrados += self.file_system.search_files("", extension=e, directory=pasta)
            encontrados = list(set(encontrados))[:10]
            if encontrados:
                linhas.append(f"  {categoria} ({len(encontrados)} mostrados):")
                for f in encontrados:
                    linhas.append(f"    {f}")
            else:
                linhas.append(f"  {categoria}: nenhum encontrado")
        return "\n".join(linhas)

    def ajuda_mix(self):
        return (
            "Musica - Mix/Master: mix:voz | master:genero:spotify | comp:voz | reverb:plate | "
            "organizar:PASTA | pesquisa:TEXTO"
        )

    # ======================================================
    # PESQUISA (usa o motor DDG ja existente no projeto)
    # ======================================================
    def pesquisa(self, termo, searcher=None):
        s = searcher or self.searcher
        if not s:
            return "Pesquisa web nao disponivel."
        try:
            return s(termo)
        except Exception as e:
            return f"Falha na pesquisa: {e}"
