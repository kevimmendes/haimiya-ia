# ============//======================//================
# 🧰 UTILIDADES NERIVA — funções do dia a dia
# ======================================================
# Módulo novo: NÃO mexe em nada do que já existe no run.py.
# Só HTTP (requests) + stdlib — sem dependências novas.
#
# Todas as funções devolvem texto pronto a mostrar e fazem LOG
# de qualquer erro, em consola e em armazen/utilidades.log.
# ======================================================
import json
import hashlib
import os
import re
import shutil
import subprocess
import time
from datetime import datetime

import requests

TIMEOUT = 12
UA = "Haimiya-IA/1.0 (utilidades neriva)"
LOG_FILE = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "armazen", "utilidades.log"))

_CACHE = {}


def _log(erro, detalhe=""):
    """LOG DE ERRO: consola + ficheiro. Nunca rebenta com a app."""
    linha = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | {erro} | {detalhe}"
    print(f"[UTILIDADES][ERRO] {erro}" + (f" — {detalhe}" if detalhe else ""))
    try:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(linha + "\n")
    except Exception:
        pass  # sem disco não pode ser este módulo que mata a app


def _get_json(url, headers=None, timeout=TIMEOUT):
    """GET com JSON. Em erro faz log e devolve None."""
    try:
        r = requests.get(url, headers={"User-Agent": UA, **(headers or {})}, timeout=timeout)
        if r.status_code != 200:
            _log(f"HTTP {r.status_code} em {url.split('?')[0]}", (r.text or "")[:200])
            return None
        return r.json()
    except Exception as e:
        _log(f"pedido falhou: {url.split('?')[0]}", f"{type(e).__name__}: {e}")
        return None


def _get_texto(url, headers=None, timeout=TIMEOUT):
    try:
        r = requests.get(url, headers={"User-Agent": UA, **(headers or {})}, timeout=timeout)
        if r.status_code != 200:
            _log(f"HTTP {r.status_code} em {url.split('?')[0]}", (r.text or "")[:200])
            return None
        return r.text
    except Exception as e:
        _log(f"pedido falhou: {url.split('?')[0]}", f"{type(e).__name__}: {e}")
        return None


def _digitos(t):
    return re.sub(r"\D", "", t or "")


def _formata_numero(n, casas=2):
    try:
        return f"{n:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return str(n)


# ------------------------------------------------------
# 🇧🇷 BRASIL — CEP, CNPJ, feriados, CPF
# ------------------------------------------------------
def consulta_cep(cep):
    """CEP -> BrasilAPI v2 (rua, bairro, cidade, UF)."""
    c = _digitos(cep)
    if len(c) != 8:
        return "CEP inválido: preciso de 8 dígitos (ex: 01310-100)."
    d = _get_json(f"https://brasilapi.com.br/api/cep/v2/{c}")
    if not d:
        return f"Não consegui consultar o CEP {c} (erro de rede/api — ver log)."
    if d.get("erro") or d.get("errors"):
        return f"A BrasilAPI não conhece o CEP {c}."
    return (f"CEP {c}: {d.get('street', '?')}, {d.get('neighborhood', '?')} — "
            f"{d.get('city', '?')}/{d.get('state', '?')} "
            f"[{d.get('location', {}).get('coordinates', {}).get('latitude', '')}, "
            f"{d.get('location', {}).get('coordinates', {}).get('longitude', '')}]")


def consulta_cnpj(cnpj):
    """CNPJ -> BrasilAPI (razão social, situação, endereço)."""
    c = _digitos(cnpj)
    if len(c) != 14:
        return "CNPJ inválido: preciso de 14 dígitos (ex: 00.000.000/0001-91)."
    d = _get_json(f"https://brasilapi.com.br/api/cnpj/v1/{c}")
    if not d:
        return f"Não consegui consultar o CNPJ {c} (erro de rede/api — ver log)."
    if d.get("erro") or d.get("errors"):
        return f"A BrasilAPI não conhece o CNPJ {c}."
    partes = [
        f"CNPJ {c} — {d.get('razao_social', '?')}",
        f"Fantasia: {d.get('nome_fantasia') or '—'} | Situação: {d.get('descricao_situacao_cadastral') or d.get('situacao', '?')}",
        f"Abertura: {d.get('data_abertura', '?')} | CNAE: {d.get('cnae_fiscal_descricao', '?')}",
        f"Endereço: {d.get('descricao_tipo_de_logradouro', '')} {d.get('logradouro', '?')}, {d.get('numero', 's/n')}, "
        f"{d.get('bairro', '?')} — {d.get('descricao_municipio', '?')}/{d.get('uf', '?')} CEP {_digitos(d.get('cep', ''))}",
    ]
    if d.get("capital_social"):
        partes.append(f"Capital social: R$ {_formata_numero(float(d['capital_social']))}")
    return "\n".join(partes)


def lista_feriados(ano=None):
    """Feriados nacionais do ano -> BrasilAPI."""
    try:
        ano = int(ano) if ano else datetime.now().year
    except ValueError:
        return "Ano inválido (ex: <UTIL:feriados:2026>)."
    if ano < 2000 or ano > 2100:
        return "Ano fora do intervalo aceite (2000-2100)."
    d = _get_json(f"https://brasilapi.com.br/api/feriados/v1/{ano}")
    if d is None:
        return f"Não consegui buscar os feriados de {ano} (erro de rede/api — ver log)."
    if isinstance(d, dict) and (d.get("erro") or d.get("errors")):
        return f"A BrasilAPI não tem feriados para {ano}."
    if not isinstance(d, list) or not d:
        return f"A BrasilAPI devolveu nada para os feriados de {ano}."
    linhas = []
    hoje = datetime.now().date()
    for f in d:
        try:
            dt = datetime.strptime(f.get("date", ""), "%Y-%m-%d").date()
            marca = " (já passou)" if dt < hoje else ""
            linhas.append(f"{dt.strftime('%d/%m')} — {f.get('name', '?')}{marca}")
        except Exception as e:
            _log("feriado com data inválida", f"{f} ({type(e).__name__})")
    return f"Feriados nacionais de {ano} ({len(linhas)}):\n" + "\n".join(linhas)


def valida_cpf(cpf):
    """Valida CPF pelos dígitos verificadores (sem consultar a Receita)."""
    c = _digitos(cpf)
    if len(c) != 11:
        return "CPF inválido: preciso de 11 dígitos."
    if c == c[0] * 11:
        return f"CPF {c} INVÁLIDO (sequência repetida)."
    for dv in (9, 10):
        soma = sum(int(c[i]) * ((dv + 1) - i) for i in range(dv))
        dig = (soma * 10) % 11
        dig = 0 if dig == 10 else dig
        if dig != int(c[dv]):
            return f"CPF {c} INVÁLIDO (dígito verificador não bate)."
    return f"CPF {c} é FORMATAMENTE VÁLIDO (11 dígitos e dígitos verificadores corretos)."


# ------------------------------------------------------
# 🌤️ CLIMA, COTAÇÃO E GEOLOCALIZAÇÃO
# ------------------------------------------------------
_CODIGOS_CLIMA = {
    0: "céu limpo", 1: "predominantemente limpo", 2: "parcialmente nublado", 3: "nublado",
    45: "nevoeiro", 48: "nevoeiro com geada",
    51: "chuva molhada fraca", 53: "chuva molhada", 55: "chuva molhada forte",
    56: "chuva molhada gelada", 57: "chuva molhada gelada forte",
    61: "chuva fraca", 63: "chuva", 65: "chuva forte",
    66: "chuva gelada", 67: "chuva gelada forte",
    71: "neve fraca", 73: "neve", 75: "neve forte", 77: "grãos de neve",
    80: "pancadas de chuva", 81: "pancadas de chuva fortes", 82: "pancadas violentas",
    85: "pancadas de neve", 86: "pancadas de neve fortes",
    95: "trovoada", 96: "trovoada com granizo", 99: "trovoada forte com granizo",
}


def _geocodificar(cidade):
    cidade = (cidade or "").strip()
    if not cidade:
        return None, "Diz-me a cidade (ex: <UTIL:clima:Lisboa>)."
    d = _get_json("https://geocoding-api.open-meteo.com/v1/search"
                  f"?name={requests.utils.quote(cidade)}&count=1&language=pt&format=json")
    if d is None:
        return None, f"Não consegui geocodificar '{cidade}' (erro de rede — ver log)."
    res = d.get("results") or []
    if not res:
        return None, f"Não encontrei a cidade '{cidade}'."
    return res[0], None


def geolocalizar(cidade):
    """Cidade -> coordenadas (Open-Meteo geocoding)."""
    loc, erro = _geocodificar(cidade)
    if erro:
        return erro
    pais = loc.get("country", "?")
    admin = loc.get("admin1", "")
    return (f"{loc.get('name')}{', ' + admin if admin else ''}, {pais} — "
            f"lat {loc.get('latitude')}, lon {loc.get('longitude')}, "
            f"fuso {loc.get('timezone', '?')}, ID {loc.get('id')}")


def clima(cidade):
    """Tempo atual + 3 dias (Open-Meteo, sem chave de API)."""
    loc, erro = _geocodificar(cidade)
    if erro:
        return erro
    lat, lon = loc.get("latitude"), loc.get("longitude")
    url = (f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
           "&current=temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m"
           "&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max"
           "&timezone=auto&forecast_days=3")
    d = _get_json(url)
    if not d:
        return f"Não consegui buscar o tempo para '{cidade}' (erro de rede — ver log)."
    try:
        cur = d["current"]
        dias = d["daily"]
        desc = _CODIGOS_CLIMA.get(cur.get("weather_code"), f"código {cur.get('weather_code')}")
        nome = f"{loc.get('name')}{', ' + loc.get('admin1', '') if loc.get('admin1') else ''}"
        linhas = [
            f"{nome} ({loc.get('country', '?')}) — agora:",
            f"  {_formata_numero(cur['temperature_2m'], 1)}°C "
            f"(sensação {_formata_numero(cur.get('apparent_temperature', cur['temperature_2m']), 1)}°C), "
            f"umidade {cur.get('relative_humidity_2m', '?')}%, "
            f"vento {_formata_numero(cur.get('wind_speed_10m', 0), 0)} km/h — {desc}",
        ]
        for i, dt in enumerate(dias["time"]):
            try:
                data = datetime.strptime(dt, "%Y-%m-%d").date()
                quando = "Hoje" if i == 0 else data.strftime("%a %d/%m")
                linhas.append(
                    f"  {quando}: máx {_formata_numero(dias['temperature_2m_max'][i], 0)}° / "
                    f"mín {_formata_numero(dias['temperature_2m_min'][i], 0)}°, "
                    f"precipitação {dias['precipitation_probability_max'][i] or 0}%")
            except Exception as e:
                _log("dia de previsão com dados incompletos", f"{dt} ({type(e).__name__}: {e})")
        return "\n".join(linhas)
    except Exception as e:
        _log("resposta inesperada do Open-Meteo", f"{type(e).__name__}: {e}")
        return "Recebi o tempo mas em formato que não percebi (ver log)."


_MOEDAS = {
    "dolar": "USD", "dólar": "USD", "usd": "USD",
    "euro": "EUR", "eur": "EUR",
    "bitcoin": "BTC", "btc": "BTC",
    "libra": "GBP", "iene": "JPY", "franco": "CHF",
    "real": "BRL", "brl": "BRL",
}


def cotacao(moeda=None):
    """Cotações vs Real (open.er-api.com, sem chave)."""
    d = _get_json("https://open.er-api.com/v6/latest/USD")
    if not d or d.get("result") != "success":
        return "Não consegui buscar as cotações (erro de rede/api — ver log)."
    rates = d.get("rates", {})
    brl = rates.get("BRL")
    if not brl:
        _log("cotação sem taxa BLR na resposta", str(d)[:200])
        return "A resposta das cotações não veio com BRL (ver log)."
    alvo = None
    if moeda:
        chave = _digitos(moeda) if moeda.isdigit() else moeda.strip().lower()
        alvo = _MOEDAS.get(chave) or (chave.upper() if chave.upper() in ("USD", "EUR", "BTC", "GBP", "JPY", "CHF") else None)
        if not alvo:
            return f"Moeda desconhecida '{moeda}'. Aceito: {', '.join(sorted(set(_MOEDAS)))}."
    codigos = [alvo] if alvo else ["USD", "EUR", "BTC"]
    partes = []
    for cod in codigos:
        taxa = rates.get(cod)
        if not taxa:
            _log(f"sem taxa para {cod}", "")
            continue
        valor = brl if cod == "BRL" else brl / taxa
        nome = {"USD": "Dólar", "EUR": "Euro", "BTC": "Bitcoin", "GBP": "Libra",
                "JPY": "Iene", "CHF": "Franco suíço", "BRL": "Real"}.get(cod, cod)
        partes.append(f"1 {nome} ({cod}) = R$ {_formata_numero(valor, 2 if cod != 'BTC' else 2)}")
    if not partes:
        return "Nenhuma taxa disponível (ver log)."
    quando = d.get("time_last_update_utc", "?")
    return "\n".join(partes) + f"\nFonte: open.er-api.com, atualizado {quando}"


# ------------------------------------------------------
# 🔐 SEGURANÇA — senha vazada (k-Anonymity, sem expor a senha)
# ------------------------------------------------------
def senha_vazada(senha):
    """Have I Been Pwned por RANGE: só manda os 5 primeiros chars do hash SHA-1."""
    s = (senha or "").strip()
    if len(s) < 4:
        return "Senha demasiado curta para verificar."
    digest = hashlib.sha1(s.encode("utf-8")).hexdigest().upper()
    prefixo, sufixo = digest[:5], digest[5:]
    texto = _get_texto(f"https://api.pwnedpasswords.com/range/{prefixo}",
                       headers={"Add-Padding": "true"})
    if texto is None:
        return "Não consegui verificar a senha (erro de rede — ver log). NÃO assumes que é segura."
    for linha in texto.splitlines():
        if ":" not in linha:
            continue
        suf, conta = linha.split(":", 1)
        if suf.strip().upper() == sufixo:
            n = int(conta.strip() or 0)
            if n > 0:
                return (f"⚠️ ESTA SENHA JÁ FOI VAZADA {n} vez(es) em furos de dados conhecidos. "
                        f"Troca-a já (a verificação foi anónima: só os 5 primeiros caracteres do hash saíram daqui).")
            break
    return ("✅ Esta senha não aparece em nenhum vazamento conhecido do HIBP "
            "(verificação anónima por k-Anonymity).")


# ------------------------------------------------------
# ▶️ YOUTUBE — resumo de vídeo
# ------------------------------------------------------
def _id_youtube(url):
    u = (url or "").strip()
    m = re.search(r"(?:youtu\.be/|v=|/shorts/|/embed/|/live/)([\w-]{11})", u)
    return m.group(1) if m else None


def resumo_youtube(url):
    """Título + canal + transcrição/descrição de um vídeo do YouTube."""
    vid = _id_youtube(url)
    if not vid:
        return "Não consegui reconhecer o link do YouTube (ex: <UTIL:youtube:https://youtu.be/XXXXXXXXXXX>)."
    partes = []
    oe = _get_json(f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch%3Fv%3D{vid}&format=json")
    if oe:
        partes.append(f"Título: {oe.get('title', '?')}")
        partes.append(f"Canal: {oe.get('author_name', '?')}")
    else:
        _log("oEmbed do YouTube falhou", vid)

    # Transcrição: só se o pacote opcional estiver instalado (não é dependência obrigatória)
    try:
        from youtube_transcript_api import YouTubeTranscriptApi  # opcional
        try:
            blocos = YouTubeTranscriptApi.get_transcript(vid, languages=["pt", "en", "pt-BR"])
            texto = " ".join(b.get("text", "") for b in blocos)
        except AttributeError:
            blocos = YouTubeTranscriptApi().fetch(vid, languages=["pt", "en", "pt-BR"])
            texto = " ".join(getattr(b, "text", "") for b in blocos)
        if texto:
            partes.append("Transcrição:\n" + texto[:3500] + ("…" if len(texto) > 3500 else ""))
    except Exception as e:
        _log("transcrição do YouTube indisponível", f"{type(e).__name__}: {e}")

    if not partes:
        return f"Não consegui ler o vídeo {vid} (título e transcrição falharam — ver log)."

    # Fallback: descrição embutida na página
    if len(partes) < 3:
        pagina = _get_texto(f"https://www.youtube.com/watch?v={vid}")
        if pagina:
            m = re.search(r'"shortDescription":"(.*?)","', pagina)
            if m:
                try:
                    desc = json.loads('"' + m.group(1) + '"')
                    if desc.strip():
                        partes.append("Descrição:\n" + desc[:1500])
                except Exception as e:
                    _log("descrição do YouTube ilegível", f"{type(e).__name__}: {e}")
    return "\n".join(partes) + f"\n(link: https://youtu.be/{vid})"


# ------------------------------------------------------
# 💾 DISCO — auditoria de ficheiros gigantes/órfãos
# ------------------------------------------------------
_LIXO_EXTS = (".tmp", ".temp", ".dmp", ".bak", ".old", ".orig", ".crdownload",
              ".part", ".download", ".log", ".etl", ".chk")
_SKIP_DIRS = {"windows", "$recycle.bin", "system volume information", ".git",
              "__pycache__", "node_modules", ".venv", "venv"}


def auditoria_disco(raiz=None, limite_segundos=25, top_n=12):
    """Procura ficheiros gigantes e órfãos/temporários. Limitada no tempo."""
    if raiz is None:
        disco = os.path.splitdrive(os.getcwd())[0] or "/"
        raiz = disco + ("\\" if disco.endswith(":") else "")
    if not os.path.isdir(raiz):
        return f"Pasta '{raiz}' não existe."
    try:
        uso = shutil.disk_usage(raiz)
        cabecalho = (f"Disco {raiz} — total {_formata_numero(uso.total / 1e9, 1)} GB, "
                     f"usado {_formata_numero(uso.used / 1e9, 1)} GB, "
                     f"livre {_formata_numero(uso.free / 1e9, 1)} GB "
                     f"({uso.used * 100 // uso.total}%)")
    except Exception as e:
        _log("disk_usage falhou", f"{raiz} ({type(e).__name__}: {e})")
        cabecalho = f"Disco {raiz} — uso desconhecido (ver log)"

    inicio = time.time()
    gigantes, lixo, vistos, total = [], [], 0, 0
    erros = 0
    for pasta, subs, ficheiros in os.walk(raiz, topdown=True, onerror=lambda e: None):
        subs[:] = [s for s in subs if s.lower() not in _SKIP_DIRS]
        for nome in ficheiros:
            vistos += 1
            caminho = os.path.join(pasta, nome)
            try:
                st = os.stat(caminho)
            except Exception:
                erros += 1
                continue
            total += st.st_size
            if st.st_size >= 100 * 1024 * 1024:
                gigantes.append((st.st_size, caminho, st.st_mtime))
            if nome.lower().endswith(_LIXO_EXTS) or nome.endswith("~"):
                lixo.append((st.st_size, caminho))
            if time.time() - inicio > limite_segundos:
                break
        if time.time() - inicio > limite_segundos:
            break

    gigantes.sort(reverse=True)
    lixo.sort(reverse=True)
    saida = [cabecalho,
             f"Percorridos {vistos} ficheiros em {time.time() - inicio:.0f}s "
             f"({_formata_numero(total / 1e9, 2)} GB vistos" + (f", {erros} erros de leitura" if erros else "") + ")"]
    if gigantes:
        saida.append(f"Maiores que 100 MB (top {min(top_n, len(gigantes))}):")
        for sz, cam, _mt in gigantes[:top_n]:
            saida.append(f"  {_formata_numero(sz / 1e6, 0)} MB — {cam}")
    else:
        saida.append("Nenhum ficheiro acima de 100 MB encontrado (varredura parcial por tempo).")
    if lixo:
        saida.append(f"Candidatos a limpar ({len(lixo)}):")
        for sz, cam in lixo[:top_n]:
            saida.append(f"  {_formata_numero(sz / 1e6, 1)} MB — {cam}")
    else:
        saida.append("Nenhum temporário/órfão óbvio encontrado.")
    return "\n".join(saida)


# ------------------------------------------------------
# 🩺 AUTO-DIAGNÓSTICO DO CÓDIGO
# ------------------------------------------------------
def auto_diagnostico(pasta="."):
    """Compila os .py todos, acha erros de sintaxe, TODOs e except cegos."""
    if not os.path.isdir(pasta):
        return f"Pasta '{pasta}' não existe."
    arquivos, erros, todos, cegos, longos = [], [], [], 0, []
    for raiz, subs, ficheiros in os.walk(pasta, topdown=True, onerror=lambda e: None):
        subs[:] = [s for s in subs if s.lower() not in
                   (".git", "__pycache__", ".venv", "venv", "node_modules", "site-packages")]
        for nome in ficheiros:
            if not nome.endswith(".py"):
                continue
            caminho = os.path.join(raiz, nome)
            arquivos.append(caminho)
            try:
                with open(caminho, "r", encoding="utf-8", errors="replace") as f:
                    src = f.read()
            except Exception as e:
                _log("não consegui ler", f"{caminho} ({type(e).__name__}: {e})")
                continue
            try:
                compile(src, caminho, "exec")
            except SyntaxError as e:
                erros.append(f"{caminho}:{e.lineno} — {e.msg}")
            except Exception as e:
                erros.append(f"{caminho} — {type(e).__name__}: {e}")
            n_linhas = src.count("\n") + 1
            if n_linhas > 1200:
                longos.append(f"  {caminho} — {n_linhas} linhas")
            for i, linha in enumerate(src.splitlines(), 1):
                s = linha.strip()
                if re.search(r"except\s*:", linha):
                    cegos += 1
                    if cegos <= 5:
                        todos.append(f"  except cego: {caminho}:{i}")
                elif re.search(r"#\s*(TODO|FIXME|XXX)\b", linha, re.IGNORECASE):
                    if len(todos) < 15:
                        todos.append(f"  {caminho}:{i} — {s[:80]}")
            if len(arquivos) >= 300:
                break
        if len(arquivos) >= 300:
            break

    saida = [f"Diagnóstico de '{os.path.abspath(pasta)}' — {len(arquivos)} ficheiros .py verificados"]
    if erros:
        saida.append(f"ERROS DE SÍNTAXE ({len(erros)}):")
        saida.extend(f"  {e}" for e in erros[:10])
    else:
        saida.append("✅ Sem erros de sintaxe.")
    saida.append(f"except cegos (engolem erros sem log): {cegos}")
    if longos:
        saida.append("Ficheiros muito grandes:")
        saida.extend(longos[:5])
    if todos:
        saida.append("TODO/FIXME e avisos:")
        saida.extend(todos[:15])
    return "\n".join(saida)


# ------------------------------------------------------
# 🎯 CLASSIFICADOR DE INTENÇÃO (técnica / social / ação direta)
# ------------------------------------------------------
_PALAVRAS_ACAO = re.compile(
    r"\b(abre|abrir|fecha|fechar|inicia|iniciar|inicia|corre|correr|executa|executar|instala|instalar|"
    r"desliga|desligar|liga|ligar|reinicia|reiniciar|apaga|apagar|deleta|deletar|move|mover|copia|copiar|"
    r"toca|tocar|manda|mandar|envia|enviar|escreve|escrever|cria|criar|baixa|baixar|pesquisa|pesquisar|"
    r"captura|capturar|clica|clicar|digita|digitar|limpa|limpar|guarda|guardar|abre o|roda|rodar)\b", re.I)
_PALAVRAS_TECNICA = re.compile(
    r"\b(c[óo]digo|código|erro|bug|buga|exception|traceback|log|logs|api|fun[çc][ãa]o|funcao|função|"
    r"script|python|banco de dados|sql|json|git|commit|deploy|servidor|servi[çc]o|config|configura[çc][ãa]o|"
    r"instala[çc][ãa]o|depend[êe]ncia|compila|compilar|debug|deploy|framework|rotina|m[ée]todo|método)\b", re.I)
_PALAVRAS_SOCIAL = re.compile(
    r"\b(oi|ol[áa]|e a[íi]|bom dia|boa tarde|boa noite|obrigad|valeu|kkkk|haha|lol|como (est[áa]|va|tas)|"
    r"tudo bem|tudo bom|beleza|saudade|amor|feliz|triste|cansad)\b", re.I)


def classificar_intencao(texto):
    """Heurística barata (sem gastar tokens): 'ação direta' | 'técnica' | 'social'."""
    t = (texto or "").strip()
    if not t:
        return "social"
    tem_acao = bool(_PALAVRAS_ACAO.search(t))
    tem_tec = bool(_PALAVRAS_TECNICA.search(t))
    tem_social = bool(_PALAVRAS_SOCIAL.search(t)) or len(t.split()) <= 3
    if tem_acao and (tem_tec or "<" in t or "tag" in t.lower()):
        return "ação direta"
    if tem_acao and not tem_social:
        return "ação direta"
    if tem_tec and not (tem_social and not tem_tec):
        return "técnica"
    if tem_acao:
        return "ação direta"
    if tem_social and not tem_tec:
        return "social"
    return "social"


# ------------------------------------------------------
# 🔀 DISPATCH — o run.py chama só isto
# ------------------------------------------------------
_ACOES = {
    "cep": consulta_cep,
    "cnpj": consulta_cnpj,
    "feriados": lista_feriados,
    "cpf": valida_cpf,
    "clima": clima,
    "tempo": clima,
    "cotacao": cotacao,
    "cotação": cotacao,
    "geo": geolocalizar,
    "geolocalizar": geolocalizar,
    "senha": senha_vazada,
    "senha_vazada": senha_vazada,
    "youtube": resumo_youtube,
    "video": resumo_youtube,
    "disco": auditoria_disco,
    "auditoria": auditoria_disco,
    "auditoria_disco": auditoria_disco,
    "diagnostico": auto_diagnostico,
    "diagnóstico": auto_diagnostico,
    "codigo": auto_diagnostico,
}


def executar(acao, param=None):
    """Executa uma ação util. Sempre devolve texto; erro -> log + mensagem."""
    acao = (acao or "").strip().lower()
    if acao in ("", "ajuda", "help"):
        return "Ações disponíveis: " + ", ".join(sorted(set(_ACOES)))
    func = _ACOES.get(acao)
    if not func:
        return f"Ação desconhecida '{acao}'. Ações: {', '.join(sorted(set(_ACOES)))}."
    try:
        return func(param)
    except Exception as e:
        _log(f"ação '{acao}' com parâmetro {param!r}", f"{type(e).__name__}: {e}")
        return f"Falhou a ação '{acao}': {type(e).__name__}: {e} (ver utilidades.log)"
