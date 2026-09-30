import json
import os
import queue

import tkinter as tk
from tkinter import ttk

from PIL import ImageTk

from Arcana.Apps import vidro

# PADRÃO ABSOLUTO E CORRETO: brain.json
BRAIN_FILE = "Arcana/armazen/brain.json"

# Paleta — Haimiya (amarelo/vermelho sobre o vidro quente)
BG_COLOR = "#0d0d14"
SURFACE_COLOR = "#17171f"
HIGHLIGHT_COLOR = "#282833"
REM_YELLOW = "#ffd60a"
REM_RED = "#ff5c5c"
TEXT_COLOR = "#f2f0e5"
TEXT_DIM = "#9a9685"

BRANCO_QUENTE = "#ffeade"   # texto secundario sobre o vidro quente
ESCURO_OURO = "#3d2b00"     # texto por cima do amarelo solido

W_JANELA, A_JANELA = 900, 620

# caixas do desenho (x0, y0, x1, y1)
CAIXA_MESTRE = (16, 16, 884, 604)
BARRA_LATERAL = 250

CARTOES = {
    "geral": [
        (274, 48, 868, 218),     # modelos locais
        (274, 238, 868, 408),    # modelos do discord
        (274, 428, 868, 588),    # avatar virtual
    ],
    "discord": [
        (274, 48, 868, 258),     # estado da ligacao
        (274, 278, 868, 588),    # configuracao avancada
    ],
}

# pilulas de escolha: chave, caixa, campo do estado, valor
PILULAS = [
    ("m_local_nvidia", (298, 122, 563, 178), "local", "nvidia"),
    ("m_local_groq",   (579, 122, 844, 178), "local", "groq"),
    ("m_disc_nvidia",  (298, 306, 563, 362), "modelos_discord", "nvidia"),
    ("m_disc_groq",    (579, 306, 844, 362), "modelos_discord", "groq"),
    ("av_on",          (298, 496, 563, 552), "vtuber", True),
    ("av_off",         (579, 496, 844, 552), "vtuber", False),
]

# aspeto de cada superficie desenhada
ESTILOS = {
    "nav":         dict(raio=16, veu=(255, 255, 255, 70),  borda=(255, 255, 255, 120)),
    "nav_foco":    dict(raio=16, veu=(255, 255, 255, 44),  borda=(255, 255, 255, 95)),
    "ouro":        dict(raio=14, cor=(255, 214, 10, 255),  borda=(255, 255, 255, 160)),
    "ouro_foco":   dict(raio=14, cor=(255, 233, 96, 255),  borda=(255, 255, 255, 190)),
    "vazado":      dict(raio=14, veu=(255, 255, 255, 34),  borda=(255, 130, 130, 185)),
    "vazado_foco": dict(raio=14, veu=(255, 255, 255, 64),  borda=(255, 170, 170, 220)),
    "fresco":      dict(raio=14, veu=(255, 255, 255, 36),  borda=(255, 255, 255, 96)),
    "fresco_foco": dict(raio=14, veu=(255, 255, 255, 66),  borda=(255, 255, 255, 135)),
}


def _centrar(janela):
    """Centra a janela na area de trabalho, para nao ficar por cima da
    barra de tarefas (num ecrã de 768px isso escondia o rodape)."""
    try:
        import ctypes
        from ctypes import wintypes

        class RECT(ctypes.Structure):
            _fields_ = [("Left", ctypes.c_long), ("Top", ctypes.c_long),
                        ("Right", ctypes.c_long), ("Bottom", ctypes.c_long)]

        class MONITORINFO(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", RECT),
                        ("rcWork", RECT), ("dwFlags", wintypes.DWORD)]

        u = ctypes.windll.user32
        hwnd = u.GetParent(janela.winfo_id())
        mi = MONITORINFO()
        mi.cbSize = ctypes.sizeof(MONITORINFO)
        m = u.MonitorFromWindow(wintypes.HWND(hwnd), 2)  # MONITOR_DEFAULTTONEAREST
        if m and u.GetMonitorInfoW(m, ctypes.byref(mi)):
            x = mi.rcWork.Left + ((mi.rcWork.Right - mi.rcWork.Left) - W_JANELA) // 2
            y = mi.rcWork.Top + ((mi.rcWork.Bottom - mi.rcWork.Top) - A_JANELA) // 2
        else:
            x = (janela.winfo_screenwidth() - W_JANELA) // 2
            y = (janela.winfo_screenheight() - A_JANELA) // 2
        janela.geometry(f"{W_JANELA}x{A_JANELA}+{max(0, x)}+{max(0, y)}")
    except Exception:
        pass


def criar_checkbutton(master, text, variable, fg_color=TEXT_COLOR):
    return tk.Checkbutton(
        master, text=text, variable=variable,
        bg=SURFACE_COLOR, fg=fg_color, selectcolor=BG_COLOR,
        activebackground=SURFACE_COLOR, activeforeground=REM_RED,
        font=("Segoe UI", 10), cursor="hand2", bd=0, highlightthickness=0
    )


class RemGUI:
    """Painel de controlo da Haimiya.

    Todo o aspeto e' uma imagem so (Pillow): fundo quente desfocado,
    cartoes e pilulas recortados desse fundo. O Tkinter por cima so
    guarda textos e areas de clique, com o fundo de cada widget
    amostrado na imagem — e' isso que evita custuras visiveis.
    """

    janela = None
    _base = None          # imagem do fundo quente
    _camada = None        # Label que mostra a imagem composta
    _foto = None          # referencia viva da PhotoImage
    _master = None        # imagem composta atual (para amostrar cores)
    _estado = None
    _amostrar = []        # widgets cujo bg vem amostrado da imagem
    _acoes = {}           # chave -> funcao da area de clique
    _cenario_cache = {}
    _rotulos_pilula = []  # (Label, campo, valor) para trocar cor do texto

    # ------------------------------------------------------------------
    # desenho
    # ------------------------------------------------------------------
    @classmethod
    def _cenario(cls, vista):
        """Imagem com o fundo, o contentor e os cartoes da vista."""
        if vista in cls._cenario_cache:
            return cls._cenario_cache[vista]
        base = cls._base
        img = base.copy()

        mestre = vidro.frescor(base, CAIXA_MESTRE, raio=32, veu=(255, 255, 255, 22),
                               borda=(255, 255, 255, 66), sombra=150, desfoque=10)
        img.paste(mestre, (CAIXA_MESTRE[0] - 26, CAIXA_MESTRE[1] - 26), mestre)
        vidro.divisor(img, BARRA_LATERAL, 36, 584)

        for caixa in CARTOES[vista]:
            cartao = vidro.frescor(base, caixa, raio=24, veu=(255, 255, 255, 24),
                                   borda=(255, 255, 255, 74), sombra=115, desfoque=9)
            img.paste(cartao, (caixa[0] - 26, caixa[1] - 26), cartao)

        cls._cenario_cache[vista] = img
        return img

    @classmethod
    def _superficies(cls):
        """Pilulas e botoes da situacao atual: (caixa, estilo)."""
        e = cls._estado
        lista = [
            ((36, 130, 226, 174), "nav" if e["vista"] == "geral"
             else ("nav_foco" if e["hover"] == "nav_geral" else None)),
            ((36, 182, 226, 226), "nav" if e["vista"] == "discord"
             else ("nav_foco" if e["hover"] == "nav_discord" else None)),
            ((36, 468, 226, 516), "ouro_foco" if e["hover"] == "guardar" else "ouro"),
            ((36, 528, 226, 576), "vazado_foco" if e["hover"] == "painel" else "vazado"),
        ]
        if e["vista"] == "geral":
            for chave, caixa, campo, valor in PILULAS:
                ativa = e[campo] == valor
                foco = e["hover"] == chave
                if ativa:
                    est = "ouro_foco" if foco else "ouro"
                else:
                    est = "fresco_foco" if foco else "fresco"
                lista.append((caixa, est))
        else:
            foco = e["hover"] == "abrir"
            lista.append(((298, 510, 700, 558), "vazado_foco" if foco else "vazado"))
        return [(c, s) for c, s in lista if s]

    @classmethod
    def _repintar(cls):
        """Remonta a imagem e reaplica a cor de fundo de cada texto."""
        e = cls._estado
        img = cls._cenario(e["vista"]).copy()
        for caixa, estilo in cls._superficies():
            op = ESTILOS[estilo]
            p = vidro.pilula(img, caixa, raio=op["raio"], veu=op.get("veu"),
                             borda=op["borda"], cor=op.get("cor"))
            img.paste(p, (int(caixa[0]), int(caixa[1])), p)

        cls._foto = ImageTk.PhotoImage(img)
        cls._camada.configure(image=cls._foto)
        cls._master = img

        cls.janela.update_idletasks()
        # Cada widget mostra o recorte exato da imagem que tem por baixo.
        # Uma cor so nao acompanha o degrade e deixava retangulos visiveis.
        for w in cls._amostrar:
            try:
                x, y = w.winfo_x(), w.winfo_y()
                ww, hh = w.winfo_width(), w.winfo_height()
                if ww < 3 or hh < 3:
                    continue
                x0, y0 = max(0, x), max(0, y)
                x1 = min(img.width, x + ww)
                y1 = min(img.height, y + hh)
                if x1 - x0 < 3 or y1 - y0 < 3:
                    continue
                # fundo aproximado ja na primeira vez (evita relampago preto)
                w.configure(bg=vidro.amostra(img, (x0 + x1) // 2, (y0 + y1) // 2))
                if not w.winfo_ismapped():
                    continue
                recorte = img.crop((x0, y0, x1, y1))
                foto = ImageTk.PhotoImage(recorte)
                w._fundo = foto          # referencia viva, senao o GC apaga
                # trava a dimensao: sem isto o texto volta a pedir mais
                # espaco que o recorte e fica uma tira com outra cor
                w.configure(image=foto, compound="center",
                            width=x1 - x0, height=y1 - y0)
            except tk.TclError:
                pass

        # texto das pilulas: escuro sobre amarelo, branco sobre o resto
        for lb, campo, valor in cls._rotulos_pilula:
            ativa = cls._estado[campo] == valor
            lb.configure(fg=ESCURO_OURO if ativa else "#ffffff")

    # ------------------------------------------------------------------
    # widgets por cima da imagem
    # ------------------------------------------------------------------
    @classmethod
    def _txt(cls, x, y, texto, tam=10, negrito=False, cor="#ffffff",
             ancora="nw", grupo="comum", wrap=None, alvo=None):
        op = dict(font=("Segoe UI", tam, "bold" if negrito else "normal"),
                  fg=cor, bg="#000000", bd=0, highlightthickness=0,
                  padx=0, pady=0)   # padx/pady vem 1 por omissao: +2px de desvio
        if wrap:
            op.update(wraplength=wrap, justify="left")
        if ancora == "center":
            op.update(anchor="center")
        lb = tk.Label(cls.janela, text=texto, **op)
        onde = dict(x=x, y=y, anchor="center" if ancora == "center" else ancora)
        lb._grupo = grupo
        lb._onde = onde
        lb._alvo = alvo
        lb.place(**onde)
        cls._amostrar.append(lb)
        if alvo:
            lb.bind("<Enter>", lambda ev: cls._passar(alvo))
            lb.bind("<Leave>", lambda ev: cls._passar(None))
            lb.bind("<Button-1>", lambda ev: cls._acoes[alvo]())
            lb.configure(cursor="hand2")
        return lb

    @classmethod
    def _area(cls, caixa, chave, acao=None, grupo="comum"):
        x0, y0, x1, y1 = caixa
        lb = tk.Label(cls.janela, bg="#000000", bd=0, highlightthickness=0,
                      padx=0, pady=0, cursor="hand2")
        onde = dict(x=x0, y=y0, width=x1 - x0, height=y1 - y0)
        lb._grupo = grupo
        lb._onde = onde
        lb.place(**onde)
        lb.bind("<Enter>", lambda ev: cls._passar(chave))
        lb.bind("<Leave>", lambda ev: cls._passar(None))
        if acao:
            lb.bind("<Button-1>", lambda ev: acao())
            cls._acoes[chave] = acao
        cls._amostrar.append(lb)
        return lb

    @classmethod
    def _passar(cls, chave):
        if cls._estado["hover"] == chave:
            return
        cls._estado["hover"] = chave
        cls._repintar()

    @classmethod
    def _ver(cls, nome):
        if cls._estado["vista"] == nome:
            return
        cls._estado["vista"] = nome
        for w in cls._amostrar:
            g = getattr(w, "_grupo", "comum")
            if g == "comum":
                continue
            if g == nome:
                w.place(**w._onde)
            else:
                w.place_forget()
        cls._repintar()

    # ------------------------------------------------------------------
    # janela principal
    # ------------------------------------------------------------------
    @classmethod
    def iniciar_gui_loop(cls, nome_ai_override=None):
        if cls.janela is not None:
            return

        try:
            with open(BRAIN_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                modelos = data.get("modelos_ativos", {"local": "nvidia", "discord": "groq"})
                vtuber_ativo = data.get("vtuber_overlay_ativo", False)
                nome_ai = data.get("personality", {}).get("name", "IA")
                discord_ativo = data.get("discord_active", False)
                total_guilds = len(data.get("discord_guilds_cache", []) or [])
        except Exception:
                modelos = {"local": "nvidia", "discord": "groq"}
                vtuber_ativo = False
                nome_ai = "IA"
                discord_ativo = False
                total_guilds = 0

        if nome_ai_override:
            nome_ai = nome_ai_override

        cls.janela = tk.Tk()
        cls.janela.title(f"Haimiya System - {nome_ai}")
        cls.janela.geometry(f"{W_JANELA}x{A_JANELA}")
        _centrar(cls.janela)
        cls.janela.resizable(False, False)
        cls.janela.configure(bg=BG_COLOR)
        # a cor chave la' fora dos cantos arredondados fica transparente,
        # e' isso que arredonda a propria janela
        try:
            cls.janela.wm_attributes("-transparentcolor", BG_COLOR)
        except tk.TclError:
            pass

        # o painel do discord continua a usar os widgets ttk
        style = ttk.Style(cls.janela)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("Vertical.TScrollbar", background=HIGHLIGHT_COLOR,
                        troughcolor=BG_COLOR, bordercolor=BG_COLOR, arrowcolor=TEXT_DIM)

        cls._base = vidro.fundo(W_JANELA, A_JANELA)
        cls._cenario_cache = {}
        cls._amostrar = []
        cls._acoes = {}
        cls._rotulos_pilula = []
        cls._estado = {
            "vista": "geral",
            "hover": None,
            "local": modelos.get("local", "nvidia"),
            "modelos_discord": modelos.get("discord", "groq"),
            "vtuber": bool(vtuber_ativo),
        }

        # imagem de fundo de toda a janela
        cls._camada = tk.Label(cls.janela, bd=0, highlightthickness=0, bg=BG_COLOR)
        cls._camada.place(x=0, y=0, width=W_JANELA, height=A_JANELA)

        # --- areas de clique (fica por baixo dos textos) ---
        cls._area((36, 130, 226, 174), "nav_geral", lambda: cls._ver("geral"))
        cls._area((36, 182, 226, 226), "nav_discord", lambda: cls._ver("discord"))
        cls._area((36, 468, 226, 516), "guardar", cls.salvar)
        cls._area((36, 528, 226, 576), "painel",
                  lambda: cls.abrir_gui_discord(cls.janela))

        for chave, caixa, campo, valor in PILULAS:
            cls._area(caixa, chave, cls._escolher(campo, valor), grupo="geral")
        cls._area((298, 510, 700, 558), "abrir",
                  lambda: cls.abrir_gui_discord(cls.janela), grupo="discord")

        # --- barra lateral ---
        cls._txt(42, 42, "☀  HAIMIYA", tam=20, negrito=True, cor=REM_YELLOW)
        cls._txt(44, 80, "Painel de Controlo", tam=9, cor=BRANCO_QUENTE)
        cls._txt(58, 144, "⚙   GERAL", tam=11, negrito=True, alvo="nav_geral")
        cls._txt(58, 196, "💬   DISCORD", tam=11, negrito=True, alvo="nav_discord")
        cls._txt(131, 492, "💾  GUARDAR", tam=10, negrito=True,
                 cor=ESCURO_OURO, ancora="center", alvo="guardar")
        cls._txt(131, 552, "💬  PAINEL DISCORD", tam=9, negrito=True,
                 cor="#ffdada", ancora="center", alvo="painel")

        # --- vista GERAL ---
        g = "geral"
        cls._txt(298, 72, "🧠  MODELO LOCAL (PC)", tam=10, negrito=True,
                 cor="#ffffff", grupo=g)
        cls._txt(431, 150, "🚀  NVIDIA", tam=11, negrito=True, ancora="center",
                 grupo=g, alvo="m_local_nvidia")
        cls._txt(711, 150, "⚡  GROQ", tam=11, negrito=True, ancora="center",
                 grupo=g, alvo="m_local_groq")
        cls._txt(298, 262, "🌐  MODELO DO DISCORD", tam=10, negrito=True,
                 cor="#ffffff", grupo=g)
        cls._txt(431, 334, "🚀  NVIDIA", tam=11, negrito=True, ancora="center",
                 grupo=g, alvo="m_disc_nvidia")
        cls._txt(711, 334, "⚡  GROQ", tam=11, negrito=True, ancora="center",
                 grupo=g, alvo="m_disc_groq")
        cls._txt(298, 452, "🎭  AVATAR VIRTUAL", tam=10, negrito=True,
                 cor="#ffffff", grupo=g)
        cls._txt(431, 524, "✨  ATIVAR", tam=11, negrito=True, ancora="center",
                 grupo=g, alvo="av_on")
        cls._txt(711, 524, "🌑  DESATIVAR", tam=11, negrito=True, ancora="center",
                 grupo=g, alvo="av_off")

        cls._rotulos_pilula = [
            (cls._janela_rotulo("m_local_nvidia"), "local", "nvidia"),
            (cls._janela_rotulo("m_local_groq"), "local", "groq"),
            (cls._janela_rotulo("m_disc_nvidia"), "modelos_discord", "nvidia"),
            (cls._janela_rotulo("m_disc_groq"), "modelos_discord", "groq"),
            (cls._janela_rotulo("av_on"), "vtuber", True),
            (cls._janela_rotulo("av_off"), "vtuber", False),
        ]

        # --- vista DISCORD ---
        d = "discord"
        # o ponto de estado e' texto comum, nao emoji: o emoji sai
        # monocromatico e o verde/vermelho perdia-se
        cor_estado = "#54e08a" if discord_ativo else "#ff8a8a"
        marca = "●"
        estado = "ONLINE" if discord_ativo else "OFFLINE"
        cls._txt(298, 72, "📡  ESTADO DA LIGAÇÃO", tam=10, negrito=True,
                 cor="#ffffff", grupo=d)
        cls._txt(302, 116, f"{marca}  Bot no Discord: {estado}", tam=14,
                 negrito=True, cor=cor_estado, grupo=d)
        cls._txt(302, 158, f"🛡️  Servidores vistos pelo bot: {total_guilds}",
                 tam=10, cor=BRANCO_QUENTE, grupo=d)
        if not total_guilds:
            cls._txt(302, 194, "Liga a IA e abre o painel outra vez para a lista atualizar.",
                     tam=9, cor=BRANCO_QUENTE, grupo=d, wrap=520)
        cls._txt(298, 302, "⚙️  CONFIGURAÇÃO AVANÇADA", tam=10, negrito=True,
                 cor="#ffffff", grupo=d)
        cls._txt(302, 342,
                 "Regras do servidor, menções, autopost, foco em utilizador "
                 "e lista de servidores.", tam=10, cor=BRANCO_QUENTE,
                 grupo=d, wrap=520)
        cls._txt(499, 534, "⚙  ABRIR PAINEL COMPLETO", tam=10, negrito=True,
                 cor="#ffdada", ancora="center", grupo=d, alvo="abrir")

        # esconde a vista que nao esta ativa
        for w in cls._amostrar:
            if getattr(w, "_grupo", "comum") not in ("comum", cls._estado["vista"]):
                w.place_forget()

        cls.janela.protocol("WM_DELETE_WINDOW", lambda: cls.janela.withdraw())
        cls._repintar()
        # a janela ainda nao esta mapeada no primeiro repintar, por isso os
        # widgets ficavam sem imagem; repinta assim que aparece
        cls.janela.after(250, cls._repintar)
        print(" [GUI] Painel de controlo pronto (vidro quente).")
        cls._comandos = queue.Queue()
        cls._bombeia_comandos()
        cls.janela.mainloop()

    # ------------------------------------------------------------------
    # acoes
    # ------------------------------------------------------------------
    @classmethod
    def _escolher(cls, campo, valor):
        def acao():
            cls._estado[campo] = valor
            cls._repintar()
        return acao

    @classmethod
    def _janela_rotulo(cls, chave):
        """Label do texto centrado numa pilula, ja criado."""
        for w in cls._amostrar:
            if getattr(w, "_alvo", None) == chave:
                return w
        return None

    @classmethod
    def salvar(cls):
        if os.path.exists(BRAIN_FILE):
            with open(BRAIN_FILE, 'r', encoding='utf-8') as f:
                dados = json.load(f)
            e = cls._estado
            dados.update({"vtuber_overlay_ativo": e["vtuber"]})
            if "modelos_ativos" not in dados:
                dados["modelos_ativos"] = {}
            dados["modelos_ativos"]["local"] = e["local"]
            dados["modelos_ativos"]["discord"] = e["modelos_discord"]
            with open(BRAIN_FILE, 'w', encoding='utf-8') as f:
                json.dump(dados, f, indent=4, ensure_ascii=False)
            print(" [SISTEMA] Configurações guardadas no cérebro!")
        cls.janela.withdraw()

    @classmethod
    def abrir_gui_discord(cls, parent_janela):
        janela_discord = tk.Toplevel(parent_janela)
        janela_discord.title("💛 Painel Mestre do Discord")
        janela_discord.geometry("1100x850")
        janela_discord.configure(bg=BG_COLOR)

        try:
            with open(BRAIN_FILE, 'r', encoding='utf-8') as f: data = json.load(f)
        except Exception: data = {}

        var_discord_on = tk.BooleanVar(value=data.get("discord_active", False))
        var_music_on = tk.BooleanVar(value=data.get("discord_music_mode", False))
        var_server = tk.BooleanVar(value=data.get("discord_server_active", True))
        var_mentions = tk.BooleanVar(value=data.get("discord_mentions", True))
        var_dinamismo = tk.BooleanVar(value=data.get("discord_dinamismo", True))
        var_autopost = tk.IntVar(value=data.get("discord_auto_post", 0))
        var_unit = tk.StringVar(value=data.get("discord_auto_post_unit", "Minutos"))
        var_target_on = tk.BooleanVar(value=data.get("discord_target_user_active", False))
        var_dm = tk.BooleanVar(value=data.get("discord_dm_active", False))
        var_dm_dono = tk.BooleanVar(value=data.get("discord_dm_dono_always", False))
        target_name = data.get("discord_target_user_name", "")

        disabled_guilds = data.get("discord_disabled_guilds", [])
        guilds_list = data.get("discord_guilds_cache", [])

        container = tk.Frame(janela_discord, bg=BG_COLOR)
        container.pack(fill="both", expand=True, padx=20, pady=10)

        left_col = tk.Frame(container, bg=BG_COLOR)
        left_col.pack(side="left", fill="both", expand=True, padx=(0, 15))

        right_col = tk.Frame(container, bg=BG_COLOR)
        right_col.pack(side="right", fill="both", expand=True, padx=(15, 0))

        tk.Label(left_col, text="⚙️ GERAL E OPERAÇÃO", font=("Segoe UI", 10, "bold"), bg=BG_COLOR, fg=REM_RED).pack(anchor="w", pady=(0, 5))
        f_main = tk.Frame(left_col, bg=SURFACE_COLOR, padx=15, pady=10)
        f_main.pack(fill="x", pady=5)
        criar_checkbutton(f_main, " 🔴 LIGAR A IA NO DISCORD", var_discord_on, fg_color="#f38ba8").pack(anchor="w", pady=2)
        criar_checkbutton(f_main, " 🎵 Ativar Modo Música (Bloqueia Escuta de Voz)", var_music_on).pack(anchor="w", pady=2)

        tk.Label(left_col, text="🛡️ REGRAS DE SERVIDOR", font=("Segoe UI", 10, "bold"), bg=BG_COLOR, fg=REM_RED).pack(anchor="w", pady=(15, 5))
        f_server = tk.Frame(left_col, bg=SURFACE_COLOR, padx=15, pady=10)
        f_server.pack(fill="x", pady=5)
        criar_checkbutton(f_server, " Responder livremente (Texto e Voz)", var_server).pack(anchor="w", pady=2)
        criar_checkbutton(f_server, " Permitir que responda a Menções (@)", var_mentions).pack(anchor="w", pady=2)
        criar_checkbutton(f_server, " Ativar Dinamismo (Zoações e Offline)", var_dinamismo).pack(anchor="w", pady=2)

        tk.Label(left_col, text="⏱️ INTERVALO AUTO-POST (0 = Desligado)", font=("Segoe UI", 10, "bold"), bg=BG_COLOR, fg=TEXT_DIM).pack(anchor="w", pady=(15, 5))
        f_tempo = tk.Frame(left_col, bg=SURFACE_COLOR, padx=15, pady=10)
        f_tempo.pack(fill="x", pady=5)
        frame_t_inner = tk.Frame(f_tempo, bg=SURFACE_COLOR)
        frame_t_inner.pack(anchor="w")
        e_time = tk.Entry(frame_t_inner, textvariable=var_autopost, width=8, bg=HIGHLIGHT_COLOR, fg=TEXT_COLOR, font=("Segoe UI", 11), insertbackground=TEXT_COLOR, relief="flat")
        e_time.pack(side="left", padx=(0, 10), ipady=3)
        cb_unit = ttk.Combobox(frame_t_inner, textvariable=var_unit, values=["Segundos", "Minutos"], width=12, state="readonly", font=("Segoe UI", 10))
        cb_unit.pack(side="left", ipady=2)

        tk.Label(left_col, text="🎯 FOCO EM USUÁRIO", font=("Segoe UI", 10, "bold"), bg=BG_COLOR, fg=REM_RED).pack(anchor="w", pady=(15, 5))
        f_alvo = tk.Frame(left_col, bg=SURFACE_COLOR, padx=15, pady=10)
        f_alvo.pack(fill="x", pady=5)
        criar_checkbutton(f_alvo, " Responder a TODAS as mensagens da pessoa", var_target_on).pack(anchor="w", pady=2)
        tk.Label(f_alvo, text="Nome (@ ou Nick):", bg=SURFACE_COLOR, fg=TEXT_DIM, font=("Segoe UI", 9)).pack(anchor="w", pady=(5, 2))
        entry_target = tk.Entry(f_alvo, bg=HIGHLIGHT_COLOR, fg=TEXT_COLOR, insertbackground=TEXT_COLOR, relief="flat", font=("Segoe UI", 11))
        entry_target.insert(0, target_name)
        entry_target.pack(fill="x", pady=2, ipady=4)

        tk.Label(left_col, text="🔒 PRIVADO (DM)", font=("Segoe UI", 10, "bold"), bg=BG_COLOR, fg=REM_RED).pack(anchor="w", pady=(15, 5))
        f_dm = tk.Frame(left_col, bg=SURFACE_COLOR, padx=15, pady=10)
        f_dm.pack(fill="x", pady=5)
        criar_checkbutton(f_dm, " Responder Mensagens no Privado", var_dm).pack(anchor="w", pady=2)
        criar_checkbutton(f_dm, " IGNORAR TRAVA: Sempre responder ao Dono", var_dm_dono).pack(anchor="w", pady=2)

        tk.Label(right_col, text="📡 SERVIDORES ATIVOS (Ligue o Bot primeiro)", font=("Segoe UI", 11, "bold"), bg=BG_COLOR, fg=REM_YELLOW).pack(anchor="w", pady=(0, 10))

        canvas_bg = tk.Frame(right_col, bg=SURFACE_COLOR, bd=0)
        canvas_bg.pack(fill="both", expand=True)

        canvas = tk.Canvas(canvas_bg, bg=SURFACE_COLOR, highlightthickness=0)
        scrollbar = ttk.Scrollbar(canvas_bg, orient="vertical", command=canvas.yview)
        scroll_frame = tk.Frame(canvas, bg=SURFACE_COLOR)

        scroll_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=scroll_frame, anchor="nw", width=450)
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True, padx=5, pady=5)
        scrollbar.pack(side="right", fill="y")

        guild_vars = {}

        def toggle_all(state):
            for v in guild_vars.values(): v.set(state)

        btn_all = tk.Frame(right_col, bg=BG_COLOR)
        btn_all.pack(fill="x", pady=(10, 0))
        tk.Button(btn_all, text="✅ Ativar Todos", command=lambda: toggle_all(True), bg=SURFACE_COLOR, fg=REM_YELLOW, font=("Segoe UI", 9, "bold"), bd=0, padx=15, pady=5, cursor="hand2").pack(side="left")
        tk.Button(btn_all, text="❌ Desativar Todos", command=lambda: toggle_all(False), bg=SURFACE_COLOR, fg=REM_RED, font=("Segoe UI", 9, "bold"), bd=0, padx=15, pady=5, cursor="hand2").pack(side="left", padx=10)

        if not guilds_list:
            tk.Label(scroll_frame, text="Aguardando a conexão do Bot para ler os servidores...\nFeche esta janela, certifique-se que a IA está online\ne abra novamente.", bg=SURFACE_COLOR, fg=TEXT_DIM, font=("Segoe UI", 10)).pack(pady=40)
        else:
            for guild in guilds_list:
                g_id = str(guild['id'])
                is_active = g_id not in disabled_guilds
                var = tk.BooleanVar(value=is_active)
                guild_vars[g_id] = var

                f_guild = tk.Frame(scroll_frame, bg=HIGHLIGHT_COLOR, pady=8, padx=15)
                f_guild.pack(fill="x", pady=3, padx=5)
                tk.Label(f_guild, text=f"🌐 {guild['name']}", bg=HIGHLIGHT_COLOR, fg=TEXT_COLOR, font=("Segoe UI", 10, "bold")).pack(side="left")
                tk.Checkbutton(f_guild, text="Ativo", variable=var, bg=HIGHLIGHT_COLOR, fg=REM_RED, selectcolor=BG_COLOR, activebackground=HIGHLIGHT_COLOR, bd=0, cursor="hand2").pack(side="right")

        def salvar_discord():
            try:
                with open(BRAIN_FILE, 'r', encoding='utf-8') as f: d = json.load(f)
            except Exception: d = {}

            new_disabled = [gid for gid, var in guild_vars.items() if not var.get()]

            d.update({
                "discord_active": var_discord_on.get(),
                "discord_music_mode": var_music_on.get(),
                "discord_mentions": var_mentions.get(),
                "discord_dinamismo": var_dinamismo.get(),
                "discord_server_active": var_server.get(),
                "discord_dm_active": var_dm.get(),
                "discord_dm_dono_always": var_dm_dono.get(),
                "discord_auto_post": var_autopost.get(),
                "discord_auto_post_unit": var_unit.get(),
                "discord_target_user_active": var_target_on.get(),
                "discord_target_user_name": entry_target.get().strip(),
                "discord_disabled_guilds": new_disabled
            })

            with open(BRAIN_FILE, 'w', encoding='utf-8') as f: json.dump(d, f, indent=4, ensure_ascii=False)
            print(" [SISTEMA] Configurações do Discord Atualizadas e Salvas!")
            janela_discord.destroy()

        tk.Button(janela_discord, text="💾 APLICAR CONFIGURAÇÕES DO DISCORD", command=salvar_discord,
                  bg=REM_YELLOW, fg=BG_COLOR, font=("Segoe UI", 11, "bold"),
                  bd=0, cursor="hand2", padx=40, pady=12).pack(pady=(0, 20))

        janela_discord.transient(parent_janela)
        janela_discord.grab_set()
        janela_discord.focus_force()

    @classmethod
    def toggle(cls):
        """Mostra/esconde a janela.

        Este metodo e' chamado de outra thread (o hook de teclado do F4) e o
        Tk NAO aceita isso: o after() de outra thread e' ignorado e o F4
        deixava de funcionar. Por isso aqui so' metemos o comando numa fila
        que a thread do Tk vai buscar.
        """
        cls.na_thread_tk(cls._alternar)

    @classmethod
    def _alternar(cls):
        if cls.janela is None:
            return
        try:
            if cls.janela.state() != "normal":
                cls.janela.deiconify()
                # traz para a frente: sem isto a janela abre mas fica por
                # baixo da consola e parece que "nao responde"
                cls.janela.lift()
                cls.janela.focus_force()
            else:
                cls.janela.withdraw()
        except tk.TclError:
            pass

    @classmethod
    def na_thread_tk(cls, func):
        """Manda uma acao para a thread do Tk (unico sitio seguro)."""
        if cls.janela is None:
            return False
        try:
            cls._comandos.put(func)
            return True
        except Exception:
            return False

    @classmethod
    def _bombeia_comandos(cls):
        """Corre na thread do Tk: executa o que as outras threads pedirem."""
        def ciclo():
            try:
                while True:
                    acao = cls._comandos.get_nowait()
                    try:
                        acao()
                    except Exception as e:
                        print(f" [GUI] acao falhou: {e}")
            except queue.Empty:
                pass
            if cls.janela is not None:
                try:
                    cls.janela.after(60, ciclo)
                except tk.TclError:
                    pass
        try:
            cls.janela.after(60, ciclo)
        except tk.TclError:
            pass
