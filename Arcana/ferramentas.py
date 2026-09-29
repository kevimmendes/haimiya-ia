"""Function calling nativo para as acoes com efeito no sistema.

O dispatch por tags de texto (`<COMPUTER:digitar:...>`) tem dois problemas:
o modelo tem de acertar a sintaxe numa frase, e uma tag pode aparecer
dentro de uma citacao sem que o tenha querendo dizer. Com tool calling a
decisao e um campo estruturado, e o resultado volta num `role: "tool"` que
o modelo nao pode confundir com fala do utilizador.

So entram aqui as acoes que mexem em alguma coisa. As ferramentas de
consulta (teoria musical, guas de jogos) continuam no prompt por tag:
sao texto de consulta, nao side effects, e o modelo trata-as melhor em
linguagem natural do que em JSON.

O `seguranca.envolver` continua a ser aplicado ao que a ferramenta devolve
da web, do ecra e do disco. O `role: "tool"` ja separa a origem, mas
defesa em herec e barata aqui.
"""

import os
from Arcana import seguranca


def _coordenadas(args):
    """Aceita x/y separados ou um par [x, y] e devolve (x, y) ints."""
    x = args.get("x")
    y = args.get("y")
    if isinstance(x, (list, tuple)):
        par = list(x) + [0, 0]
        x, y = par[0], par[1]
    return _int(x), _int(y)


def _int(valor, omissao=0):
    if valor is None or valor == "":
        return omissao
    try:
        return int(float(str(valor).strip()))
    except (TypeError, ValueError):
        return omissao


def construir_definicoes(platform, launcher=None, tem_photoshop=False):
    """Devolve o array `tools` para a API, conforme as capacidades."""
    tools = []

    def add(nome, descricao, props, obrigatorias=None):
        tools.append({
            "type": "function",
            "function": {
                "name": nome,
                "description": descricao,
                "parameters": {
                    "type": "object",
                    "properties": props,
                    "required": obrigatorias or [],
                },
            },
        })

    add("abrir_app", "Abre uma aplicação instalada no computador, por nome.",
        {"nome": {"type": "string", "description": "Nome da aplicação, ex: 'terminal', 'navegador', 'calculadora'."}},
        ["nome"])

    add("pesquisar_web", "Pesquisa na internet e devolve resultados. Usa quando o utilizador pede noticias, dados atuais ou um facto que nao sabes.",
        {"termo": {"type": "string", "description": "O que pesquisar."}},
        ["termo"])

    add("controlar_mouse", "Move o cursor ou clica no ecra. Coordenadas em pxeis, comecando em 0,0 no canto superior esquerdo.",
        {
            "accoes": {
                "type": "string",
                "enum": ["mover", "clicar", "clicar_direito", "duplo_clique"],
                "description": "O que fazer com o cursor.",
            },
            "x": {"type": "integer", "description": "Posicao horizontal."},
            "y": {"type": "integer", "description": "Posicao vertical."},
        },
        ["accoes", "x", "y"])

    add("digitar_texto", "Escreve texto no programa que estiver em foco. Confirma antes com o utilizador se o texto for longo ou envolver dinheiro.",
        {"texto": {"type": "string", "description": "Texto a escrever, sem caracteres de controlo."}},
        ["texto"])

    add("pressionar_tecla", "Carrega uma tecla ou um atalho de teclado. Ex: 'enter', 'esc', 'ctrl+c'.",
        {"teclas": {"type": "string", "description": "Tecla ou atalho separado por '+'."}},
        ["teclas"])

    add("analisar_ecra", "Tira uma foto do ecra e analisa-a com visao. Usa quando o utilizador diz 'olha para o ecra', 'o que vês', 'o que esta escrito'.",
        {"pergunta": {"type": "string", "description": "O que queres que vejas no ecra."}},
        ["pergunta"])

    add("listar_ficheiros", "Procura ficheiros no computador por nome. Devolve so nomes, nunca conteudo.",
        {"termo": {"type": "string", "description": "Texto a procurar no nome do ficheiro."}},
        ["termo"])

    add("criar_tarefa", "Cria um plano em etapas para um trabalho com varios passos. So para trabalho que realmente tenha fases.",
        {"nome": {"type": "string", "description": "Nome curto da tarefa."}},
        ["nome"])

    add("estado_tarefa", "Mostra o progresso da tarefa em curso.", {})

    add("tocar_musica", "Manda o player de musica tocar, saltar, pausar, parar ou retomar. Exige que o utilizador tenha pedido.",
        {
            "accoes": {
                "type": "string",
                "enum": ["tocar", "saltar", "pausar", "parar", "retomar"],
                "description": "O que fazer no player.",
            },
            "nome": {"type": "string", "description": "Nome da musica, so para 'tocar'."},
        },
        ["accoes"])

    if tem_photoshop:
        add("photoshop", "Controla o Photoshop: abrir, criar documento, criar/selecionar layer, forma, texto, cor, preencher, selecao, efeito, ferramenta, desfazer, estado, guardar, exportar. Apenas em Windows.",
            {
                "accoes": {
                    "type": "string",
                    "description": "Acao Photoshop (abrir, documento, layer, camada, forma, texto, cor, preencher, selecionar, efeito, ferramenta, desfazer, estado, guardar, exportar).",
                },
                "largura": {"type": "integer"},
                "altura": {"type": "integer"},
                "nome": {"type": "string", "description": "Nome da layer, texto ou ficheiro."},
                "cor": {"type": "string", "description": "Cor em hex, ex: FF0000."},
            },
            ["accoes"])

    return tools


# ---------------------------------------------------------------- execucao

def executar(nome, args, ctx):
    """Corre uma ferramenta. Devolve (resultado_texto, precisa_outra_turno).

    Levanta Exception para o dispatcher registar e devolver erro ao modelo em
    vez de rebentar o ciclo.
    """
    args = args or {}
    tools = ctx.get("tools")
    launcher = ctx.get("launcher")

    if nome == "abrir_app":
        app = (args.get("nome") or "").strip()
        if not app:
            return "Não indicaste o nome da aplicação.", False
        if launcher is None:
            return "O lançador de aplicações não está disponível.", False
        return launcher.abrir_por_nome(app), False

    if nome == "pesquisar_web":
        from Arcana.Net import search_ddg
        termo = (args.get("termo") or "").strip()
        if not termo:
            return "Não indicaste o termo da pesquisa.", False
        bruto = search_ddg.search_ddg(termo)
        if not bruto:
            return "A pesquisa não devolveu resultados.", False
        return seguranca.envolver(bruto, f"resultados web para '{termo}'")[0], False

    if nome == "controlar_mouse":
        accoes = (args.get("accoes") or "mover").lower()
        x, y = _coordenadas(args)
        if accoes == "mover":
            tools.move_mouse(x, y)
            return f"Cursor movido para ({x}, {y}).", False
        if accoes in ("clicar", "clicar_direito", "duplo_clique"):
            button = "right" if accoes == "clicar_direito" else "left"
            clicks = 2 if accoes == "duplo_clique" else 1
            tools.click(button=button, clicks=clicks)
            return f"Clique {button} ({clicks}x) executado.", False
        return f"Acção de rato desconhecida: {accoes}.", False

    if nome == "digitar_texto":
        texto = str(args.get("texto") or "")
        if not texto:
            return "Não há texto para escrever.", False
        tools.type_text(texto)
        return f"Escrevi {len(texto)} caracteres no programa em foco.", False

    if nome == "pressionar_tecla":
        teclas = [t.strip() for t in str(args.get("teclas") or "").split("+") if t.strip()]
        if not teclas:
            return "Não indicaste que tecla carregar.", False
        if len(teclas) == 1:
            tools.press_key(teclas[0])
        else:
            tools.hotkey(*teclas)
        return f"Atalho '{'+'.join(teclas)}' executado.", False

    if nome == "analisar_ecra":
        img = tools.capture_screen()
        if not img:
            from Arcana import platform_shim
            motivos = ", ".join(platform_shim.capturas_disponiveis()) or "sem ecra disponível"
            return f"Não consegui capturar o ecra: {motivos}.", False
        análise = tools.analyze_screen(args.get("pergunta") or "Descreve o ecra.")
        if not análise:
            return "A análise do ecrã não devolveu nada.", False
        return seguranca.envolver(análise, "análise de ecrã")[0], False

    if nome == "listar_ficheiros":
        ficheiros = tools.search_files(args.get("termo") or "")
        if not ficheiros:
            return "Não encontrei ficheiros com esse nome.", False
        lista = "\n".join(os.path.basename(f) for f in ficheiros[:10])
        return seguranca.envolver(lista, "lista de ficheiros")[0], False

    if nome == "criar_tarefa":
        tools.start_task(args.get("nome") or "Tarefa sem nome")
        return f"Tarefa '{args.get('nome')}' iniciada. Vê o progresso com estado_tarefa.", False

    if nome == "estado_tarefa":
        estado = tools.get_task_status()
        if not estado:
            return "Não há tarefa em curso.", False
        return f"Tarefa: {estado.get('task', 'N/A')}. Progresso: {estado.get('progress', '0')}%.", False

    if nome == "tocar_musica":
        accoes = (args.get("accoes") or "").lower()
        mapa = {"tocar": "PLAY", "saltar": "SKIP", "pausar": "PAUSE", "parar": "STOP", "retomar": "RESUME"}
        if accoes not in mapa:
            return f"Acção de música desconhecida: {accoes}.", False
        if accoes == "tocar" and not (args.get("nome") or "").strip():
            return "Para tocar preciso do nome da musica.", False
        return ctx["set_musica"](mapa[accoes], args.get("nome") or ""), False

    if nome == "photoshop":
        return _executar_photoshop(args, tools.photoshop), True

    return f"Ferramenta desconhecida: {nome}.", False


def _executar_photoshop(args, ps):
    """Devolve so a mensagem; o `True` do segundo elemento e do `executar`."""
    accao = (args.get("accoes") or "").lower()
    nome = args.get("nome") or ""
    if accao == "abrir":
        ps.abrir()
        return "Photoshop aberto."
    if accao == "documento":
        largura = args.get("largura") or 1920
        altura = args.get("altura") or 1080
        ps.criar_documento(largura, altura, 72)
        return f"Documento {largura}x{altura} criado."
    if accao == "layer":
        return "Layer criada." if ps.criar_layer(nome or "Layer") else "Não foi possível criar a layer."
    if accao == "camada":
        return f"Layer ativa: {nome}." if ps.selecionar_layer(nome) else f"Layer '{nome}' nao encontrada."
    if accao == "texto":
        return "Texto adicionado." if ps.texto(nome or "Texto") else "Texto nao adicionado."
    if accao == "cor":
        limpo = nome.lstrip("#") or "FF0000"
        return f"Cor #{limpo} definida." if ps.definir_cor(limpo) else "Cor invalida."
    if accao == "preencher":
        ps.preencher()
        return "Preenchimento aplicado."
    if accao == "selecionar":
        return f"Selecao '{nome}' aplicada." if ps.selecionar(nome or "tudo") else f"Selecao '{nome}' nao aplicada."
    if accao == "efeito":
        return f"Efeito '{nome}' aplicado." if ps.efeito(nome or "blur") else f"Efeito '{nome}' NAO aplicado."
    if accao == "ferramenta":
        ps.ferramenta(nome or "move")
        return f"Ferramenta '{nome}' selecionada."
    if accao == "desfazer":
        ps.desfazer()
        return "Acao desfeita."
    if accao == "estado":
        return f"Estado real: {ps.estado()}"
    if accao in ("guardar", "exportar"):
        padrao = "psd" if accao == "guardar" else "jpg"
        bruto = nome.strip() or f"saida.{padrao}"
        base, _, ext = bruto.rpartition(".")
        tem_extensao = bool(base) and len(ext) <= 4
        formato = ext if tem_extensao else padrao
        caminho = bruto if tem_extensao else f"{bruto}.{padrao}"
        if accao == "guardar":
            ok = ps.guardar(caminho, formato)
            return f"Guardado em {caminho}." if ok else f"Não foi possível guardar em {caminho}."
        ok = ps.exportar(caminho, formato)
        return f"Exportado para {caminho}." if ok else f"Não foi possível exportar para {caminho}."
    return f"Acção Photoshop desconhecida: {accao}."
