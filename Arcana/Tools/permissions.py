"""Permissoes: quem pode pedir o que a IA faz.

A Haimiya passa a responder a varias pessoas ao mesmo tempo (call do Discord,
voz local). Nao faz sentido um desconhecido poder abrir programas, mexer nos
ficheiros ou desligar o PC, por isso aqui fica a unica fonte de verdade sobre
quem pode o que:

    comum  -> conversar, pedir musica, gerar imagens, pesquisar, guias de jogos
    admin  -> tudo o que o comum pode + Photoshop, ficheiros e musica
    dono   -> tudo + controlar o PC e interromper a IA a vontade

Regra de desenho importante: o que nao estiver escrito em CAPACIDADES e'
negado. Se amanha' se inventar uma capacidade nova, ela naso fica aberta a
toda a gente so' por esquecimento de a escrever.

O papel de cada pessoa vive em Arcana/armazen/brain.json, dentro de
"permissoes", e pode-se editar a mao ou pelo painel (F4).
"""

import json
import os
import re

PAPEL_COMUM = "comum"
PAPEL_ADMIN = "admin"
PAPEL_DONO = "dono"

PAPEIS = (PAPEL_DONO, PAPEL_ADMIN, PAPEL_COMUM)

# Tudo o que a IA consegue fazer. Serve tambem de lista de capacidades
# reconhecidas: uma capacidade aqui escrita e' segura, o resto e' negado.
TUDO = frozenset({
    "falar",       # conversar, seja por voz, chat ou DM
    "musica",      # pedir musicas (fila do YouTube, Spotify)
    "imagem",      # gerar imagens
    "pesquisa",    # buscar na web
    "jogos",       # guias, builds, analise de ecrã de jogo
    "pc",          # abrir/fechar apps, rato, teclado, janelas, volume
    "ficheiros",   # listar, abrir, renomear, mover ficheiros
    "photoshop",   # controlos do Photoshop
    "musica_teoria",  # escalas, acordes, mix e master
    "forcar",      # interromper a IA enquanto ela fala, limpar a fila
})

CAPACIDADES = {
    PAPEL_DONO: TUDO,
    PAPEL_ADMIN: TUDO,
    PAPEL_COMUM: frozenset({"falar", "musica", "imagem", "pesquisa", "jogos"}),
}

# Qual capacidade cada tag do cerebro exige. A tag e' o nome que vem entre
# < > ou [ ]; o run.py pergunta aqui ANTES de executar seja o que for.
CAPACIDADE_DAS_TAGS = {
    "COMPUTER": "pc",
    "APP": "pc",
    "PS": "photoshop",
    "FICHEIRO": "ficheiros",
    "MUS": "musica_teoria",
    "PLAY": "musica",
    "SKIP": "musica",
    "PAUSE": "musica",
    "STOP": "musica",
    "RESUME": "musica",
    "PESQUISAR": "pesquisa",
    "JOGO": "jogos",
}

# Palavras que tornam uma acao perigosa, mesmo para quem tem a capacidade.
# Nao e' a lista completa do que da para fazer mal: e' o que aparece nas
# ordens que a IA pode receber. Qualquer tag que contenha uma destas palavras
# para na confirmacao.
#
# A comparacao passa por `_normalizar`, que troca underscores e acentos por
# espacos. Por isso "terminar_processo" e "terminar processo" sao a mesma
# palavra - e "desligar a musica" NAO e' perigoso, "desligar o pc" e'.
PALAVRAS_PERIGOSAS = (
    "apagar", "apaga", "eliminar", "elimina", "deletar", "delete",
    "formatar", "format c", "shutdown", "reiniciar", "reboot",
    "desligar o pc", "desligar pc", "desligar a maquina",
    "taskkill", "terminar processo", "matar processo",
    "regedit", "registo", "registro",
    "instalar", "instal", "desinstalar",
    "powershell", "cmd exe", "executar comando",
    "descarregar", "download", "sobrescrever", "alterar ficheiro",
    "porta aberta", "desbloquear", "desbloqueado",
    # Abrir e fechar programas foi pedido com confirmacao: fechar pode
    # perder o que estava por guardar, e abrir lanca o executavel que o
    # Whisper acabou por inventar.
    "abrir app", "abrir programa", "abrir aplicacao", "executar app",
    "fechar app", "fechar programa", "encerrar app", "encerrar programa",
)

# Palavras pelas quais um dono/admin interrompe a IA a falar. Curto de
# proposito: a deteccao e' feita no audio, nao nas tags.
PALAVRAS_INTERRUPTORAS = (
    "silêncio", "silencio", "cala-te", "cala te", "chega", "para",
    "pare", "stop", "cala-te", "basta", "acaba", "silencia",
)

CAMINHO_BRAIN_PADRAO = "Arcana/armazen/brain.json"

_PADRAO = {
    "dono_ids": [],
    "admin_ids": [],
    "admin_papeis": ["Moderação", "Admin", "Administrador", "Dono", "Owner"],
    "exigir_confirmacao": True,
    "capacidades_comum": sorted(CAPACIDADES[PAPEL_COMUM]),
}


def _normalizar(texto):
    """ underscored, hifens epontuacao viram um espaco so."""
    return re.sub(r"[\s_\-]+", " ", str(texto or "").lower()).strip()


class Permissoes:
    """Quem pode pedir o quê. Carrega do brain.json e pode voltar a gravar.

    Exemplo:
        p = Permissoes()
        papel = p.papel_de(user_id, guild)
        ok, motivo = p.pode(papel, "pc")
    """

    def __init__(self, caminho=None, dados=None):
        self.caminho = caminho or CAMINHO_BRAIN_PADRAO
        self.dados = dict(_PADRAO)
        if dados is not None:
            self._fundir(dados)
        else:
            self.carregar()

    # ------------------------------------------------------------------
    # persistencia
    # ------------------------------------------------------------------
    def _fundir(self, dados):
        for chave, valor in _PADRAO.items():
            self.dados[chave] = valor
        if isinstance(dados, dict):
            for chave, valor in dados.items():
                if valor is not None:
                    self.dados[chave] = valor

    def carregar(self):
        try:
            with open(self.caminho, "r", encoding="utf-8") as f:
                bruto = json.load(f)
            self._fundir(bruto.get("permissoes"))
        except Exception:
            pass   # sem ficheiro ou sem chave: fica tudo com o omissao

    def guardar(self):
        """Escreve so' a secao 'permissoes' sem tocar no resto do cerebro."""
        try:
            os.makedirs(os.path.dirname(self.caminho) or ".", exist_ok=True)
            bruto = {}
            if os.path.exists(self.caminho):
                with open(self.caminho, "r", encoding="utf-8") as f:
                    bruto = json.load(f)
            bruto["permissoes"] = self.dados
            with open(self.caminho, "w", encoding="utf-8") as f:
                json.dump(bruto, f, indent=4, ensure_ascii=False)
            return True
        except Exception:
            return False

    # ------------------------------------------------------------------
    # quem e' cada um
    # ------------------------------------------------------------------
    def ids_de(self, chave):
        try:
            return {int(x) for x in (self.dados.get(chave) or [])}
        except (TypeError, ValueError):
            return set()

    def papel_de(self, user_id, guild=None, member=None):
        """Descobre o papel de uma pessoa.

        A ordem importa: dono > admin > comum. O owner do servidor conta
        como dono mesmo que ninguem o tenha escrito na lista, porque e' o
        servidor dele. O mesmo vale para quem tiver a permissao 'Administrador'
        do Discord - e' o owner do servidor a dar essa permissao.
        """
        if user_id is None:
            return PAPEL_COMUM
        try:
            uid = int(user_id)
        except (TypeError, ValueError):
            return PAPEL_COMUM

        if uid in self.ids_de("dono_ids"):
            return PAPEL_DONO

        if member is None and guild is not None:
            try:
                member = guild.get_member(uid)
            except Exception:
                member = None

        if member is not None:
            if getattr(member, "guild_owner", None) is True:
                return PAPEL_DONO
            perms = getattr(member, "guild_permissions", None)
            if perms is not None and getattr(perms, "administrator", False):
                return PAPEL_ADMIN

        if uid in self.ids_de("admin_ids"):
            return PAPEL_ADMIN

        # papais (roles) com os nomes configurados
        nomes = {str(n).lower() for n in (self.dados.get("admin_papeis") or [])}
        if nomes and member is not None:
            for role in getattr(member, "roles", []) or []:
                nome = str(getattr(role, "name", "")).lower()
                if nome in nomes or getattr(role, "managed", False):
                    if nome in nomes:
                        return PAPEL_ADMIN

        return PAPEL_COMUM

    def e_dono(self, user_id):
        return self.papel_de(user_id) == PAPEL_DONO

    # ------------------------------------------------------------------
    # o que cada um pode
    # ------------------------------------------------------------------
    def pode(self, papel, capacidade):
        """(True, '') se pode, (False, motivo em portugues) se nao."""
        papel = papel if papel in CAPACIDADES else PAPEL_COMUM
        permitidas = CAPACIDADES[papel]
        if capacidade in permitidas:
            return True, ""
        return False, (
            f"o teu papel '{papel}' nao permite '{capacidade}'. "
            f"Podes: {', '.join(sorted(permitidas))}."
        )

    def pode_tag(self, papel, nome_tag):
        """Permissao de uma tag concreta do cerebro, pelo nome."""
        nome_tag = (nome_tag or "").strip().upper()
        capacidade = CAPACIDADE_DAS_TAGS.get(nome_tag)
        if capacidade is None:
            return True, ""      # tag sem capacidade declarada: passa
        return self.pode(papel, capacidade)

    # ------------------------------------------------------------------
    # rede de seguranca para acoes perigosas
    # ------------------------------------------------------------------
    def e_perigosa(self, acao):
        """Diz se uma acao (palavra ou tag) mexe em coisas que nao se desfazem."""
        if not acao:
            return False
        alvo = _normalizar(acao)
        return any(_normalizar(p) in alvo for p in PALAVRAS_PERIGOSAS)

    def precisa_confirmacao(self, acao, papel):
        """Acoes perigosas pedem sempre um 'sim' antes de acontecerem.

        Inclusive ao dono. Oobjectivo nao e' a desconfianca (o dono manda),
        e' a Possibilidade de a frase ter sido ouvida mal: um comando dito
        na call vai passar por transcricao, e 'apaga a pasta dos documentos'
        e 'apaga a pasta das downloads' diferem numa palavra.
        """
        if not self.dados.get("exigir_confirmacao", True):
            return False
        return self.e_perigosa(acao)

    def requer_papel(self, capacidade):
        """Qual o papel minimo a capacidade exige (util para texto de ajuda)."""
        for papel in (PAPEL_DONO, PAPEL_ADMIN):
            if capacidade in CAPACIDADES[papel]:
                return papel
        return PAPEL_COMUM

    # ------------------------------------------------------------------
    # texto para o prompt da IA e para os menus
    # ------------------------------------------------------------------
    def resumo_papel(self, papel):
        papel = papel if papel in CAPACIDADES else PAPEL_COMUM
        return f"{papel}: {', '.join(sorted(CAPACIDADES[papel]))}"

    def para_dict(self):
        return dict(self.dados)

    @classmethod
    def from_dict(cls, data, caminho=None):
        return cls(caminho=caminho, dados=data)


def obter_permissoes(caminho=None):
    """Instancia unica, sem estado global espalhado."""
    return Permissoes(caminho=caminho)