# ============//======================//================
#region 📚 CHAMADAS E MODOS
# ======================================================
import asyncio
import json
import re
import io
import wave
import torch
import numpy as np
import pyaudio
import requests
import edge_tts
import pygame
import keyboard
import threading
import os
import base64
import time
import subprocess  # Adicionado
import sys         # Adicionado
from PIL import ImageGrab
from datetime import datetime
from groq import Groq
from openai import OpenAI  # Apenas para o LLM principal Kimi via NVIDIA
from dotenv import load_dotenv

# A consola do Windows usa cp1252 e rebenta com emojis (UnicodeEncodeError).
# Passa para UTF-8 logo no arranque, antes de qualquer print.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# O .env tem de ser lido ANTES de qualquer os.getenv. A configuracao da visao
# (logo abaixo) le VISAO_PROVEDOR/VISAO_MODELO: se o load_dotenv() ficar mais
# abaixo no ficheiro, essas variaveis sao lidas vazias e a visao local
# nunca liga, mesmo com tudo escrito no .env.
load_dotenv()

# 🧠 MODELOS DA GROQ — confirmados contra a API (client.models.list()).
# O antigo "llama-3.3-70b-versatile" foi descontinuado e devolvia 404 model_not_found,
# o que fazia TODA a conversa falhar. Estes foram testados a responder.
#
# Medido nesta conta (set/2026) com o prompt real da Haimiya, temperatura 0.9:
#   qwen/qwen3.8-27b   -> emitiu as tags 3/3, 0.52s por resposta
#   openai/gpt-oss-120b -> emitiu as tags 1/3, 0.88s por resposta
#   openai/gpt-oss-20b  -> emitiu as tags 1/3, 0.61s por resposta
# Os "gpt-oss" sao modelos de RAZONAMENTO: o campo `reasoning` consome os
# tokens e, quando o max_tokens acaba a meio do raciocinio, devolvem
# `content` VAZIO - ou seja, a Haimiya ficava calada sem aviso.
# Por isso o texto vai no qwen, que nao tem esse campo.
MODELO_LLM = "qwen/qwen3.8-27b"             # cerebro principal (texto)
MODELO_TRANSCRICAO = "whisper-large-v3-turbo"  # voz -> texto

# 👁️ VISÃO:GROQ (cloud) ou LOCAL (Ollama / LM Studio)
# Tudo pelo .env, sem mexer em codigo. O pedido de visao ja e no formato
# aberto da OpenAI (image_url com base64), que e o mesmo que o Ollama aceita.
#
#   VISAO_PROVEDOR=groq      -> usa a chave GROQ_API_KEY_VISION
#   VISAO_PROVEDOR=local     -> usa o Ollama em http://localhost:11434/v1
#   VISAO_BASE_URL=...       -> muda se usares o LM Studio
#   VISAO_MODELO=...         -> ex: qwen2.5vl:3b, moondream, llama3.2-vision
#
# Modelos locais que cabem em 16 GB de RAM sem GPU NVIDIA:
#   qwen2.5vl:3b   ~3 GB  - melhor escolha, razoavel e leve
#   moondream      ~2 GB  - o mais leve, so paraecrã
#   llama3.2-vision:11b ~8 GB - pesado, so com o resto do sistema fechado
VISAO_PROVEDOR = os.getenv("VISAO_PROVEDOR", "groq").strip().lower()
VISAO_BASE_URL = os.getenv("VISAO_BASE_URL", "http://localhost:11434/v1").strip()
VISAO_MODELO_PADRAO_GROQ = "qwen/qwen3.8-27b"
VISAO_MODELO_PADRAO_LOCAL = "qwen2.5vl:3b"
MODELO_VISAO = os.getenv("VISAO_MODELO", "").strip() or (
    VISAO_MODELO_PADRAO_LOCAL if VISAO_PROVEDOR in ("local", "ollama", "lmstudio")
    else VISAO_MODELO_PADRAO_GROQ
)
VISAO_LOCAL = VISAO_PROVEDOR in ("local", "ollama", "lmstudio")

# 👂 OUVINTE DO PC: ela fica sempre a escutar o audio que o PC reproduz
# (loopback), mas isso NAO gasta tokens: so' guarda o audio num buffer
# rolante de 30 s. A transcricao (Whisper) so' e paga quando perguntas
# 'o que esta a tocar?' ou 'ouviste o que eu disse?'. A deteccao de fala e'
# energetica (sem rede), portanto estar sempre a escutar custa zero tokens.
#
#   AUDIO_PC_HABILITADO=true|false  -> liga/desliga a escuta do PC
#   AUDIO_PC_SEGUNDOS=8             -> segundos transcritos por pergunta
#   AUDIO_PC_PROATIVO=false         -> true = transcreve tambem sozinha quando
#                                      deteta fala (gasta tokens, so' ativa
#                                      se quiseres mesmo)
AUDIO_PC_HABILITADO = os.getenv("AUDIO_PC_HABILITADO", "true").strip().lower() in (
    "1", "true", "sim", "yes")
AUDIO_PC_SEGUNDOS = int(os.getenv("AUDIO_PC_SEGUNDOS", "8") or 8)
AUDIO_PC_PROATIVO = os.getenv("AUDIO_PC_PROATIVO", "false").strip().lower() in (
    "1", "true", "sim", "yes")

# ======================================================
# 🚦 LIMITE DE PEDIDOS ("many requests" / 429)
# ======================================================
# A Groq corta pedidos quando o limite da conta estoura. Sem isto, um unico
# erro matava a resposta da Haimiya na hora e ela ficava calada sem dizer
# nada. Agora: espera, volta a tentar, e se nao houver jeito avisa em portugues.
ESPERAS_RATE_LIMIT = [4, 10, 25]   # segundos entre tentativas


def _e_rate_limit(erro):
    """Diz se a excecao e um limite de pedidos (429 / many requests)."""
    if erro.__class__.__name__ == "RateLimitError":
        return True
    if getattr(erro, "status_code", None) == 429:
        return True
    txt = str(erro).lower()
    return "429" in txt or "rate limit" in txt or "many requests" in txt or "too many" in txt


async def chamada_com_tentativas(func, tentativas_extra=3, o_que="o cerebro"):
    """Chama a API e, se for limite de pedidos, espera e volta a tentar.

    Por omissao sao 4 tentativas com esperas de 4s, 10s e 25s (39s no total).
    Isso porque o limite da Groq conta por minuto: esperar so 4s nao resolve,
    era preciso dar para a janela de 1 minuto passar.

    Devolve a resposta, ou None se desistir. Nao deixa o erro rebentar a
    conversa: quem chama decide o que dizer ao utilizador.
    """
    esperas = ESPERAS_RATE_LIMIT[:tentativas_extra]
    for tentativa in range(len(esperas) + 1):
        try:
            return await asyncio.to_thread(func)
        except Exception as e:
            if not _e_rate_limit(e):
                raise
            if tentativa >= len(esperas):
                print(f" [LIMITE] {o_que}: limite de pedidos da Groq. Desisti apos {tentativa + 1} tentativas.")
                return None
            espera = esperas[tentativa]
            print(f" [LIMITE] {o_que}: 'many requests'. A tentar de novo dentro de {espera}s "
                  f"(tentativa {tentativa + 2}/{len(esperas) + 1})...")
            await asyncio.sleep(espera)
    return None


# 🔥 IMPORTAÇÃO DA INTERFACE GRÁFICA ATUALIZADA
from Arcana.Apps.gui_handler import RemGUI

# 🔥 IMPORTAÇÃO DO SISTEMA DE FERRAMENTAS
from Arcana.Tools.tools_system import ToolsSystem

# 🔥 IMPORTAÇÃO DO SEU MÓDULO DE PESQUISA
import Arcana.Net.search_ddg as search_ddg

# 🔒 PERMISSÕES: quem pode pedir o quê. Vem antes de tudo o resto porque o
#Discord e' que vai trazer papeis (dono/admin/comum) de gente que nao e' o
#dono do programa, e todas as tags passam por aqui antes de fazerem alguma
#coisa no PC.
from Arcana.Tools.permissions import (
    PAPEL_ADMIN, PAPEL_COMUM, PAPEL_DONO, Permissoes,
)
from Arcana.Tools import stt

# O bot do Discord NAO e' importado aqui. Se o discord.py nao estiver
# instalado, este programa tem de continuar a funcionar na mesma (voz local,
# visao, PC); a falha do Discord nao pode ser a falha da Haimiya. Por isso o
# modulo só é carregado quando o Discord e' ligado, em `_ligar_discord`.
DISCORD_BOT = None

# 🔥 IMPORTAÇÃO DO SEU MÓDULO DE AUTOMAÇÃO DE APPS
from Arcana.Aura.app_launcher import AppLauncher 

# Carrega as chaves do ficheiro .env
# (o load_dotenv() ja correu no topo do ficheiro, ANTES da configuracao da visao)
GROQ_API_KEY_LLM = os.getenv("GROQ_API_KEY_LLM")
GROQ_API_KEY_VISION = os.getenv("GROQ_API_KEY_VISION")
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY") # Chave da NVIDIA
#endregion
# ======================================================
#region 🧠 VARIÁVEIS GLOBAIS E PAINEL
# ======================================================
# Cria a pasta automaticamente se ela não existir
os.makedirs("Arcana/armazen", exist_ok=True)

# 🔥 ARQUIVOS FIXOS
BRAIN_FILE = "Arcana/armazen/brain.json"
MEMORIA_FILE = "Arcana/armazen/memoria.json"
SEARCH_MEMORY_FILE = "Arcana/armazen/pesquisa_memoria.json" 

# Comeca LIGADA: a visao so' e' desligada se carregares F2. Antes comecava
# desligada e a Haimiya respondia "nao vejo" sem nunca tentar.
VISAO_HABILITADA = True  # Controlo global do F2
CONTADOR_VISAO = 0       # Contador para limpar a memória visual

# 🔥 SISTEMA DE FERRAMENTAS (global, como VISAO_HABILITADA - inicializado no main)
TOOLS_SYSTEM = None

# 🔒 Quem pode pedir o quê. Sem isto, qualquer pessoa que chegue a call
# mandar a IA abrir programas e mexer nos ficheiros. Inicializado no main
# a partir do brain.json.
PERMISSOES = Permissoes()


def gate_de_permissao(papel_usuario, tag_nome, accao=""):
    """Diz se este papel pode executar esta tag. Devolve (ok, motivo).

    Chamado ANTES de cada execucao de tag no processar_ia. O motivo devolve
    em portugues para a IA poder explicar a recusa em vez de falhar calada.
    """
    if PERMISSOES is None:
        return True, ""
    try:
        ok, motivo = PERMISSOES.pode_tag(papel_usuario, tag_nome)
    except Exception:
        return True, ""      # nunca deixar a segurança ser a causa da falha
    if ok and accao and PERMISSOES.e_perigosa(acao):
        return True, ""      # perigoso: tratado a parte, na confirmation
    return ok, motivo


# 🔒 CONFIRMAÇÕES À ESPERA
# Uma ação perigosa ("apaga a pasta Downloads") não pode acontecer na mesma
# frase em que foi pedida. Fica aqui à espera de um "sim", e só nessa altura
# é executada. A chave é o nome de quem pediu, para a confirmação vá para a
# mesma pessoa que deu a ordem.
PENDENTE_PC = {}

SIM = ("sim", "s", "yes", "y", "podes", "pod", "confirmo", "autorizo",
       "autoriza", "vai", "manda", "faz isso", "faz lá isso", "bora", "ok", "okay")
NAO = ("não", "nao", "no", "n", "cancela", "cancelar", "deixa", "deixar",
       "não faz", "nao faz", "esquece", "esqueça", "pára", "para")


def _chave_pessoa(nome):
    return (nome or "").strip().lower()


def _e_resposta(texto, palavras):
    """Diz se a mensagem é nada mais nada menos uma destas palavras."""
    t = re.sub(r"[^\w\s]", " ", (texto or "").lower()).strip()
    t = re.sub(r"\s+", " ", t)
    return any(t == p or t.startswith(p + " ") or t.startswith(p + "!")
               or t.startswith(p + "?") for p in palavras)


def _confirmacao_aceite(usuario_nome, texto):
    """Se a pessoa respondeu 'sim' ao que estava pendente, devolve a tag.

    Devolve as tags <COMPUTER:...> prontas a executar, ou None. Quem chamou
    junta essas tags à resposta da IA e o bloco de execução faz o que sempre
    fez — não há um segundo caminho de execução para manutenção.

    Se guardou várias tags (uma resposta pode pedir duas coisas), volta
    todas: confirmar uma e não a outra era exatamente o buraco por onde
    passavam os comandos perigosos.
    """
    chave = _chave_pessoa(usuario_nome)
    if chave not in PENDENTE_PC:
        return None
    pendente = PENDENTE_PC.pop(chave)
    tags = pendente["tags"] if "tags" in pendente else [pendente["tag"]]
    resumo = " | ".join(tags)
    if _e_resposta(texto, NAO):
        print(f" [SEGURANÇA] {usuario_nome} cancelou: {resumo}")
        return "CANCELADO"
    if _e_resposta(texto, SIM):
        print(f" [SEGURANÇA] {usuario_nome} CONFIRMOU: {resumo}")
        return "\n".join(tags)
    # Nem sim nem não: a confirmação continua à espera.
    pendente["tags"] = tags
    PENDENTE_PC[chave] = pendente
    return None

# A escuta do PC pode ser ligada/desligada pelo menu (opcao 6) ou pelo F5.
MODO_ESCUTA_ATIVA = False

def abrir_gui_modelos():
    """Abre o painel de controlo unico da Haimiya (o mesmo do F4).
    Antes a opcao 5 do menu abria uma segunda janela, 'Painel de Controle
    IA - Rem', que duplicava a escolha de modelo e ainda usava a paleta
    antiga azul/verde. Passou a ser o mesmo painel, com o mesmo aspeto."""
    if RemGUI.janela is not None:
        RemGUI.toggle()
    else:
        RemGUI.iniciar_gui_loop()
#endregion
# ======================================================
#region 👁️ VISÃO COMPUTACIONAL E INJETORES
# ======================================================
def toggle_visao(e):
    global VISAO_HABILITADA
    VISAO_HABILITADA = not VISAO_HABILITADA
    play_beep("inicio" if VISAO_HABILITADA else "fim")
    print(f"\n[SISTEMA] 👁️ Permissão de Visão (F2): {'LIGADA' if VISAO_HABILITADA else 'DESLIGADA'}")

def toggle_gatilho(e):
    # 🔥 F3 GLOBAL RESOLVIDO: Não trava mais no microfone!
    if os.path.exists(BRAIN_FILE):
        try:
            with open(BRAIN_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            novo_estado = not data.get("trigger_active", False)
            data["trigger_active"] = novo_estado
            with open(BRAIN_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            play_beep("inicio" if novo_estado else "fim")
            print(f"\n[SISTEMA] 🎤 Gatilho de Voz (F3): {'LIGADO' if novo_estado else 'DESLIGADO'}")
        except Exception as ex:
            # Antes falhava em silencio: o F3 parecia funcionar e nada acontecia.
            print(f"\n[SISTEMA] Erro ao alternar o gatilho de voz: {ex}")

def requer_visao(texto):
    """Diz se o utilizador pediu para ela olhar para o ecrã.

    A lista foi alargada porque 'o que tens no ecra' ou 'o que estou a
    fazer agora' caem fora dos padroes antigos e a Haimiya ficava calada.
    """
    texto_min = texto.lower()
    padrao_palavras = (r"\b(olha|olhar|veja|ver|vê|ve|tela|ecra|ecrã|imagem|foto|"
                       r"analisa|analise|analisar|lê|leia|lê-me|vendo|mostra|"
                       r"mostrar|aconteceu|acontece)\b")
    frases_exatas = ["o que é isso", "o que e isso", "o que tem na tela",
                     "o que tens no ecra", "o que tens no ecrã", "aqui esta",
                     "neste ecra", "neste ecrã", "no meu ecra", "no meu ecrã",
                     "o que estou a ver", "o que estou a fazer agora",
                     "estou a fazer o que", "o que se passa aqui"]
    if re.search(padrao_palavras, texto_min): return True
    if any(frase in texto_min for frase in frases_exatas): return True
    return False

def requer_despertar(texto, nome_ai):
    texto_min = texto.lower()
    padrao_gatilhos = rf"\b({nome_ai.lower()}|ei|acorda|ouve|escuta)\b"
    return bool(re.search(padrao_gatilhos, texto_min))

# 🔥 O SEU NOVO INJETOR CIRÚRGICO DE COMANDOS DE MÚSICA
def detectar_comando_musica(texto):
    t = texto.lower().strip()
    if re.search(r'\b(pausar|pausa|despausa|resume)\b', t): return "PAUSE"
    if re.search(r'\b(para a música|para tudo|stop|desliga a música|calar a boca)\b', t): return "STOP"
    if re.search(r'\b(pula|próxima|skip|pular|passa)\b', t): return "SKIP"
    
    padrao_tocar = r'\b(toca|tocar|coloca|colocar|põe|bota)\b.*?(música|músicas|som|playlist|rock|kpop|pop|lofi|clássica|jazz|rap|funk|metal|eletrônica|abertura|encerramento)'
    if re.search(padrao_tocar, t):
        query = re.sub(r'\b(toca|tocar|coloca|colocar|põe|bota|a|o|um|umas|uma|alguma|algumas|música|músicas|som|playlist|ai|aí|pra|mim)\b', '', t).strip()
        query = re.sub(r'[^a-zA-Z0-9\s\-\u00C0-\u00FF]', '', query).strip()
        return f"PLAY:{query}" if query else "PLAY:uma música aleatória"
    
    if len(t.split()) <= 6 and re.match(r'^(toca|coloca|põe|bota)\b', t):
        query = re.sub(r'^(toca|coloca|põe|bota|a|o|um|uma|umas|alguma)\b', '', t).strip()
        return f"PLAY:{query}" if query else "PLAY:uma recomendação aleatória"
        
    return None

def _janela_em_foco():
    """Caixa (x0, y0, x1, y1) da janela que esta em foco, ou None.

    Para a visao e' melhor que o ecra inteiro: um print de 1366x768 encolhe
    para 512px e o texto fica ilegivel, e o modelo acaba a inventar conteudo.
    Se so' dermos a janela da frente, o texto fica legivel e a resposta
    deixa de ser adivinhacao.
    """
    try:
        import ctypes
        from ctypes import wintypes
        u = ctypes.windll.user32
        hwnd = u.GetForegroundWindow()
        if not hwnd:
            return None
        r = wintypes.RECT()
        if not u.GetWindowRect(hwnd, ctypes.byref(r)):
            return None
        x0, y0, x1, y1 = r.left, r.top, r.right, r.bottom
        if x1 - x0 < 200 or y1 - y0 < 200:
            return None   # janela minuscula: nao vale a pena
        return (x0, y0, x1, y1)
    except Exception:
        return None


def capturar_tela_b64(max_lado=1024, so_janela=False):
    """Captura o ecrã em JPEG base64.

    max_lado menor = menos "tokens de imagem" = resposta mais rapozinha.
    so_janela=True captura so' a janela em foco (texto legivel -> o modelo
    deixa de inventar coisas que nao estao no ecra).
    """
    try:
        caixa = _janela_em_foco() if so_janela else None
        img = ImageGrab.grab(bbox=caixa) if caixa else ImageGrab.grab()
        img.thumbnail((max_lado, max_lado))
        buffered = io.BytesIO()
        img.save(buffered, format="JPEG", quality=70)
        return base64.b64encode(buffered.getvalue()).decode('utf-8')
    except Exception as e:
        print(f" Erro ao capturar ecrã: {e}")
        return None
#endregion
# ======================================================
#region 🧠 BRAIN E PERSISTÊNCIA
# ======================================================
def carregar_brain():
    if not os.path.exists(BRAIN_FILE):    
        return {}, "Sistema Padrão", "Assistente", False, False, {"local": "nvidia"}, False # Agora retorna 7 valores corretos
    
    with open(BRAIN_FILE, 'r', encoding='utf-8') as f:
        brain = json.load(f)
        
    p = brain.get('personality', {'name': 'Assistente', 'role': 'Assistente de IA'})
    nome_ai = p.get('name', 'Assistente')
    traits = "\n- ".join(p.get('traits', []))
    
    r = "\n- ".join(brain.get('rules', {}).get('response_style', []))
    s = brain.get('emotional_analysis', {}).get('sentiment', 'Neutral')
    trigger = brain.get("trigger_active", False)
    discord_active = brain.get("discord_active", False) 
    modelos = brain.get("modelos_ativos", {"local": "nvidia", "discord": "groq"})
    vtuber_ativo = brain.get("vtuber_overlay_ativo", False)
    
    relacionamentos = brain.get('relationships', {})
    nome_user = list(relacionamentos.keys())[0] if relacionamentos else "Mestre"
    user_data = relacionamentos.get(nome_user, {})
    relacao = f"Nome do Usuário com quem você está falando: {nome_user}\nRelação: {user_data.get('relationship', 'Mestre')}\nComportamento com ele: {user_data.get('behavior', '')}"
    
    vocab_dict = brain.get('vocabulário', {})
    vocabulario = "\n- ".join([f"{k}: {v}" for k, v in vocab_dict.items()])

    tela_atual = brain.get('visual_context', {}).get('screen_content', '')

    prompt = (
        f"Nome: {nome_ai}\n"
        f"Papel: {p.get('role', 'Assistente')}\n\n"
        f"Traços de Personalidade:\n- {traits}\n\n"
        f"Sobre o Usuário:\n{relacao}\n\n"
        f"Estado Emocional: {s}\n\n"
        f"Diretrizes de Conversa (Incorpore de forma fluida e natural, varie as estruturas das frases):\n- {r}\n\n"
        f"Vocabulário Contextual (Use estas palavras/gírias de forma esporádica e APENAS se encaixar perfeitamente no assunto):\n- {vocabulario}"
    )
    
    if tela_atual:
        prompt += f"\n\n[CONTEXTO VISUAL ATUAL DA TELA]:\n- {tela_atual}"
    
    # 🔥 Retornando 7 variáveis rigorosamente na ordem correta
    return brain, prompt, nome_ai, trigger, discord_active, modelos, vtuber_ativo

def salvar_gatilho_brain(estado):
    if os.path.exists(BRAIN_FILE):
        with open(BRAIN_FILE, 'r', encoding='utf-8') as f: data = json.load(f)
        data["trigger_active"] = estado
        with open(BRAIN_FILE, 'w', encoding='utf-8') as f: json.dump(data, f, indent=4, ensure_ascii=False)

def salvar_discord_brain(estado):
    if os.path.exists(BRAIN_FILE):
        with open(BRAIN_FILE, 'r', encoding='utf-8') as f: data = json.load(f)
        data["discord_active"] = estado
        with open(BRAIN_FILE, 'w', encoding='utf-8') as f: json.dump(data, f, indent=4, ensure_ascii=False)

def salvar_visao_brain(descricao):
    if os.path.exists(BRAIN_FILE):
        with open(BRAIN_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if "visual_context" not in data: data["visual_context"] = {}
        data["visual_context"]["screen_content"] = descricao
        with open(BRAIN_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
#endregion
# ======================================================
#region 📚 GERENCIADOR DE MEMÓRIA
# ======================================================
def carregar_memoria():
    if not os.path.exists(MEMORIA_FILE): return {"master_summary": "", "recent_summaries": [], "mensagens": []}
    try:
        with open(MEMORIA_FILE, 'r', encoding='utf-8') as f: return json.load(f)
    except: return {"master_summary": "", "recent_summaries": [], "mensagens": []}

def salvar_memoria(memoria):
    with open(MEMORIA_FILE, 'w', encoding='utf-8') as f:
        json.dump(memoria, f, indent=4, ensure_ascii=False)

def carregar_memoria_pesquisa():
    if not os.path.exists(SEARCH_MEMORY_FILE): return {"master_search_summary": "", "recent_searches": []}
    try:
        with open(SEARCH_MEMORY_FILE, 'r', encoding='utf-8') as f: return json.load(f)
    except: return {"master_search_summary": "", "recent_searches": []}

async def gerenciar_memoria_pesquisa(client_llm, query, resultados):
    memoria = carregar_memoria_pesquisa()
    memoria["recent_searches"].append({"query": query, "resultados": resultados[:400]})

    if len(memoria["recent_searches"]) >= 5:
        print("\n [SISTEMA] Otimizando banco de dados de Pesquisas (Resumindo web)...")
        textos_resumo = [f"Busca: '{m['query']}' | Resultado: {m['resultados']}" for m in memoria["recent_searches"]]
        if memoria["master_search_summary"]: textos_resumo.insert(0, f"Conhecimento Web Anterior: {memoria['master_search_summary']}")
        master_resumo = await resumir_com_ia(client_llm, textos_resumo, "Você é um bibliotecário digital. Faça um resumo direto e conciso de todo o conhecimento e fatos adquiridos nestas pesquisas web. Descarte informações irrelevantes e foque apenas nos fatos úteis que podem servir de contexto no futuro.")
        if master_resumo:
            memoria["master_search_summary"] = master_resumo
            memoria["recent_searches"] = [] 

    with open(SEARCH_MEMORY_FILE, 'w', encoding='utf-8') as f: json.dump(memoria, f, indent=4, ensure_ascii=False)
    return memoria

async def resumir_com_ia(client_llm, textos, comando):
    texto_junto = "\n".join(textos)
    try:
        res = await chamada_com_tentativas(
            lambda: client_llm.chat.completions.create(
                model=MODELO_LLM,
                messages=[{"role": "system", "content": comando}, {"role": "user", "content": texto_junto}],
                temperature=0.3
            ),
            o_que="resumo de memoria")
        if res is None:
            return ""
        return res.choices[0].message.content
    except Exception as e:
        print(f" Erro ao resumir memória: {e}")
        return ""

async def gerenciar_e_salvar_memoria(client_llm, sender, message):
    memoria = carregar_memoria()
    agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    memoria["mensagens"].append({"timestamp": agora, "sender": sender, "message": message})

    # 🧠 RAMO VETORIAL: guarda também na memória de longo prazo (ChromaDB)
    # para o RAG recuperar depois. Falha silenciosa se não estiver instalado.
    try:
        from Arcana.Memoria.vector_store import get_vector_memory
        get_vector_memory().add_text(
            f"[{sender}] {message}",
            {"timestamp": agora, "sender": sender, "tipo": "conversa"},
        )
    except Exception:
        pass

    if len(memoria["mensagens"]) >= 15:
        print("\n [SISTEMA] Otimizando memória (Resumindo conversas antigas)...")
        msgs_para_resumir = memoria["mensagens"][:10]
        textos_resumo = [f"[{m['timestamp']}] {m['sender']}: {m['message']}" for m in msgs_para_resumir]
        
        novo_resumo = await resumir_com_ia(client_llm, textos_resumo, "Faça um resumo direto e curto sobre o que foi conversado nessas mensagens.")
        if novo_resumo:
            memoria["recent_summaries"].append(novo_resumo)
            memoria["mensagens"] = memoria["mensagens"][10:] 

        if len(memoria["recent_summaries"]) >= 5:
            print(" [SISTEMA] Consolidando Resumo Mestre...")
            textos_master = memoria["recent_summaries"].copy()
            if memoria["master_summary"]: textos_master.insert(0, f"Resumo Histórico: {memoria['master_summary']}")
            master_resumo = await resumir_com_ia(client_llm, textos_master, "Integre todos esses resumos em um único 'Resumo Mestre' detalhando tudo o que já aconteceu com o usuário.")
            if master_resumo:
                memoria["master_summary"] = master_resumo
                memoria["recent_summaries"] = [] 

    salvar_memoria(memoria)
    return memoria

def construir_historico_para_api(sys_prompt, memoria, nome_ai, launcher=None):
    agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # 🔥 INJETOR DE AUTORIDADE E CAPACIDADES CRÍTICAS 🔥
    prompt_completo = sys_prompt + "\n\n[SISTEMA DE CAPACIDADES MÁXIMAS]:"
    prompt_completo += "\n1. CONTROLO DE MÚSICA: Você É o bot de música. Nunca diga que não pode tocar. Use OBRIGATORIAMENTE a tag <PLAY:pedido> para tocar qualquer coisa no Discord."
    prompt_completo += "\n2. CONTROLO DO PC: Você tem acesso total ao PC do Nero. Use <APP:abrir:alvo> ou <APP:fechar:alvo> para comandar o computador. Não invente que é apenas uma IA de texto."
    prompt_completo += "\n3. BUSCA WEB: Use [PESQUISAR: termo] para ler notícias e dados atuais. Você é conectada à internet."
    
    prompt_completo += f"\n\n[SISTEMA DE TEMPO]\nO momento atual exato é: {agora}.\nVocê recebe o horário para entender o ritmo da conversa."
    
    prompt_completo += "\n\n[REGRAS ESTRITAS DE RESPOSTA]:"
    prompt_completo += "\n- ZERO ROLEPLAY: Proibido narrar ações físicas, usar itálicos ou asteriscos (ex: *sorri*). Fale como uma pessoa real."
    prompt_completo += "\n- ZERO TAGS FALSAS: Nunca invente tags como <ignore> ou <pensamento>. Use apenas as oficiais ensinadas aqui."
    prompt_completo += "\n- SEJA CURTA E GROSSA: Responda em 1 ou 2 frases curtas. Você odeia textões e explicações desnecessárias."
    
    if launcher and hasattr(launcher, 'obter_nomes_dos_apps'):
        nomes_apps = launcher.obter_nomes_dos_apps()
        prompt_completo += "\n\n[INTEGRAÇÃO COM O COMPUTADOR]:"
        prompt_completo += f"\n📂 APLICATIVOS INSTALADOS: {nomes_apps}."
        prompt_completo += "\nPara abrir ou pesquisar no navegador/youtube, use: <APP:abrir:alvo:termo_de_busca>."
        
        prompt_completo += "\n\n[MANUAL DO PLAYER DE MÚSICA]:"
        prompt_completo += "\n- TOCAR: <PLAY:nome_da_musica>"
        prompt_completo += "\n- PULAR: <SKIP>"
        prompt_completo += "\n- PAUSAR: <PAUSE>"
        prompt_completo += "\n- PARAR: <STOP>"
        prompt_completo += "\n🚨 REGRA DE OURO DA MÚSICA:"
        prompt_completo += "\n1. É OBRIGATÓRIO escrever uma frase sua (entre 1 e 7 palavras) ANTES de colocar a tag. NUNCA envie apenas a tag! (Ex: 'Aqui está a sua música. <PLAY:rock>')."
        prompt_completo += "\n2. NUNCA tente adivinhar nomes de músicas de animes ou séries. O sistema usa o YouTube, por isso gere a tag EXATAMENTE com as palavras que o usuário usou."
        prompt_completo += "\n3. É ESTRITAMENTE PROIBIDO tocar música do nada. NUNCA use a tag <PLAY> se o usuário não lhe deu uma ordem clara para tocar algo."

    if TOOLS_SYSTEM and TOOLS_SYSTEM.enabled:
        prompt_completo += "\n\n[FERRAMENTAS DE AUTOMAÇÃO DO PC]:"
        prompt_completo += "\nVocê pode executar ações reais no computador. Use estas tags:"
        prompt_completo += "\n- <COMPUTER:mover_mouse:x,y> - Mover o cursor para a posição x,y"
        prompt_completo += "\n- <COMPUTER:clicar> - Clique esquerdo"
        prompt_completo += "\n- <COMPUTER:clicar:right,2> - Clique direito ou duplo clique"
        prompt_completo += "\n- <COMPUTER:digitar:texto> - Digitar texto no programa aberto"
        prompt_completo += "\n- <COMPUTER:pressionar:enter> - Pressionar uma tecla"
        prompt_completo += "\n- <COMPUTER:atalho:ctrl+c> - Atalho de teclado"
        prompt_completo += "\n- <COMPUTER:capturar_tela> - Capturar a tela"
        prompt_completo += "\n- <COMPUTER:analisar_tela:o que quer que veja> - Analisar a tela com visão"
        prompt_completo += "\n- <COMPUTER:listar_arquivos:termo> - Procurar arquivos no PC"
        prompt_completo += "\n- <COMPUTER:abrir_pasta:caminho> - Listar o conteúdo de uma pasta"
        prompt_completo += "\n- <COMPUTER:nova_tarefa:nome> - Criar um plano em etapas"
        prompt_completo += "\n- <COMPUTER:status_tarefa> - Ver o progresso da tarefa"
        prompt_completo += "\nREGRA: só use estas tags quando o usuário pedir a ação de verdade. Nunca diga que já fez algo sem executado."

        prompt_completo += "\n\n[PHOTOSHOP - API oficial via COM/ExtendScript]:"
        prompt_completo += "\n- <PS:abrir> - Abrir o Photoshop"
        prompt_completo += "\n- <PS:documento:1920,1080> - Criar documento novo (LARGxALT)"
        prompt_completo += "\n- <PS:layer:NomeDaLayer> - Criar layer"
        prompt_completo += "\n- <PS:forma:retangulo,100,100,400,300> - Desenhar forma (retangulo|circulo|linha)"
        prompt_completo += "\n- <PS:texto:conteudo> - Criar camada de texto"
        prompt_completo += "\n- <PS:cor:FF0000> - Definir cor de frente"
        prompt_completo += "\n- <PS:preencher> - Preencher a seleção com a cor atual. Não funciona em camadas de texto."
        prompt_completo += "\n- <PS:selecionar:tudo|retangulo|nada> - Fazer uma seleção"
        prompt_completo += "\n- <PS:efeito:blur> - Aplicar filtro (blur|nitidez). Precisa de uma seleção ativa."
        prompt_completo += "\n- <PS:ferramenta:pincel|mover|crop> - Trocar de ferramenta"
        prompt_completo += "\n- <PS:desfazer> - Ctrl+Z"
        prompt_completo += "\n- <PS:estado> - Ver documento e layers atuais"
        prompt_completo += "\n- <PS:guardar:C:/Users/K/Imagens/trabalho.psd> - Guardar (só no final, quando o usuário disser)"
        prompt_completo += "\n- <PS:exportar:C:/Users/K/Imagens/saida.jpg> - Exportar (.jpg/.png/.webp/.gif/.tif)"
        prompt_completo += "\n- <PS:camada:Nome> - Escolher qual a layer ativa (para preencher/filtrar)"
        prompt_completo += "\nREGRA PS: cria o documento e as layers, NÃO guardes nem exportes sem o usuário pedir. Confirma sempre o estado antes de afirmar que ficou feito."

        prompt_completo += "\n\n[PRODUÇÃO MUSICAL - teoria, arranjo, mix e master]:"
        prompt_completo += "\n- <MUS:escala:Am,menor> - Notas de uma escala"
        prompt_completo += "\n- <MUS:acorde:C,menor> - Notas e qualidade de um acorde"
        prompt_completo += "\n- <MUS:progressao:C,menor,pop> - Progressão por género"
        prompt_completo += "\n- <MUS:estrutura:trap,140> - Estrutura de一首 com tempos".replace("一首", "uma música")
        prompt_completo += "\n- <MUS:mix:voz|baixo|bateria|sintetizador> - Chain de mixagem por instrumento"
        prompt_completo += "\n- <MUS:master:pop,spotify> - Chain de masterização com alvo de loudness"
        prompt_completo += "\n- <MUS:comp:voz,3,15> - Compressor com ataque/release"
        prompt_completo += "\n- <MUS:reverb:plate|room|hall|delay> - Configuração de reverb/delay"
        prompt_completo += "\n- <MUS:organizar:PASTA> - Organizar samples/projetos/presets"
        prompt_completo += "\nREGRA MUS: escreve em português claro e prático. Dá o valor concreto (dB, Hz, ms, BPM), não conselhos vagos."

        prompt_completo += "\n\n[JOGOS - guias, builds, config e screenshots]:"
        prompt_completo += "\n- <JOGO:pesquisa:Cyberpunk 2077,build> - Pesquisar (dica|guia|quest|build|item|boss|config|mod|tecnico)"
        prompt_completo += "\n- <JOGO:ajuda:estou preso num boss em Elden Ring> - Pesquisa interpretive"
        prompt_completo += "\n- <JOGO:correr> - Ver que jogos estão a correr"
        prompt_completo += "\n- <JOGO:screenshot> - Analisar o ecrã de jogo com visão"
        prompt_completo += "\nREGRA JOGO: quando o usuário travar num jogo, pesquisa na web e dá passos concretos. Não inventes soluções sem pesquisar."

    # Integração de Memórias
    memoria_pesquisa = carregar_memoria_pesquisa()
    if memoria_pesquisa.get("master_search_summary"):
        prompt_completo += f"\n\n[CONHECIMENTO WEB ADQUIRIDO]:\n{memoria_pesquisa['master_search_summary']}"

    if memoria["master_summary"]:
        prompt_completo += f"\n\n[MEMÓRIA DE LONGO PRAZO]:\n{memoria['master_summary']}"
        
    if memoria["recent_summaries"]:
        prompt_completo += "\n\n[ACONTECIMENTOS RECENTES]:\n" + "\n".join(memoria["recent_summaries"])

    # Construção do histórico para a API
    historico = [{"role": "system", "content": prompt_completo}]
    
    for m in memoria["mensagens"]:
        role = "assistant" if m["sender"] == nome_ai else "user"
        if role == "user":
            historico.append({"role": role, "content": f"[Enviado em {m['timestamp']}] {m['message']}"})
        else:
            msg_limpa = m['message'].split("] ", 1)[-1] if m['message'].startswith("[2026") else m['message']
            msg_limpa = re.sub(rf"^{nome_ai} disse:\s*", "", msg_limpa, flags=re.IGNORECASE)
            msg_limpa = re.sub(rf"^{nome_ai}:\s*", "", msg_limpa, flags=re.IGNORECASE)
            historico.append({"role": role, "content": msg_limpa.strip()})
            
    return historico
#endregion
# ======================================================
#region 🎵 FEEDBACKS SONOROS E ÁUDIO
# ======================================================
def play_beep(tipo="inicio"):
    try:
        pygame.mixer.init(frequency=44100, size=-16, channels=2)
        duration = 0.1
        sample_rate = 44100
        n_samples = int(sample_rate * duration)
        freq = 800 if tipo == "inicio" else 400
        t = np.linspace(0, duration, n_samples, False)
        signal = np.sin(2 * np.pi * freq * t) * 0.3
        sound_array = (signal * 32767).astype(np.int16)
        stereo_array = np.column_stack((sound_array, sound_array))
        sound = pygame.sndarray.make_sound(stereo_array)
        sound.play()
    except Exception as e:
        # O beep e' cosmetico: nao vale a pena travar a app, mas nao e' um
        # erro silencioso se o pygame falhar.
        print(f"[AVISO] Beep de confirmacao falhou: {e}")

class LocalVoiceFilter:
    def __init__(self):
        # O silero-vad descarrega uma vez via torch.hub. Sem trust_repo, o torch
        # pergunta interativamente "confia neste repositorio?" e bloqueia o arranque.
        # E se falhar, a app nao pode morrer: a voz tem de continuar a funcionar.
        self.model = None
        try:
            self.model, _ = torch.hub.load(
                repo_or_dir='snakers4/silero-vad',
                model='silero_vad',
                force_reload=False,
                trust_repo=True,
            )
        except TypeError:
            # torch mais antigo: nao aceita trust_repo
            try:
                self.model, _ = torch.hub.load(repo_or_dir='snakers4/silero-vad', model='silero_vad', force_reload=False)
            except Exception as e:
                print(f" Aviso: VAD silero-vad indisponivel ({e}). A usar deteccao por energia.")
        except Exception as e:
            print(f" Aviso: VAD silero-vad nao descarregou ({e}). A usar deteccao por energia.")
    
    def is_human_voice(self, audio_data, rate=16000):
        audio_int16 = np.frombuffer(audio_data, dtype=np.int16)
        if np.max(np.abs(audio_int16)) < 300: return False
        if self.model is None:
            # Sem o modelo, aceita acima do limiar de energia
            return True
        audio_float32 = audio_int16.astype(np.float32) / 32768.0
        tensor = torch.from_numpy(audio_float32)
        with torch.no_grad():
            confidence = self.model(tensor, rate).item()
        return confidence > 0.75

async def microsoft_speak(text): 
    if not text: return
    VOICE = "pt-BR-FranciscaNeural" 
    output_file = "vocal_.mp3"
    
    # 🔥 Limpa tags do sistema (<APP...>, etc)
    text_limpo_voz = re.sub(r'<[^>]+>', '', text).strip()
    
    # 🔥 SALVAÇÃO DA MATEMÁTICA: Se o * estiver entre números, vira "vezes"
    text_limpo_voz = re.sub(r'(?<=\d)\s*\*\s*(?=\d)', ' vezes ', text_limpo_voz)
    
    # 🔥 Arranca qualquer outro asterisco inútil que sobrou (formatação/roleplay)
    text_limpo_voz = text_limpo_voz.replace('*', '') 
    
    if not text_limpo_voz:
        text_limpo_voz = "Comando executado."
        
    communicate = edge_tts.Communicate(text_limpo_voz, VOICE)
    await communicate.save(output_file)
    pygame.mixer.init()
    pygame.mixer.music.load(output_file)
    pygame.mixer.music.play()
    while pygame.mixer.music.get_busy(): await asyncio.sleep(0.1)
    pygame.mixer.quit()

async def whisper_transcription(audio_frames, api_key):
    """Voz -> texto. Agora so' embrulha o stt.py partilhado.

    Antes esta funcao montava o WAV e falava com a Groq aqui dentro. O
    Discord precisa do mesmo pedido para ouvir a call, e ter duas copias
    significa que, quando o modelo muda, uma das duas fica desatualizada.
    """
    wav = stt.em_wav(audio_frames)
    return await asyncio.to_thread(stt.transcrever, wav, api_key, MODELO_TRANSCRICAO)

# 👂 OUVINTE DO PC --------------------------------------------------
async def ouvir_pc_e_descrever(segundos=None):
    """Transcreve o que se ouve no PC agora. E' o UNICO sitio onde a
    escuta do PC gasta tokens, e so' quando o utilizador pergunta.
    Devolve um texto pronto para meter no contexto da IA."""
    from Arcana.Tools.ouvinte_pc import obter_ouvinte
    segundos = segundos or AUDIO_PC_SEGUNDOS
    ouvinte = obter_ouvinte()
    if not ouvinte.a_viver():
        if not ouvinte.iniciar():
            return f"[não consegui abrir a escuta do áudio do PC: {ouvinte.erro}]"
        await asyncio.sleep(1.5)          # deixa encher um bocado o buffer
    if not ouvinte.tem_som():
        return "[o áudio do PC está em silêncio]"
    wav = ouvinte.ultimos_segundos(segundos, so_fala=True)
    if not wav:
        # sem voz no buffer: devolve aviso em vez de gastar tokens a topar
        return "[não há voz audível no áudio do PC agora — só música ou silêncio]"
    texto = await whisper_transcription([wav], GROQ_API_KEY_LLM)
    if not texto:
        return "[o áudio do PC não foi percebido como fala]"
    return texto.strip()
#endregion
# ======================================================
#region 🕹️ CÉREBRO DA IA (PROCESSAMENTO INTEGRADO LLM + SCOUT)
# ======================================================
async def processar_ia(client_nvidia, client_llm, client_vision, sys_prompt, texto, nome_ai, usuario_nome, launcher, modo_chat=False, papel_usuario=PAPEL_DONO, origem="local"):
    """O cerebro. Devolve SEMPRE a resposta final em texto.

    `papel_usuario` e o que decide o que a IA pode executar (ver
    permissions.py). Por omissao e' dono: quem esta ao teclado e' o dono,
    tal como estava antes de o Discord existir. Quem vem do Discord traz o
    papel que o modulo de permissoes lhe deu.

    `origem` distingue a voz local (que fala pelos altifalantes do PC) do
    Discord (que fala no canal de voz, e nao aqui).
    """
    # No Discord a resposta vai para a call/para o canal: escreve-la na
    # consola e um' segunda vez nao ajuda ninguem.
    do_discord = origem == "discord"
    if not modo_chat and not do_discord:
        print(f"{usuario_nome}: {texto}")

    # O que este utilizador pediu e' recusado por falta de permissao. A IA
    # recebe a recusa como contexto e explica-lha com as palavras dela.
    _sem_permissao = set()

# 🔒 Se estava pendente uma acao perigosa e a pessoa respondeu 'sim',
    # a tag dela volta a entrar na resposta e executa como se fosse nova.
    _confirmada = _confirmacao_aceite(usuario_nome, texto)

    await gerenciar_e_salvar_memoria(client_llm, usuario_nome, texto)
    memoria_atual = carregar_memoria()

    # 🧠 RAG: puxa o contexto passado mais parecido com o que esta a ser
    # perguntado agora. Sem isto, a Haimiya esquece o que se falou ontem
    # assim que a conversa passa para o resumo. A busca é vetorial e barata
    # (ChromaDB); se o módulo não estiver instalado, simplesmente não injeta.
    contexto_extra = ""
    try:
        from Arcana.Memoria.vector_store import get_vector_memory
        _vm = get_vector_memory()
        _achados = _vm.search(texto, n_results=3)
        if _achados:
            contexto_extra = "\n".join(f"- {h['text']}" for h in _achados)
    except Exception:
        contexto_extra = ""

    historico_api = construir_historico_para_api(sys_prompt, memoria_atual, nome_ai, launcher)

    if contexto_extra:
        historico_api.append({
            "role": "user",
            "content": ("[MEMÓRIA DE LONGO PRAZO (contexto relevante recuperado "
                        "do que já foi conversado antes)]:\n" + contexto_extra),
        })

    if _confirmada == "CANCELADO":
        historico_api.append({
            "role": "user",
            "content": ("[SISTEMA: o utilizador ACABOU DE CANCELAR uma acao "
                        "perigosa que tinhas pedido para executar. Diz só que "
                        "não fazes isso, numa frase curta, e não voltes a "
                        "oferecer-ma."),
        })
    elif _confirmada is None and _chave_pessoa(usuario_nome) in PENDENTE_PC:
        historico_api.append({
            "role": "user",
            "content": ("[SISTEMA: há uma acao perigosa à espera de "
                        "confirmação e o utilizador não disse sim nem não. "
                        "Pergunta outra vez, de forma curta, o que queres "
                        "fazer a seguir. Não executes nada entretanto."),
        })
    
    # 🔥 INJETOR DE PRESSÃO: Força o LLM a não esquecer a tag da música
    comando_musica = detectar_comando_musica(texto)
    if comando_musica:
        alerta = f"\n\n[ALERTA DE SISTEMA DO CÉREBRO]: Você OBRIGATORIAMENTE deve incluir a tag <{comando_musica}> no final da sua próxima fala para a música obedecer ao usuário. Sem a tag, a música não mudará!"
        historico_api[-1]["content"] += alerta

    # 👁️ LÓGICA DE VISÃO
    # Ver o ecrã do PC é ver a máquina dele: só quem tem o papel certo pede.
    # Sem esta porta, qualquer pessoa na call escrevia "olha o ecra" e recebia
    # uma descrição do que o dono tinha aberto.
    _pode_ver, _motivo_ver = gate_de_permissao(papel_usuario, "COMPUTER")
    # A recusa só entra no histórico se a pessoa PEDIU mesmo o ecrã. Sem
    # esta condição, um utilizador comum levava a frase "não posso ver o
    # ecrã" em cima de todas as perguntas que fazia.
    _pediu_ecra = requer_visao(texto)
    if not _pode_ver and _pediu_ecra:
        print(f" [SEGURANÇA] {usuario_nome} pediu para ver o ecrã e foi recusado: {_motivo_ver}")
        historico_api.append({
            "role": "user",
            "content": (
                f"[SISTEMA DE SEGURANÇA: NÃO FAÇAS ISTO] O utilizador '{usuario_nome}' "
                f"pediu-te para olhares para o ecrã do computador, mas NÃO tens "
                f"permissão: {_motivo_ver} Explica-lhe isso em UMA frase curta, "
                f"sem falar de 'tags', 'sistema' ou 'permissão' como se fosses um "
                f"programa, e sem prometer que vais fazê-lo."
            ),
        })
        _sem_permissao.add("ecra")
    if VISAO_HABILITADA and _pode_ver and _pediu_ecra:
        print(" [SISTEMA] Intenção visual detetada! A analisar o ecrã com o llama...")
        # Local = modelo pequeno: dá-lhe a janela em foco (texto legível) e
        # pede uma resposta curta, senão inventa o que não está no ecrã.
        lado_visao = 512 if VISAO_LOCAL else 1024
        tokens_visao = 150 if VISAO_LOCAL else 1024
        b64_img = capturar_tela_b64(lado_visao, so_janela=VISAO_LOCAL)
        if b64_img:
            if VISAO_LOCAL:
                # Prompt objetivo e temperatura 0: o moondream/gemma3 a
                # temperatura alta inventava coisas que nao estavam no ecra.
                prompt_vision = (
                    f"Vê esta captura de ecrã e responde ao que o utilizador pede: '{texto}'.\n"
                    "Regras: responde SEMPRE em português, no máximo 2 frases curtas; "
                    "só menciona o que consegues ler na imagem; se não tiveres a certeza, "
                    "diz que não tens a certeza em vez de inventar."
                )
            else:
                prompt_vision = f"Descreva a imagem. Identifique contexto, textos, ações e detalhes.\nO usuário pediu: '{texto}'. Foque nisso."
            try:
                res_vision = await chamada_com_tentativas(
                    lambda: client_vision.chat.completions.create(
                        model=MODELO_VISAO,
                        messages=[{
                            "role": "user",
                            "content": [
                                {"type": "text", "text": prompt_vision},
                                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_img}"}}
                            ]
                        }],
                        max_tokens=tokens_visao,
                        temperature=0.0 if VISAO_LOCAL else 0.1
                    ),
                    o_que="visao")
                if res_vision is None:
                    raise RuntimeError("limite de pedidos na visao")
                descricao_imagem = res_vision.choices[0].message.content
                print(" [ANÁLISE SCOUT CONCLUÍDA]")

                salvar_visao_brain(descricao_imagem)
                _, sys_prompt_atualizado, _, _, _, _, *_ = carregar_brain()
                historico_api = construir_historico_para_api(sys_prompt_atualizado, memoria_atual, nome_ai, launcher)
                historico_api[-1]["content"] += "\n\n[SISTEMA: Acabei de analisar o ecrã a teu pedido. O contexto visual atualizado já se encontra na tua mente.]"

            except Exception as e:
                print(f" Erro na API de Visão (Scout): {e}")

    # 👂 LÓGICA DE ESCUTA DO PC (o que está a tocar / o que disseste)
    # Só transcreve quando perguntas -> é o único momento que gasta tokens.
    # Ouvir o áudio do PC é, tal como ver o ecrã, meter-se na máquina dele:
    # porta fechada para quem não tem o papel.
    _pode_ouvir, _motivo_ouvir = gate_de_permissao(papel_usuario, "COMPUTER")
    _quer_ouvir = False
    if AUDIO_PC_HABILITADO:
        from Arcana.Tools.ouvinte_pc import requer_escuta_pc
        _quer_ouvir = requer_escuta_pc(texto)
    if not _pode_ouvir and _quer_ouvir:
        print(f" [SEGURANÇA] {usuario_nome} pediu para ouvir o PC e foi recusado: {_motivo_ouvir}")
        _sem_permissao.add("ouvir_o_pc")
    if AUDIO_PC_HABILITADO and _pode_ouvir and _quer_ouvir:
        print(" [SISTEMA] Pergunta sobre o áudio do PC! A escutar...")
        try:
            o_que_se_ouviu = await ouvir_pc_e_descrever()
            print(f" [OUVIDO] {o_que_se_ouviu}")
            if not o_que_se_ouviu.startswith("["):
                historico_api[-1]["content"] += (
                    "\n\n[SISTEMA: Ouvi agora o áudio do teu PC e transcrevi: "
                    f"'{o_que_se_ouviu}'. Responde a partir disto, sem inventar "
                    "o resto. Se for musica, diz honestamente que parece musica "
                    "e nao consegues ler a letra com certeza.]"
                )
        except Exception as e:
            print(f" Erro ao ouvir o áudio do PC: {e}")

    # Se sobrou alguma recusa, diz-se agora, antes de gastar o pedido: assim
    # a IA responde a uma coisa so, em vez de se truncar a meio.
    if _sem_permissao:
        historico_api.append({
            "role": "user",
            "content": (
                "[SISTEMA DE SEGURANÇA: NÃO FAÇAS ISTO] Este pedido foi-recusado "
                "por falta de permissão: " + "; ".join(sorted(_sem_permissao)) + ". "
                "Diz isso ao utilizador numa frase curta e natural, com a tua "
                "personalidade. Não cites 'sistema', 'tags' nem 'permissão' como "
                "se fosses um programa, e não o faças repetir."
            ),
        })

    # 🧠 LÓGICA DO CÉREBRO PRINCIPAL
    _, _, _, _, _, modelos_config, *_ = carregar_brain()
    provedor_local = modelos_config.get("local", "nvidia")
    
    if provedor_local == "nvidia":
        cliente_ativo = client_nvidia
        # O id do modelo NVIDIA nunca foi guardado no código, por isso lê-se do cérebro.
        # Não é adivinhado: se faltar, avisa em vez de rebentar com NameError.
        id_modelo = modelos_config.get("nvidia_modelo")
        if not id_modelo:
            print(" ERRO: provedor 'nvidia' ativo, mas 'nvidia_modelo' não está definido no brain.json.")
            print(" Adiciona  \"nvidia_modelo\": \"<id-do-modelo>\"  dentro de modelos_ativos, ou volta para Groq.")
            return "O meu cérebro está mal configurado, diz ao dono para ver o console."
        extra = {"chat_template_kwargs": {"thinking": False}}
    else:
        cliente_ativo = client_llm
        id_modelo = MODELO_LLM
        extra = None

    try:
        kwargs_initial = {
            "model": id_modelo,
            "messages": historico_api,
            "temperature": 0.7
        }
        if extra: kwargs_initial["extra_body"] = extra

        res = await chamada_com_tentativas(
            lambda: cliente_ativo.chat.completions.create(**kwargs_initial),
            o_que="primeira resposta")
        if res is None:
            resposta_final = "Estou a levar com o limite de pedidos da API. Tenta daqui a bocado."
            if not do_discord:
                print(f" {nome_ai}: {resposta_final}")
                await microsoft_speak(resposta_final)
            return resposta_final
        resposta_inicial = res.choices[0].message.content
        resposta_inicial = re.sub(r'<think>.*?</think>', '', resposta_inicial, flags=re.IGNORECASE | re.DOTALL).strip()
        
        resposta_final = resposta_inicial
        precisa_nova_resposta = False

        # 🔥 1. INTERCEPTADOR E LIMPEZA DE MÚSICA LOCAL
        match_musica = re.search(r'<(PLAY:[^>]+|SKIP|PAUSE|STOP|RESUME)[^>]*>', resposta_inicial, re.IGNORECASE)
        if match_musica:
            tag_musica = match_musica.group(1).upper()
            tag_completa = match_musica.group(0)

            resposta_inicial = resposta_inicial.replace(tag_completa, "").strip()
            resposta_final = resposta_inicial

            # Pedir música é permitido a toda a gente; o resto da máquina
            # não. Por isso esta tag quase nunca é recusada.
            _pode, _motivo = gate_de_permissao(papel_usuario, tag_musica.split(':')[0])
            if not _pode:
                print(f" [SEGURANÇA] Música recusada para {usuario_nome}: {_motivo}")
                _sem_permissao.add("pedir música")
            else:
                try:
                    if os.path.exists(BRAIN_FILE):
                        with open(BRAIN_FILE, "r+", encoding="utf-8") as f:
                            brain_data = json.load(f)
                            brain_data["pending_music"] = f"<{tag_musica}>"
                            f.seek(0)
                            json.dump(brain_data, f, indent=4, ensure_ascii=False)
                            f.truncate()
                    print(f"🎵 [SISTEMA] Comando de música enviado ao Discord: <{tag_musica}>")
                except Exception as e:
                    print(f"❌ Erro ao enviar comando remoto para o Discord: {e}")

        # 🔥 2. VERIFICAÇÃO DE AÇÕES (APP E PESQUISA)
        _pode_app, _motivo_app = gate_de_permissao(papel_usuario, "APP")
        if "<APP:" in resposta_inicial and not _pode_app:
            print(f" [SEGURANÇA] <APP:> recusado para {usuario_nome}: {_motivo_app}")
            resposta_inicial = re.sub(r'<APP:[^>]*>', '', resposta_inicial).strip()
            _sem_permissao.add("abrir ou fechar programas no computador")
        elif "<APP:" in resposta_inicial:
            resultado_app = launcher.process_llm_tag(resposta_inicial)
            if resultado_app:
                historico_api.append({"role": "assistant", "content": resposta_inicial})
                historico_api.append({"role": "user", "content": f"[SISTEMA DE AUTOMAÇÃO]: {resultado_app}"})
                precisa_nova_resposta = True

        if "PESQUISAR:" in resposta_inicial.upper():
            match = re.search(r"[\[<]PESQUISAR:\s*(.*?)[\]>]", resposta_inicial, re.IGNORECASE)
            if match:
                termo = match.group(1).strip()
                print(f" [SISTEMA] IA ativou busca autônoma para: '{termo}'")
                
                resultados_web = search_ddg.search_ddg(termo)
                await gerenciar_memoria_pesquisa(client_llm, termo, resultados_web)
                
                if not precisa_nova_resposta:
                    msg_limpa = re.sub(r"[\[<]PESQUISAR:.*?[\]>]", "", resposta_inicial, flags=re.IGNORECASE).strip()
                    if msg_limpa:
                        historico_api.append({"role": "assistant", "content": msg_limpa})
                
                historico_api.append({"role": "user", "content": f"[SISTEMA DE BUSCA]: Resultados encontrados para '{termo}':\n{resultados_web}"})
                precisa_nova_resposta = True

        # 🔧 NOVAS FERRAMENTAS: Processar comandos de controle do PC
        # Este é o bloco mais perigoso do programa: mexer no rato, escrever
        # com o teclado, abrir e fechar coisas. Por isso está fechado a quem
        # não tem o papel de dono/admin.
        _pode_pc, _motivo_pc = gate_de_permissao(papel_usuario, "COMPUTER")
        if "<COMPUTER:" in resposta_inicial and not _pode_pc:
            print(f" [SEGURANÇA] <COMPUTER:> recusado para {usuario_nome}: {_motivo_pc}")
            resposta_inicial = re.sub(r'<COMPUTER:[^>]*>', '', resposta_inicial).strip()
            _sem_permissao.add("controlar o computador")

        # Uma acao perigosa fica à espera de um "sim" em vez de executar.
        # VARREM-SE TODAS as tags, não só a primeira: uma resposta com duas
        # tags era_half perigosa e _half segura passava a outra sem
        # confirmação. E <APP:> também conta, porque abrir e fechar
        # programas foi pedido com confirmação.
        _pode_app, _motivo_app = gate_de_permissao(papel_usuario, "APP")
        if "<APP:" in resposta_inicial and not _pode_app:
            print(f" [SEGURANÇA] <APP:> recusado para {usuario_nome}: {_motivo_app}")
            resposta_inicial = re.sub(r'<APP:[^>]*>', '', resposta_inicial).strip()
            _sem_permissao.add("abrir e fechar programas")

        if _confirmada and _confirmada != "CANCELADO":
            resposta_inicial = f"{resposta_inicial}\n{_confirmada}".strip()
        elif PERMISSOES is not None and _pode_pc and _pode_app:
            _perigosas = []
            for _tag in re.findall(r'<COMPUTER:\s*[\w:,\-]+>', resposta_inicial,
                                   re.IGNORECASE):
                _acao = _tag.split(":", 1)[1].rstrip(">").strip()
                if PERMISSOES.precisa_confirmacao(_acao, papel_usuario):
                    _perigosas.append(_tag)
            # Abrir ou fechar um programa tambem pede confirmacao.
            for _tag in re.findall(r'<APP:\s*[\w:,\-]+>', resposta_inicial,
                                   re.IGNORECASE):
                _acao = _tag.split(":", 1)[1].rstrip(">").strip()
                if PERMISSOES.precisa_confirmacao(_acao, papel_usuario):
                    _perigosas.append(_tag)
            if _perigosas:
                PENDENTE_PC[_chave_pessoa(usuario_nome)] = {"tags": _perigosas}
                print(f" [SEGURANÇA] AÇÃO PERIGOSA à espera de confirmação "
                      f"para {usuario_nome}: {' | '.join(_perigosas)}")
                for _tag in _perigosas:
                    resposta_inicial = resposta_inicial.replace(_tag, "").strip()
                historico_api.append({
                    "role": "user",
                    "content": (
                        f"[SISTEMA DE SEGURANÇA: NÃO EXECUTES] '{_perigosas[0]}' "
                        f"é uma acao perigosa e o comando NÃO foi executado. "
                        f"Pergunta ao utilizador, em UMA frase curta e natural, "
                        f"se tem mesmo a certeza de que queres fazer isso. Só "
                        f"quando ele disser 'sim' é que fazes."
                    ),
                })

        if _pode_pc and "<COMPUTER:" in resposta_inicial:
            # Process computer control commands
            computer_match = re.search(r'<COMPUTER:\s*(\w+)(?::\s*([^>]*))?>', resposta_inicial, re.IGNORECASE)
            if computer_match:
                action = computer_match.group(1).lower()
                param = computer_match.group(2).strip() if computer_match.group(2) else None
                
                if action == "mover_mouse" and param:
                    try:
                        parts = param.split(',')
                        x, y = int(parts[0]), int(parts[1]) if len(parts) > 1 else (0, 0)
                        TOOLS_SYSTEM.move_mouse(x, y)
                        historico_api.append({"role": "user", "content": f"[SISTEMA] Mouse movido para ({x}, {y})"})
                    except:
                        pass
                elif action == "clicar" and param:
                    try:
                        parts = param.split(',')
                        button = parts[0] if parts else "left"
                        clicks = int(parts[1]) if len(parts) > 1 else 1
                        TOOLS_SYSTEM.click(button=button, clicks=clicks)
                        historico_api.append({"role": "user", "content": f"[SISTEMA] Clique {button} ({clicks}x) executado"})
                    except:
                        pass
                elif action == "digitar" and param:
                    TOOLS_SYSTEM.type_text(param)
                    historico_api.append({"role": "user", "content": f"[SISTEMA] Texto digitado: '{param[:30]}...'"})
                elif action == "atalho" and param:
                    keys = param.split('+')
                    TOOLS_SYSTEM.hotkey(*keys)
                    historico_api.append({"role": "user", "content": f"[SISTEMA] Atalho '{'+'.join(keys)}' executado"})
                elif action == "pressionar" and param:
                    TOOLS_SYSTEM.press_key(param)
                    historico_api.append({"role": "user", "content": f"[SISTEMA] Tecla '{param}' pressionada"})
                elif action == "capturar_tela":
                    img = TOOLS_SYSTEM.capture_screen()
                    if img:
                        historico_api.append({"role": "user", "content": "[SISTEMA] Screenshot capturado"})
                elif action == "analisar_tela" and param:
                    analysis = TOOLS_SYSTEM.analyze_screen(param)
                    if analysis:
                        historico_api.append({"role": "user", "content": f"[SISTEMA] Análise: {analysis[:200]}..."})
                elif action == "listar_arquivos" and param:
                    files = TOOLS_SYSTEM.search_files(param)
                    if files:
                        file_list = '\n'.join([os.path.basename(f) for f in files[:10]])
                        historico_api.append({"role": "user", "content": f"[SISTEMA] Arquivos encontrados:\n{file_list}"})
                elif action == "abrir_pasta" and param:
                    TOOLS_SYSTEM.list_directory(param)
                    historico_api.append({"role": "user", "content": f"[SISTEMA] Listando pasta '{param}'"})
                elif action == "nova_tarefa" and param:
                    TOOLS_SYSTEM.start_task(param)
                    historico_api.append({"role": "user", "content": f"[SISTEMA] Tarefa '{param}' iniciada"})
                elif action == "status_tarefa":
                    status = TOOLS_SYSTEM.get_task_status()
                    if status:
                        historico_api.append({"role": "user", "content": f"[SISTEMA] Tarefa: {status.get('task', 'N/A')}, Progresso: {status.get('progress', '0')}%"})

        # 🎨 PHOTOSHOP
        _pode_ps, _motivo_ps = gate_de_permissao(papel_usuario, "PS")
        if TOOLS_SYSTEM and "<PS:" in resposta_inicial and not _pode_ps:
            print(f" [SEGURANÇA] <PS:> recusado para {usuario_nome}: {_motivo_ps}")
            resposta_inicial = re.sub(r'<PS:[^>]*>', '', resposta_inicial).strip()
            _sem_permissao.add("mexer no Photoshop")
        if TOOLS_SYSTEM and _pode_ps and "<PS:" in resposta_inicial:
            ps_match = re.search(r'<PS:\s*(\w+)(?::\s*([^>]*))?>', resposta_inicial, re.IGNORECASE)
            if ps_match:
                acao = ps_match.group(1).lower()
                param = ps_match.group(2).strip() if ps_match.group(2) else None
                ps = TOOLS_SYSTEM.photoshop
                try:
                    if acao == "abrir":
                        ps.abrir()
                        historico_api.append({"role": "user", "content": "[SISTEMA PS] Photoshop aberto."})
                    elif acao == "documento":
                        p = (param or "1920,1080").split(',')
                        largura = int(p[0]); altura = int(p[1]) if len(p) > 1 else 1080
                        res = int(p[2]) if len(p) > 2 else 72
                        ps.criar_documento(largura, altura, res)
                        historico_api.append({"role": "user", "content": f"[SISTEMA PS] Documento {largura}x{altura} criado."})
                    elif acao == "layer":
                        ok_ps = ps.criar_layer(param or "Layer")
                        historico_api.append({"role": "user", "content": f"[SISTEMA PS] Layer '{param}' criada." if ok_ps else "[SISTEMA PS] NÃO foi possível criar a layer."})
                    elif acao == "camada":
                        ok_ps = ps.selecionar_layer(param or "")
                        historico_api.append({"role": "user", "content": f"[SISTEMA PS] Layer ativa agora é '{param}'." if ok_ps else f"[SISTEMA PS] Layer '{param}' não encontrada."})
                    elif acao == "forma":
                        p = (param or "retangulo,0,0,400,300").split(',')
                        tipo = p[0]
                        x = int(p[1]) if len(p) > 1 else 0
                        y = int(p[2]) if len(p) > 2 else 0
                        l = int(p[3]) if len(p) > 3 else 400
                        a = int(p[4]) if len(p) > 4 else 300
                        ok_ps = ps.forma(tipo, x, y, l, a)
                        historico_api.append({"role": "user", "content": f"[SISTEMA PS] Forma '{tipo}' desenhada em ({x},{y})." if ok_ps else f"[SISTEMA PS] Forma '{tipo}' não foi desenhada."})
                    elif acao == "texto":
                        ok_ps = ps.texto(param or "Texto")
                        historico_api.append({"role": "user", "content": "[SISTEMA PS] Texto adicionado." if ok_ps else "[SISTEMA PS] Texto não adicionado."})
                    elif acao == "cor":
                        ok_ps = ps.definir_cor((param or "FF0000").lstrip('#'))
                        historico_api.append({"role": "user", "content": f"[SISTEMA PS] Cor #{param} definida." if ok_ps else "[SISTEMA PS] Cor inválida."})
                    elif acao == "preencher":
                        ok_ps = ps.preencher()
                        historico_api.append({"role": "user", "content": "[SISTEMA PS] Preenchimento aplicado." if ok_ps else "[SISTEMA PS] Preenchimento NÃO aplicado (confirma no log do Photoshop o motivo: camada de texto ou sem documento)."})
                    elif acao == "selecionar":
                        ok_ps = ps.selecionar(param or "tudo")
                        historico_api.append({"role": "user", "content": f"[SISTEMA PS] Seleção '{param}' aplicada." if ok_ps else f"[SISTEMA PS] Seleção '{param}' não aplicada."})
                    elif acao == "efeito":
                        ok_ps = ps.efeito(param or "blur")
                        historico_api.append({"role": "user", "content": f"[SISTEMA PS] Efeito '{param}' aplicado." if ok_ps else f"[SISTEMA PS] Efeito '{param}' NÃO aplicado (motivo no log do Photoshop)."})
                    elif acao == "ferramenta":
                        ps.ferramenta(param or "move")
                        historico_api.append({"role": "user", "content": f"[SISTEMA PS] Ferramenta '{param}' selecionada."})
                    elif acao == "desfazer":
                        ps.desfazer()
                        historico_api.append({"role": "user", "content": "[SISTEMA PS] Ação desfeita."})
                    elif acao == "estado":
                        est = ps.estado()
                        historico_api.append({"role": "user", "content": f"[SISTEMA PS] Estado real: {est}"})
                    elif acao == "guardar":
                        partes = (param or "").rsplit('.', 1)
                        formato = partes[1] if len(partes) == 2 else "psd"
                        ok_ps = ps.guardar(param, formato)
                        historico_api.append({"role": "user", "content": f"[SISTEMA PS] Guardado em {param}" if ok_ps else f"[SISTEMA PS] NÃO foi possível guardar em {param}."})
                    elif acao == "exportar":
                        partes = (param or "").rsplit('.', 1)
                        formato = partes[1] if len(partes) == 2 else "jpg"
                        ok_ps = ps.exportar(param, formato)
                        historico_api.append({"role": "user", "content": f"[SISTEMA PS] Exportado para {param}" if ok_ps else f"[SISTEMA PS] NÃO foi possível exportar para {param}."})
                    precisa_nova_resposta = True
                except Exception as e:
                    print(f"[ERRO PS] {e}")

        # 🎵 MUSICA
        _pode_mus, _motivo_mus = gate_de_permissao(papel_usuario, "MUS")
        if TOOLS_SYSTEM and "<MUS:" in resposta_inicial and not _pode_mus:
            print(f" [SEGURANÇA] <MUS:> recusado para {usuario_nome}: {_motivo_mus}")
            resposta_inicial = re.sub(r'<MUS:[^>]*>', '', resposta_inicial).strip()
            _sem_permissao.add("teoria/produção musical")
        if TOOLS_SYSTEM and _pode_mus and "<MUS:" in resposta_inicial:
            mus_match = re.search(r'<MUS:\s*(\w+)(?::\s*([^>]*))?>', resposta_inicial, re.IGNORECASE)
            if mus_match:
                acao = mus_match.group(1).lower()
                param = mus_match.group(2).strip() if mus_match.group(2) else None
                mus = TOOLS_SYSTEM.music
                try:
                    p = (param or "").split(',')
                    if acao == "escala":
                        r = mus.escala(p[0] or "C", p[1] if len(p) > 1 else "menor")
                        historico_api.append({"role": "user", "content": f"[SISTEMA MUS] {r}"})
                    elif acao == "acorde":
                        r = mus.acorde(p[0] or "C", p[1] if len(p) > 1 else "menor")
                        historico_api.append({"role": "user", "content": f"[SISTEMA MUS] {r}"})
                    elif acao == "progressao":
                        r = mus.progressao(p[0] or "C", p[1] if len(p) > 1 else "menor", p[2] if len(p) > 2 else "pop")
                        historico_api.append({"role": "user", "content": f"[SISTEMA MUS] {r}"})
                    elif acao == "estrutura":
                        r = mus.estrutura(p[0] or "pop", int(p[1]) if len(p) > 1 else 120)
                        historico_api.append({"role": "user", "content": f"[SISTEMA MUS] {r}"})
                    elif acao == "mix":
                        r = mus.chain_mix(p[0] if p and p[0] else "voz")
                        historico_api.append({"role": "user", "content": f"[SISTEMA MUS] {r}"})
                    elif acao == "master":
                        r = mus.chain_master(p[0] if p and p[0] else "pop", p[1] if len(p) > 1 else "spotify")
                        historico_api.append({"role": "user", "content": f"[SISTEMA MUS] {r}"})
                    elif acao == "comp":
                        mus.compressor(p[0] if p and p[0] else "voz", int(p[1]) if len(p) > 1 else 3, int(p[2]) if len(p) > 2 else 15)
                        historico_api.append({"role": "user", "content": f"[SISTEMA MUS] Compressor aplicado: {p}"})
                    elif acao == "reverb":
                        r = mus.reverb_delay(p[0] if p and p[0] else "plate")
                        historico_api.append({"role": "user", "content": f"[SISTEMA MUS] {r}"})
                    elif acao == "organizar":
                        r = mus.organizacao(p[0] if p and p[0] else ".")
                        historico_api.append({"role": "user", "content": f"[SISTEMA MUS] {r}"})
                    precisa_nova_resposta = True
                except Exception as e:
                    print(f"[ERRO MUS] {e}")

        # 🎮 JOGOS
        if TOOLS_SYSTEM and "<JOGO:" in resposta_inicial:
            jogo_match = re.search(r'<JOGO:\s*(\w+)(?::\s*([^>]*))?>', resposta_inicial, re.IGNORECASE)
            if jogo_match:
                acao = jogo_match.group(1).lower()
                param = jogo_match.group(2).strip() if jogo_match.group(2) else None
                jogos = TOOLS_SYSTEM.games
                try:
                    if acao == "pesquisa":
                        p = (param or "").split(',')
                        nome_jogo = p[0] if p and p[0] else "o jogo"
                        topico = p[1] if len(p) > 1 else "dica"
                        r = jogos.pesquisa(nome_jogo, topico)
                        historico_api.append({"role": "user", "content": f"[SISTEMA JOGO] Resultados sobre {nome_jogo}:\n{r}"})
                    elif acao == "ajuda":
                        r = jogos.ajuda(param or "")
                        historico_api.append({"role": "user", "content": f"[SISTEMA JOGO] Pesquisa: {r}"})
                    elif acao == "correr":
                        a_correr = jogos.jogos_a_correr()
                        lista = ", ".join(a_correr.keys()) if a_correr else "nenhum jogo detetado"
                        historico_api.append({"role": "user", "content": f"[SISTEMA JOGO] Jogos a correr: {lista}"})
                    elif acao == "screenshot":
                        r = jogos.analisar_screenshot(param)
                        if r:
                            historico_api.append({"role": "user", "content": f"[SISTEMA JOGO] Análise do ecrã: {r[:600]}"})
                    precisa_nova_resposta = True
                except Exception as e:
                    print(f"[ERRO JOGO] {e}")

        if _sem_permissao and not precisa_nova_resposta:
            precisa_nova_resposta = True

        if precisa_nova_resposta:
            historico_api.append({"role": "user", "content": "Agora dê a sua resposta definitiva ao usuário incorporando o que aconteceu. REGRA ABSOLUTA: Fale com a sua personalidade de forma fluida. É PROIBIDO FAZER ROLEPLAY DE AÇÕES (NUNCA use asteriscos). NUNCA use a palavra 'pesquisa', não diga que buscou na web, e não mencione tags ou comandos. Aja simplesmente como se você tivesse lembrado dessa informação de cabeça."})
            
            kwargs_final = {
                "model": id_modelo,
                "messages": historico_api,
                "temperature": 0.7
            }
            if extra: kwargs_final["extra_body"] = extra

            res_final = await chamada_com_tentativas(
                lambda: cliente_ativo.chat.completions.create(**kwargs_final),
                o_que="resposta final")
            if res_final is None:
                resposta_final = resposta_inicial or "Feito."
            else:
                resposta_final = res_final.choices[0].message.content
                resposta_final = re.sub(r'<think>.*?</think>', '', resposta_final, flags=re.IGNORECASE | re.DOTALL).strip()

        # 🧹 LIMPEZA BRUTAL FINAL: Remove qualquer outra tag <...> do terminal 
        resposta_final = re.sub(r'<[^>]+>', '', resposta_final).strip()

        # 🔥 NOVO: Se a IA enviar só a tag e a resposta ficar vazia, o próprio LLM gera a frase curta!
        if not resposta_final:
            # A API recusa um pedido sem nenhuma mensagem do utilizador
            # ("No user query found in messages", erro 400), por isso a
            # instrucao vem em system E em user.
            historico_fallback = [{"role": "system", "content": "Você é um assistente que responde com frases curtas, sem tags nem asteriscos."}, {"role": "user", "content": f"Aja como {nome_ai}, usando a sua personalidade sarcástica. Confirma em UMA frase curta (entre 1 a 7 palavras) que acabaste de executar o comando. Não use tags nem asteriscos."}]
            try:
                res_fall = await chamada_com_tentativas(
                    lambda: cliente_ativo.chat.completions.create(
                        model=id_modelo, messages=historico_fallback, temperature=0.9, extra_body=extra
                    ),
                    o_que="confirmacao curta")
                if res_fall is None:
                    resposta_final = "Feito."
                else:
                    resposta_final = res_fall.choices[0].message.content
                    resposta_final = re.sub(r'<think>.*?</think>', '', resposta_final, flags=re.IGNORECASE | re.DOTALL)
                    resposta_final = re.sub(r'<[^>]+>', '', resposta_final).strip()
            except Exception as e:
                print(f" Erro na confirmacao curta: {e}")
                resposta_final = "Feito."

        if not do_discord:
            print(f"{nome_ai}: {resposta_final}")
        await gerenciar_e_salvar_memoria(client_llm, nome_ai, resposta_final)
        # No Discord a voz e' o canal de voz, nao os altifalantes do PC: se
        # tocasse aqui, as duas iam falar uma por cima da outra.
        if not do_discord:
            await microsoft_speak(resposta_final)
        return resposta_final

    except Exception as e:
        if _e_rate_limit(e):
            print(" [LIMITE] A API da Groq recusou por excesso de pedidos. Tenta daqui a bocado.")
            print(f"{nome_ai}: estou a levar com o limite de pedidos da API. Tenta daqui a bocado.")
        else:
            print(f" Erro na API LLM ({provedor_local}): {e}")
            print(f"{nome_ai}: deu-me um erro a falar com a API. Tenta outra vez.")
        return None
#endregion
# ======================================================
# region 🎤 MODOS DE OPERAÇÃO
# ======================================================
async def run_modo_continuo(client_nvidia, client_llm, client_vision, sys_prompt, voice_filter, api_key_whisper, nome_ai, usuario_nome, launcher):
    print("\n" + "="*30)
    print(" MODO VOZ ATIVA (ESCUTA CONTÍNUA)")
    print("F1: Gatilho de Voz | F2: Visão Computacional | HOME: Menu")
    print("="*30)
    
    p = pyaudio.PyAudio()
    stream = p.open(format=pyaudio.paInt16, channels=1, rate=16000, input=True, frames_per_buffer=512)
    frames, is_recording, silence_timer = [], False, 0

    while True:
        if keyboard.is_pressed('home'): break

        data = stream.read(512, exception_on_overflow=False)
        if voice_filter.is_human_voice(data):
            if not is_recording: is_recording = True
            frames.append(data); silence_timer = 0
        elif is_recording:
            silence_timer += 1
            if silence_timer > 35: # Tempo de silêncio para processar
                is_recording = False
                texto = await whisper_transcription(frames, api_key_whisper)
                frames = []
                if texto:
                    # 🔥 LÊ O ESTADO ATUALIZADO DO GATILHO ANTES DE PROCESSAR
                    _, _, _, trigger_ativo, _, _, *_ = carregar_brain()
                    if trigger_ativo:
                        if requer_despertar(texto, nome_ai): 
                            await processar_ia(client_nvidia, client_llm, client_vision, sys_prompt, texto, nome_ai, usuario_nome, launcher, modo_chat=False)
                        else:
                            print(f" [IGNORADO] Áudio captado: '{texto}' (Palavra de despertar não detetada)")
                    else:
                        await processar_ia(client_nvidia, client_llm, client_vision, sys_prompt, texto, nome_ai, usuario_nome, launcher, modo_chat=False)
        await asyncio.sleep(0.01)
    stream.stop_stream(); stream.close(); p.terminate()
    
async def run_escuta_pc(client_nvidia, client_llm, client_vision, sys_prompt, nome_ai, usuario_nome, launcher):
    """🎧 Ouve o audio do PC em TEMPO REAL, sem gravar nada em disco.

    Ela fica sempre a escutar o que o PC reproduz (loopback). Nao ha ficheiros
    nem gravacao: o audio vive num buffer de memoria de 30 s e e' apagado
    assim que deixa de ser preciso.

    IMPORTANTISSIMO (tokens): o loop so' TRANSCREVE quando ha fala de verdade
    a terminar. Como ela apanha um video ou uma musica, o teste e' feito na
    banda da voz e numa janela de 2 s: silencio, musica e pausas nao gastam
    nada. Se o audio nao for voz (ex.: musica), gasta-se UM unico pedido para
    ela dizer 'ouvi musica, mas nao ha voz' e so' a cada 60 s.

    F5  -> ligar/desligar a escuta (tambem pelo botao do menu)
    F6  -> transcrever os ultimos 10 s sem esperar pela fala
    HOME-> voltar ao menu
    """
    from Arcana.Tools.ouvinte_pc import obter_ouvinte
    ouvinte = obter_ouvinte()
    if not ouvinte.a_viver() and not ouvinte.iniciar():
        print(f" [ERRO] Não consegui abrir a escuta do áudio do PC: {ouvinte.erro}")
        return

    print("\n" + "="*30)
    print(" 🎧 ESCUTA DO PC (tempo real)")
    print(f" A escutar: {ouvinte.dispositivo}")
    print(" F5: parar escutar | F6: transcrever 10s | HOME: menu")
    print("="*30)

    ESCUTA_ATIVA = True            # global: o botao do menu tambem mexe nisto
    global MODO_ESCUTA_ATIVA
    MODO_ESCUTA_ATIVA = True

    frames = []                    # audio desta fala (so' em memoria)
    silencio = 0                   # blocos de 100 ms sem voz
    a_falar = False
    tempo_fala = 0.0               # segundos de voz nesta fala
    ultima_transcricao = 0.0

    def manter_ouvinte_vivo():
        """O soundcard pode perder o dispositivo: voltamos a abrir."""
        if not ESCUTA_ATIVA:
            return
        if not ouvinte.a_viver() and not ouvinte._parar.is_set():
            print(" [AUDIO] O dispositivo mudou, a reabrir a escuta...")
            ouvinte.iniciar()

    while True:
        if keyboard.is_pressed('home'):
            return
        if keyboard.is_pressed('f5'):
            if ESCUTA_ATIVA:
                ESCUTA_ATIVA = False
                MODO_ESCUTA_ATIVA = False
                ouvinte.parar()
                print("\n👂 Escuta do PC DESLIGADA (ela parou de escutar)")
            else:
                if ouvinte.iniciar():
                    ESCUTA_ATIVA = True
                    MODO_ESCUTA_ATIVA = True
                    print("\n👂 Escuta do PC LIGADA")
            while keyboard.is_pressed('f5'):
                await asyncio.sleep(0.05)

        if not ESCUTA_ATIVA:
            await asyncio.sleep(0.15)
            manter_ouvinte_vivo()
            continue

        await asyncio.sleep(0.1)
        manter_ouvinte_vivo()

        # ---- F6: transcrever o que ouviu agora, a pedido ----
        if keyboard.is_pressed('f6'):
            while keyboard.is_pressed('f6'):
                await asyncio.sleep(0.05)
            print(" [AUDIO] A transcrever os últimos 10s...")
            o_que = await ouvir_pc_e_descrever(10)
            print(f" 👂 Ouvi: {o_que}")
            await processar_ia(client_nvidia, client_llm, client_vision, sys_prompt,
                               f"[escuta do PC] {o_que}", nome_ai, usuario_nome,
                               launcher, modo_chat=False)
            frames = []
            silencio = 0
            a_falar = False
            continue

# ---- tempo real: apanha o audio que acabou de passar ----
        with ouvinte._lock:
            tem_som = bool(ouvinte._nivel_bruto and ouvinte._nivel_bruto[-1] > 0.008)
            bloco = ouvinte._buffer[-1] if ouvinte._buffer else None
        # so' apanha o audio para transcrever se o modo proativo estiver ligado
        ha_fala = AUDIO_PC_PROATIVO and ouvinte.fala_agora()

        if ha_fala:
            a_falar = True
            silencio = 0
            tempo_fala += 0.1
            if bloco is not None:
                frames.append(bloco)
                if len(frames) > 100:            # ~10 s de fala
                    frames.pop(0)
        elif a_falar:
            # a pessoa calou-se: guarda um bocado e conta o silencio
            if bloco is not None and len(frames) < 105:
                frames.append(bloco)
            silencio += 1
            if silencio >= 15:                   # ~1.5 s de silencio = acabou
                a_falar = False
                # sem fala suficiente nao transcreve: e' ai que nasce a
                # hallucinacao do Whisper (uma palavra de ruido vira frase)
                if tempo_fala < 0.8:
                    frames = []
                    tempo_fala = 0.0
                    continue
                # 10 s entre pedidos: com video a tocar nunca passa de 6
                # transcricoes por minuto, mesmo com fala continua
                if (time.time() - ultima_transcricao) < 10:
                    frames = []
                    tempo_fala = 0.0
                    continue
                ultima_transcricao = time.time()
                wav = ouvinte._wav_de(frames)
                frames = []
                tempo_fala = 0.0
                if wav:
                    texto = (await whisper_transcription([wav], GROQ_API_KEY_LLM) or "").strip()
                    if texto:
                        print(f" 👂 [tempo real] {texto}")
                        await processar_ia(
                            client_nvidia, client_llm, client_vision, sys_prompt,
                            f"[ouveu no PC] {texto}\n"
                            "(esta e' uma transcricao automatica do audio do PC e pode "
                            "estar errada; se nao fizer sentido, diz honestamente que "
                            "nao percebes o que ouviu em vez de inventar)",
                            nome_ai, usuario_nome, launcher, modo_chat=False)
                    elif tem_som and (time.time() - ultima_transcricao) > 60:
                        # so' musica/efeitos: UM pedido para dizer isso, e nao mais
                        ultima_transcricao = time.time()
                        print(" 👂 [tempo real] som sem voz - 1 pedido para descrever")
                        await processar_ia(
                            client_nvidia, client_llm, client_vision, sys_prompt,
                            "[ouveu no PC] há som no áudio do PC, mas não há voz para "
                            "transcrever (provavelmente música ou efeitos).",
                            nome_ai, usuario_nome, launcher, modo_chat=False)

async def run_modo_click(client_nvidia, client_llm, client_vision, sys_prompt, api_key_whisper, nome_ai, usuario_nome, launcher):
    print("\n" + "="*30)
    print(" MODO CLICK-TO-TALK")
    print("R-SHIFT: Clica Grava / Clica Envia")
    print("F3: Gatilho | F2: Visão | HOME: Menu")
    print("="*30)
    
    RATE = 16000
    CHUNK = 1024

    while True:
        try:
            while True:
                if keyboard.is_pressed('home'): return
                if keyboard.is_pressed('right shift'):
                    play_beep("inicio")
                    break
                await asyncio.sleep(0.05)

            while keyboard.is_pressed('right shift'): await asyncio.sleep(0.01)

            p = pyaudio.PyAudio()
            stream = p.open(format=pyaudio.paInt16, channels=1, rate=RATE, input=True, frames_per_buffer=CHUNK)
            frames = []
            
            print(" A gravar... (Clica R-SHIFT para enviar)")
            while True:
                data = stream.read(CHUNK, exception_on_overflow=False)
                frames.append(data)
                
                if keyboard.is_pressed('home'):
                    stream.stop_stream(); stream.close(); p.terminate()
                    return
                if keyboard.is_pressed('right shift'):
                    play_beep("fim")
                    break
                await asyncio.sleep(0.001)
                
            stream.stop_stream(); stream.close(); p.terminate()
            print(" A enviar para a IA...")
            while keyboard.is_pressed('right shift'): await asyncio.sleep(0.01)

            texto = await whisper_transcription(frames, api_key_whisper)
            if texto: 
                # 🔥 LÊ O ESTADO ATUALIZADO DO GATILHO ANTES DE PROCESSAR
                _, _, _, trigger_ativo, _, _, *_ = carregar_brain()
                if trigger_ativo:
                    if nome_ai.lower() in texto.lower(): 
                        await processar_ia(client_nvidia, client_llm, client_vision, sys_prompt, texto, nome_ai, usuario_nome, launcher, modo_chat=False)
                    else:
                        print(f" [IGNORADO] Gatilho ativo, mas o nome '{nome_ai}' não foi mencionado.")
                else:
                    await processar_ia(client_nvidia, client_llm, client_vision, sys_prompt, texto, nome_ai, usuario_nome, launcher, modo_chat=False)

        except Exception as e:
            print(f" Erro no Modo Clique: {e}")
            break
#endregion
# ======================================================
#region 👾 DISCORD
# ======================================================
# O bot vive numa thread com o loop dele e fala com o cerebro através
# deste `responder`. E' o unico fio entre os dois: o Discord diz "a pessoa
# X pediu Y com o papel Z" e o run.py devolve a frase ja limpa de tags.
_RESPONDER_DISCORD = {}


async def _responder_ao_discord(info):
    """Ponte entre o bot do Discord e o cerebro. Devolve a resposta em texto."""
    client_nvidia = _RESPONDER_DISCORD.get("nvidia")
    client_llm = _RESPONDER_DISCORD.get("llm")
    client_vision = _RESPONDER_DISCORD.get("vision")
    if client_llm is None:
        return "O meu cérebro ainda está a arrancar."
    sys_prompt = _RESPONDER_DISCORD.get("sys_prompt")
    nome_ai = _RESPONDER_DISCORD.get("nome_ai", "Haimiya")
    launcher = _RESPONDER_DISCORD.get("launcher")

    return await processar_ia(
        client_nvidia, client_llm, client_vision, sys_prompt,
        info["texto"], nome_ai,
        # Quem escreveu é quem interessa para o histórico E para a
        # confirmação de ações perigosas, por isso vai o nome e não o
        # "utilizador do Discord".
        info["autor"], launcher,
        modo_chat=True,
        papel_usuario=info.get("papel", PAPEL_COMUM),
        origem="discord",
    )


def ligar_discord(client_nvidia, client_llm, client_vision, sys_prompt,
                  nome_ai, launcher):
    """Liga o bot do Discord. Devolve o controlador, ou None se nao deu."""
    global DISCORD_BOT
    if DISCORD_BOT is not None:
        print(" [DISCORD] Já está ligado.")
        return DISCORD_BOT
    if not os.getenv("DISCORD_TOKEN", "").strip():
        print(" ERRO: DISCORD_TOKEN em falta no .env.")
        print(" Cria um bot no Discord Developer Portal e mete o token no .env.")
        return None

    _RESPONDER_DISCORD.update({
        "nvidia": client_nvidia, "llm": client_llm, "vision": client_vision,
        "sys_prompt": sys_prompt, "nome_ai": nome_ai, "launcher": launcher,
    })

    try:
        # Importado aqui e não no topo: sem o discord.py instalado, a voz
        # local, a visão e o PC têm de continuar a funcionar na mesma.
        from Arcana.Net.discord_Rem import iniciar_bot_discord
    except Exception as e:
        print(f" ERRO: o discord.py não está instalado ({e}).")
        print(" Corre:  pip install discord.py")
        return None

    try:
        DISCORD_BOT = iniciar_bot_discord(
            _responder_ao_discord, nome_ai=nome_ai,
            # Chave propria para o Whisper e' opcional: sem ela vai a do
            # LLM, que e' a mesma conta da Groq.
            api_whisper=os.getenv("GROQ_API_KEY_STT") or GROQ_API_KEY_LLM,
            caminho_brain=BRAIN_FILE,
            loop_principal=asyncio.get_running_loop(),
        )
    except Exception as e:
        print(f" ERRO ao ligar o Discord: {e}")
        DISCORD_BOT = None
        return None

    # A IA lê o prompt uma vez no arranque; se o Discord acrescentar
    # pessoas novas, é preciso reler as permissões do brain.json.
    global PERMISSOES
    PERMISSOES = Permissoes(caminho=BRAIN_FILE)
    print("🌐 Discord a ligar... (entra na tua call no Discord com !entrar)")
    return DISCORD_BOT


def desligar_discord():
    global DISCORD_BOT
    if DISCORD_BOT is None:
        print(" [DISCORD] Não está ligado.")
        return
    try:
        DISCORD_BOT.parar()
        print("\n [SISTEMA] Discord DESLIGADO.")
    except Exception as e:
        print(f" Erro ao desligar o Discord: {e}")
    DISCORD_BOT = None


def estado_discord():
    if DISCORD_BOT is None:
        return False, "DESLIGADO"
    return True, DISCORD_BOT.estado()


# ======================================================
#region 🚀 MAIN
# ======================================================
async def main():
    brain_raw, sys_prompt, nome_ai, trigger, discord_active, modelos, vtuber_ativo = carregar_brain()

    print("🎨 Iniciando Painel de Configurações em segundo plano (Pressione F4 para acessar)...")
    gui_thread = threading.Thread(target=RemGUI.iniciar_gui_loop, args=(nome_ai,), daemon=True)
    gui_thread.start()

    # 🔥 REGISTRANDO OS ATALHOS GLOBAIS ABSOLUTOS (AGORA APENAS UMA ÚNICA VEZ!)
    keyboard.add_hotkey('f4', RemGUI.toggle)
    keyboard.on_press_key('f2', toggle_visao)
    keyboard.on_press_key('f3', toggle_gatilho) 

    # 👂 OUVINTE DO PC: fica sempre a escutar o audio que o PC reproduz.
    # Custo zero tokens: so' escreve num buffer rolante de 30 s. A transcricao
    # so' acontece quando perguntas 'o que esta a tocar?'.
    if AUDIO_PC_HABILITADO:
        from Arcana.Tools.ouvinte_pc import obter_ouvinte
        _ouvinte = obter_ouvinte()
        if _ouvinte.iniciar():
            print("👂 Ouvinte do PC LIGADO (só transcreve quando perguntares)")
        else:
            print(f"👂 Ouvinte do PC desligado: {_ouvinte.erro}") 

    NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY")
    GROQ_API_KEY_LLM = os.getenv("GROQ_API_KEY_LLM")
    GROQ_API_KEY_VISION = os.getenv("GROQ_API_KEY_VISION")

    # Groq alimenta o cérebro E a memória, portanto é sempre obrigatória.
    # A VISÃO é a exceção: pode ser local (Ollama), e aí a chave da Groq
    # deixa de ser necessária.
    if not GROQ_API_KEY_LLM:
        print(" ERRO FATAL: GROQ_API_KEY_LLM em falta (cerebro e memoria).")
        print(" Verifica o teu ficheiro .env!")
        return

    if not VISAO_LOCAL and not GROQ_API_KEY_VISION:
        print(" ERRO FATAL: GROQ_API_KEY_VISION em falta e a visao esta em modo 'groq'.")
        print(" Ou poes a chave no .env, ou mudas para VISAO_PROVEDOR=local no .env")
        return

    # Atualiza as variáveis do cérebro caso o usuário tenha salvo algo no painel
    brain_raw, sys_prompt, nome_ai, trigger, discord_active, modelos, vtuber_ativo = carregar_brain()

    # A NVIDIA só é necessária se for o provedor ATIVO. Podes deixá-la vazia no .env.
    if modelos.get("local") == "nvidia" and not NVIDIA_API_KEY:
        print(" AVISO: o cérebro está configurado para 'nvidia' mas não há NVIDIA_API_KEY no .env.")
        print(" A mudar para Groq...")
        modelos["local"] = "groq"
        if isinstance(brain_raw.get("modelos_ativos"), dict):
            brain_raw["modelos_ativos"]["local"] = "groq"

    # 🔥 CHAMA O SCRIPT DO VTUBER SE ESTIVER ATIVADO
    if vtuber_ativo:
        print("🎭 Iniciando módulo VTuber Overlay em segundo plano...")
        try:
            subprocess.Popen([sys.executable, "Arcana/Net/vtuber_overlay.py"])
        except Exception as e:
            print(f"❌ Erro ao iniciar o VTuber Overlay: {e}")

    # 🧠 TRÊS CLIENTES SEPARADOS (A puxar do .env)
    # A NVIDIA só é construída se houver chave; sem ela, client_nvidia fica None
    # e nunca é usada porque o provedor ativo já foi mudado para Groq acima.
    client_nvidia = None
    if NVIDIA_API_KEY:
        client_nvidia = OpenAI(api_key=NVIDIA_API_KEY, base_url="https://integrate.api.nvidia.com/v1")
    client_llm = Groq(api_key=GROQ_API_KEY_LLM)

    # 👁️ Visão: Groq na cloud, ou um modelo local servido pelo Ollama /
    # LM Studio. O endpoint local é o mesmo formato aberto da OpenAI.
    if VISAO_LOCAL:
        client_vision = OpenAI(
            api_key=os.getenv("VISAO_API_KEY", "ollama"),  # o Ollama ignora a chave
            base_url=VISAO_BASE_URL,
            timeout=180.0,   # modelo local em CPU e lento: dá mais tempo
        )
        print(f" 👁️  Visao LOCAL: '{MODELO_VISAO}' em {VISAO_BASE_URL}")
    else:
        client_vision = Groq(api_key=GROQ_API_KEY_VISION)
        print(f" 👁️  Visao GROQ: '{MODELO_VISAO}'")
    
    voice_filter = LocalVoiceFilter()
    
    # Puxando o nome do Usuário dinamicamente
    relacionamentos_main = brain_raw.get('relationships', {})
    usuario_nome = list(relacionamentos_main.keys())[0] if relacionamentos_main else "Usuário"
    
    # 🔥 INICIA O MÓDULO DE AUTOMAÇÃO INVISÍVEL
    launcher = AppLauncher()

    # 🔥 INICIA O SISTEMA DE FERRAMENTAS
    global TOOLS_SYSTEM
    TOOLS_SYSTEM = ToolsSystem(output_callback=print, vision_client=client_vision,
                               vision_model=MODELO_VISAO, vision_local=VISAO_LOCAL)

    carregar_memoria()
    
    # [O ERRO ESTAVA AQUI: Existia um keyboard.on_press_key('f2', toggle_visao) fantasma! Removido.]

    # 👾 DISCORD: liga se o cérebro disser que sim. O `discord_active` no
    # brain.json é o botão do painel (F4); o token é o que diz se é
    # possível. Sem token, avisa e segue na mesma — a voz local não pode
    # depender do Discord estar configurado.
    global PERMISSOES
    PERMISSOES = Permissoes(caminho=BRAIN_FILE)
    print(f"🔒 Permissões: comum = {PERMISSOES.resumo_papel(PAPEL_COMUM)}")
    print(f"🔒 Permissões: {len(PERMISSOES.ids_de('dono_ids'))} dono(s), "
          f"{len(PERMISSOES.ids_de('admin_ids'))} admin(s) na lista.")

    if discord_active:
        print("\n🌐 Despertando a Rem no Discord...")
        ligar_discord(client_nvidia, client_llm, client_vision, sys_prompt,
                      nome_ai, launcher)
    else:
        print("🌐 Discord desligado. Liga com a opção 4 do menu, ou pelo painel (F4).")

    while True:
        _, _, _, trigger, discord_active, modelos, _ = carregar_brain()
        _ligado, _estado = estado_discord()
        print(f"\n{'='*15} MENU {nome_ai} {'='*15}")
        print(f"Gatilho F3: {'LIGADO' if trigger else 'DESLIGADO'}")
        print(f"Visão F2: {'LIGADA' if VISAO_HABILITADA else 'DESLIGADA'}")
        if AUDIO_PC_HABILITADO:
            from Arcana.Tools.ouvinte_pc import obter_ouvinte
            _est = obter_ouvinte().estado()
            print(f"Ouvinte PC: {'a escutar' if _est['vivo'] else 'inativo'} "
                  f"({_est['dispositivo'] or 'sem dispositivo'}"
                  f"{', há som' if _est['tem_som'] else ''})")
        print(f"Discord: {_estado}")
        print(f"Utilizador atual: {usuario_nome}")
        print("| 1. Chat")
        print("| 2. Voz Contínua")
        print("| 3. Click-to-Talk")
        print("| 4. Ligar/Desligar Discord")
        print("| 5.  Painel Gráfico (Mudar Cérebro Nvidia/Groq)")
        print("| 6.  👂 Escutar o Áudio do PC (tempo real)")
        print("| 7.  Parar de Escutar")
        print("| 0. Sair")

        op = await asyncio.to_thread(input, "Opção: ")
        if op == '1':
            while True:
                msg = await asyncio.to_thread(input, "Você: ")
                if msg == '0': break
                await processar_ia(client_nvidia, client_llm, client_vision, sys_prompt, msg, nome_ai, usuario_nome, launcher, modo_chat=True)
        elif op == '2': await run_modo_continuo(client_nvidia, client_llm, client_vision, sys_prompt, voice_filter, GROQ_API_KEY_LLM, nome_ai, usuario_nome, launcher)
        elif op == '3': await run_modo_click(client_nvidia, client_llm, client_vision, sys_prompt, GROQ_API_KEY_LLM, nome_ai, usuario_nome, launcher)
        elif op == '4':
            _ligado, _ = estado_discord()
            if _ligado:
                desligar_discord()
            else:
                ligar_discord(client_nvidia, client_llm, client_vision, sys_prompt,
                              nome_ai, launcher)
            # O estado guardado é o do PAINEL. O que estiver ligado a sério
            # manda no que fica gravado, senão o menu e a verdade
            # divergem e a opção 4 volta a ligar o que se desligou à mão.
            discord_active = estado_discord()[0]
            salvar_discord_brain(discord_active)
            print(f" [SISTEMA] Discord gravado como {'LIGADO' if discord_active else 'DESLIGADO'}.")
            if discord_active:
                print(" No Discord usa: !entrar  (entra na tua call)  |entrar")
        elif op == '5':
            await asyncio.to_thread(abrir_gui_modelos)
        elif op == '6':
            await run_escuta_pc(client_nvidia, client_llm, client_vision, sys_prompt,
                                nome_ai, usuario_nome, launcher)
        elif op == '7':
            from Arcana.Tools.ouvinte_pc import obter_ouvinte
            global MODO_ESCUTA_ATIVA
            obter_ouvinte().parar()
            MODO_ESCUTA_ATIVA = False
            print("\n👂 Escuta do PC DESLIGADA (ela parou de escutar)")
        
        elif op == '0':
            desligar_discord()
            break
if __name__ == "__main__":
    asyncio.run(main())
#endregion
# ============//======================//================