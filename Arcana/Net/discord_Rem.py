"""A Haimiya no Discord: entra na call, ouve cada pessoa a serio e responde.

Isto era o unico bloco do projecto que nao existia. O run.py tinha o
`from Arcana.Net.discord_Rem import run_discord_bot` comentado a espera de um
ficheiro que nunca chegou a ser escrito, e o painel (F4) ja desenhava
configuracoes para um bot que nao havia. Aqui esta o bot.

O que ele faz
--------------
* Entra na call e ESCUTA CADA UTILIZADOR SEPARADAMENTE. O `vc.listen()` do
  discord.py entrega um `AudioSource` de cada vez, com `source.user_id`: e'
  isso que permite saber quem disse o quê, em vez de receber a mistura toda.
* Cada pessoa tem a sua deteccao de fala (energia com limiar adaptado ao
  ruido de fundo), por isso duas pessoas a falar ao mesmo tempo nao se
  atropelam.
* FICA EM FILA. Varias pessoas falam, a Haimiya responde a uma de cada vez,
  pela ordem em que chegou. Quem e' dono/admin passa a frente.
* PODE SER INTERROMPIDA a falar. Se um dono ou admin disser "silêncio", a
  fala para imediatamente e a fila limpa. E' o "pode ser interrompida
  enquanto fala" do pedido.
* Responde no chat por mencao, por DM, ou a texto livre nos servidores
  marcados como activos.
* Pergunta o que cada um pode fazer. Os comandos de PC, ficheiros e
  Photoshop sao recusados a quem nao tem o papel certo, com uma explicacao
  em vez de um erro.

Como se liga ao run.py
----------------------
O run.py passa um `responder` async. Este modulo NAO chama a IA
directamente: chama o `responder` de volta, e assim o cerebro, a memoria e
as ferramentas ficam num sitio so. Se o run.py indicar o seu loop principal,
o `responder` e' agendado nesse loop (e o loop do Discord fica livre para
continuar a ouvir e a cortar a fala) - se nao, corre no loop do Discord.
"""

import asyncio
import copy
import json
import os
import queue
import re
import shutil
import threading
import time
from collections import deque

import discord
from discord.ext import commands

from Arcana.Tools import stt
from Arcana.Tools.permissions import (
    PALAVRAS_INTERRUPTORAS,
    PAPEL_ADMIN,
    PAPEL_COMUM,
    PAPEL_DONO,
    Permissoes,
)

# --- afinacao da escuta -------------------------------------------------
BLOCO_MS = 20          # o Opus do Discord da blocos de 20 ms
INICIO_MS = 200        # voz tem de durar isto para contar (mata os "hmm")
PICO_MINIMO = 2.2      # e' preciso highlights: duracao sem energia e' um estalo
FIM_MS = 900           # este silencio fecha a fala
MAX_SEGUNDOS = 14      # corte de seguranca para nao acumular audio eterno
LIMITE_ARRANQUE = 1.5  # fala que nunca confirmou e' deitada fora
LIMITE_TEXTO = 400     # o Whisper devolve: mais do que isto e' alucinar

# --- prioridades da fila ------------------------------------------------
PRIO_DONO = 0
PRIO_ADMIN = 1
PRIO_CONFIRMACAO = 2
PRIO_COMUM = 10

VOZES = {
    "pt-BR-Female": "pt-BR-FranciscaNeural",
    "pt-BR-Male": "pt-BR-AntonioNeural",
    "feminina": "pt-BR-FranciscaNeural",
    "masculina": "pt-BR-AntonioNeural",
}


def _intents():
    intents = discord.Intents.default()
    intents.message_content = True     # para ler as mensagens
    intents.voice_states = True       # para saber quem esta na call
    intents.members = True            # para descobrir o papel de cada um
    intents.guilds = True
    return intents


def _ffmpeg():
    """ffmpeg do sistema, ou o que o imageio-ffmpeg traz de consigo.

    Sem isto a IA fala no texto mas cala-se na call: o discord.py precisa do
    ffmpeg para codificar Opus e nao ha ninguem para o instalar.
    """
    caminho = shutil.which("ffmpeg")
    if caminho:
        return caminho
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


# O edge-tts devolve PCM de 24 kHz, mono, 16 bits. Como o audio entra por
# stdin, o ffmpeg nao o consegue sondar: e' preciso dizer-lhe o formato.
_ENTRADA_FFMPEG = "-f s16le -ar 24000 -ac 1"


class _FonteEdgeTTS:
    """edge-tts -> ffmpeg, atravessando a fronteira entre async e sync.

    O discord.py le o audio com `read()` numa thread e escreve no stdin do
    ffmpeg. O edge-tts e' assincrono. Sem esta ponte, ou o ffmpeg recebia o
    gerador como se fosse um caminho, ou a IA ficava muda na call.

    `read()` devolver bytes vazios fecha o stdin e o ffmpeg acaba o que
    tem: e' assim que uma frase cortada a meio para de falar.
    """

    def __init__(self, texto, voz, parar=None, bloco=3840):
        self.texto = texto
        self.voz = voz
        self.parar = parar or threading.Event()
        self.bloco = bloco
        self.erro = None
        self._pedacos = queue.Queue()
        self._fim = False
        self._thread = threading.Thread(
            target=self._bombeiro, daemon=True, name="edge-tts->ffmpeg")

    def start(self):
        self._thread.start()
        return self

    def _bombeiro(self):
        """Corre o `async for` do edge-tts na sua propria thread."""
        try:
            import edge_tts
        except Exception as e:
            self.erro = e
            self._fim = True
            return

        async def correr():
            comunicador = edge_tts.Communicate(self.texto, self.voz)
            async for pedaco in comunicador.stream():
                if pedaco.get("type") == "audio" and pedaco["data"]:
                    self._pedacos.put(pedaco["data"])

        try:
            asyncio.run(correr())
        except Exception as e:
            self.erro = e
        finally:
            self._fim = True

    def read(self, n=-1):
        """O que o discord.py pede. Vazio significa 'acabou'.

        Cuidado: `_fim` quer dizer que o edge-tts ja acabou, nao que
        o audio tenha acabado. Como o edge-tts e' muito mais rapido que a
        reproducao, quando o produtor acaba a fila costuma estar cheia —
        devolver vazio aqui mandava o ffmpeg com o stdin logo fechado e a
        IA ficava muda na call.
        """
        if n is None or n < 0:
            n = self.bloco
        if self.parar.is_set():
            self._pedacos = queue.Queue()      # deita fora o que sobrou
            return b""
        try:
            return self._pedacos.get_nowait()
        except queue.Empty:
            pass
        while not self.parar.is_set():
            try:
                return self._pedacos.get(timeout=0.2)
            except queue.Empty:
                if self._fim:
                    return b""
        return b""



class _FalaDe:
    """Deteccao de fala de UMA pessoa.

    Nao ha VAD de rede aqui: e' energia com um limiar que se adapta ao ruido
    de fundo da call. Um VAD pesado (silero) por pessoa custaria RAM a mais
    para o ganho que da numa sala de Discord.
    """

    __slots__ = ("buffer", "voz_ms", "silencio_ms", "picos", "pico", "falando",
                 "taxa")

    def __init__(self, taxa):
        self.taxa = taxa
        self.buffer = bytearray()
        self.voz_ms = 0
        self.silencio_ms = 0
        self.picos = deque(maxlen=50)   # ~1 s, so' de enquanto calado
        self.pico = 0.0                 # mais alto ponto do que se juntou
        self.falando = False

    def _limiar(self):
        if not self.picos:
            return 0.015
        ruido = min(self.picos)
        # 5x o ruido, com rede de seguranca. Sem isto, uma sala silenciosa
        # faz o microfone da call apanhar o teclado de alguem como frase.
        return max(0.012, min(0.06, ruido * 5 + 0.008))

    def _limpar(self):
        self.buffer = bytearray()
        self.voz_ms = 0
        self.silencio_ms = 0
        self.pico = 0.0
        self.falando = False

    def offer(self, pcm):
        """Empurra um bloco. Devolve os bytes da fala fechada, ou None."""
        nivel = stt.nivel(pcm)
        cauda = int(self.taxa * 2 * 0.3)      # 0.3 s antes da 1a palavra

        # O ruido de fundo so' se aprende no silencio a serio. Medir
        # enquanto a pessoa fala faz o limiar subir com a propria voz e a
        # deteccao trava: era o que acontecia antes desta linha.
        if not self.buffer and nivel <= 0.012:
            self.picos.append(nivel)

        limiar = self._limiar()

        if nivel > limiar:
            self.voz_ms += BLOCO_MS
            self.silencio_ms = 0
            if nivel > self.pico:
                self.pico = nivel
            self.buffer += pcm
            # Duas condicoes, e nao uma so: duracao E energia. Um "eh" de
            # 150 ms tem duracao e nao tem energia nenhuma - e transcreve-lo
            # gasta um pedido ao Whisper para dar "(silencio)".
            if self.voz_ms >= INICIO_MS and self.pico >= limiar * PICO_MINIMO:
                self.falando = True
            elif len(self.buffer) > cauda + int(self.taxa * 2 * LIMITE_ARRANQUE):
                # barulho que nunca chegou a ser palavra
                self.voz_ms = 0
                self.pico = 0.0
                self.buffer = self.buffer[-cauda:]
        elif self.falando:
            self.silencio_ms += BLOCO_MS
            self.buffer += pcm
            if self.silencio_ms >= FIM_MS:
                fala = bytes(self.buffer)
                self._limpar()
                return fala
            if len(self.buffer) >= self.taxa * 2 * MAX_SEGUNDOS:
                fala = bytes(self.buffer)
                self._limpar()
                return fala
        else:
            # calado antes da frase: guarda um bocado para nao cortar a
            # primeira palavra
            self.buffer = (self.buffer + pcm)[-cauda:]
        return None


class Pedido:
    """Uma coisa que alguem pediu e que ainda nao foi respondida."""

    __slots__ = ("prioridade", "ordem", "user_id", "nome", "texto", "papel",
                 "guild_id", "canal_id", "origem", "responde")

    def __init__(self, texto, user_id, nome, papel, guild_id=None,
                 canal_id=None, origem="voz", responde=None):
        self.texto = texto
        self.user_id = user_id
        self.nome = nome
        self.papel = papel
        self.guild_id = guild_id
        self.canal_id = canal_id
        self.origem = origem      # "voz" | "chat" | "dm"
        self.responde = responde  # funcao async(canal) para mandar a resposta
        self.prioridade = {
            PAPEL_DONO: PRIO_DONO,
            PAPEL_ADMIN: PRIO_ADMIN,
        }.get(papel, PRIO_COMUM)
        self.ordem = time.time()

    def __lt__(self, outro):
        if self.prioridade != outro.prioridade:
            return self.prioridade < outro.prioridade
        return self.ordem < outro.ordem

    def para_dict(self):
        return {
            "texto": self.texto,
            "autor": self.nome,
            "autor_id": self.user_id,
            "papel": self.papel,
            "origem": self.origem,
            "guild_id": self.guild_id,
            "canal_id": self.canal_id,
        }


class RemDoDiscord(commands.Bot):
    """O bot propriamente dito."""

    def __init__(self, responder, permissoes=None, nome_ai="Rem",
                 config=None, loop_principal=None, api_whisper=None,
                 log=print):
        super().__init__(command_prefix=config.get("prefixo", "!"),
                         intents=_intents())
        self.responder = responder
        self.permissoes = permissoes or Permissoes()
        self.nome_ai = nome_ai
        self.cfg = dict(_PADRAO_CFG, **(config or {}))
        self.loop_principal = loop_principal
        self.api_whisper = api_whisper
        self.log = log

        self.escuta = None            # _EscutaSeparada quando ha call
        self.fila = None              # asyncio.PriorityQueue
        self.trabalhador = None       # task da fila
        self.parar_bot = asyncio.Event()
        self._cortar = asyncio.Event()  # "cala-te": corta a fala a meio
        self._contador = 0

        # o motor de musica (fase seguinte) liga-se aqui para a IA calar a
        # musica enquanto fala e retomar depois. Enquanto nao existir, sao
        # duas funcoes vazias e o bot funciona na mesma.
        self.antes_de_falar = None
        self.depois_de_falar = None

        # Os handlers sao metidos como atributos de instancia e nao com
        # `add_event_handler`, que foi removido no discord.py 2.x. O
        # `on_message` do bot so' serve para processar comandos, por isso
        # o nosso chama-o primeiro: sem isso, !entrar e !papeis nao
        # respondiam a nada.
        self.on_ready = self._ao_pronto
        self.on_message = self._ao_mensagem

        # No discord.py 2.7 um comando decorado numa subclasse de Bot
        # NAO entra na fila: o decorador so' marca o atributo da classe.
        # Sem estas linhas, !entrar !sair !parar !fila !papeis nao
        # existiam e o bot so' respondia a 'help'. E' uma copia para nao
        # partilhar o mesmo objeto com outras instancias.
        for atributo in ("cmd_entrar", "cmd_sair", "cmd_parar",
                         "cmd_fila", "cmd_papeis"):
            self.add_command(copy.copy(getattr(type(self), atributo)))

    # ------------------------------------------------------------------
    # arranque
    # ------------------------------------------------------------------
    async def _ao_pronto(self):
        self.log(f" [DISCORD] {self.nome_ai} ligada como {self.user}")
        await self._guardar_guilds()
        if self.cfg.get("auto_entrar"):
            await self._entrar_por_initros()
        self._arrancar_trabalhador()

    async def _guardar_guilds(self):
        """Guarda a lista de servidores para o painel (F4) mostrar."""
        lista = [{"id": g.id, "name": g.name} for g in self.guilds]
        try:
            self.permissoes.guardar()
            caminho = self.permissoes.caminho
            dados = {}
            if os.path.exists(caminho):
                with open(caminho, "r", encoding="utf-8") as f:
                    dados = json.load(f)
            dados["discord_guilds_cache"] = lista
            with open(caminho, "w", encoding="utf-8") as f:
                json.dump(dados, f, indent=4, ensure_ascii=False)
        except Exception as e:
            self.log(f" [DISCORD] Nao foi possivel guardar os servidores: {e}")

    def _arrancar_trabalhador(self):
        if self.fila is None:
            self.fila = asyncio.PriorityQueue(maxsize=int(self.cfg.get("fila_max", 40)))
        if self.trabalhador is None or self.trabalhador.done():
            self.trabalhador = asyncio.create_task(self._ciclo_fila())

    # ------------------------------------------------------------------
    # ciclo da fila
    # ------------------------------------------------------------------
    async def _ciclo_fila(self):
        """Responde a um pedido de cada vez, por ordem de chegada.

        Um pedido por vez e' que torna a 'fila inteligente' intelligent: duas
        respostas ao mesmo tempo fariam a Haimiya falar por cima dela mesma
        e o historico ia para dois sitios ao mesmo tempo.
        """
        while not self.parar_bot.is_set():
            try:
                pedido = await asyncio.wait_for(self.fila.get(), timeout=2.0)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                return
            try:
                await self._atender(pedido)
            except Exception as e:
                self.log(f" [DISCORD] Falha a atender um pedido: {e}")
            finally:
                if self.fila is not None:
                    self.fila.task_done()

    async def _atender(self, pedido):
        texto = (pedido.texto or "").strip()
        if not texto:
            return

        # Alguem pediu para ela calar-se?
        if self._e_pedido_de_parar(texto, pedido.papel):
            await self.interromper(quem=pedido.nome)
            return

        # Fala muito comprida e' quase sempre do Whisper a inventar
        if len(texto) > LIMITE_TEXTO:
            self.log(f" [DISCORD] Descartado o que disse {pedido.nome}: "
                     f"{len(texto)} caracteres e' alucinar")
            return

        resposta = await self._perguntar_ao_cerebro(pedido)
        if not resposta:
            return

        # O run.py ja devolveu a fala limpa, sem tags. Mesmo assim passa
        # pelo filtro: se alguma vez escapar uma, e' melhor calar a call
        # do que ler '<COMPUTER:digitar:password>' em voz alta.
        resposta = re.sub(r'<[^>]+>', '', resposta).strip()
        if not resposta:
            return

        # Resposta escrita (mencao, DM, chat) vai para o ecra. Resposta a
        # voz vai para a call. Nao se faz as duas coisas: quem mandou
        # mensagem nao precisa de ouvir a IA pelo canal de voz.
        if pedido.origem == "voz":
            if await self._esta_na_call():
                await self.falar(resposta)
            else:
                await self._enviar(pedido, resposta)
        else:
            await self._enviar(pedido, resposta)

    def _e_pedido_de_parar(self, texto, papel):
        if papel == PAPEL_COMUM:
            return False
        t = texto.lower().strip(" .!,?")
        return any(t == p or t.startswith(p + " ") or t.startswith(p + ",")
                   for p in PALAVRAS_INTERRUPTORAS)

    async def _perguntar_ao_cerebro(self, pedido):
        """Manda o pedido ao run.py e traz a resposta."""
        if self.responder is None:
            return None
        try:
            if self.loop_principal is not None and self.loop_principal.is_running():
                fut = asyncio.run_coroutine_threadsafe(
                    self.responder(pedido.para_dict()), self.loop_principal)
                return await asyncio.wrap_future(fut)
            return await self.responder(pedido.para_dict())
        except asyncio.CancelledError:
            raise
        except Exception as e:
            self.log(f" [DISCORD] O cerebro nao respondeu: {e}")
            return None

    async def _enviar(self, pedido, texto):
        if pedido.responde is None:
            return
        try:
            await pedido.responde(texto)
        except Exception as e:
            self.log(f" [DISCORD] Nao foi possivel responder: {e}")

    # ------------------------------------------------------------------
    # voz
    # ------------------------------------------------------------------
    async def _esta_na_call(self):
        # No discord.py 2.x `voice_clients` e' uma LISTA de VoiceProtocol,
        # nao um dicionario por servidor. A via certa e' guild.voice_client.
        for guild in self.guilds:
            vc = guild.voice_client
            if vc is not None and vc.is_connected():
                return True
        return False

    def _voice_client(self):
        for vc in self.voice_clients:
            if vc is not None and vc.is_connected():
                return vc
        return None

    async def falar(self, texto):
        """Fala num canal de voz, e pode ser cortada a meio da frase."""
        if not texto:
            return
        vc = self._voice_client()
        if vc is None or not vc.is_connected():
            return

        if self.antes_de_falar:
            try:
                await _talvez_await(self.antes_de_falar())
            except Exception:
                pass

        try:
            await self._tocar(vc, texto)
        finally:
            if self.depois_de_falar:
                try:
                    await _talvez_await(self.depois_de_falar())
                except Exception:
                    pass

    async def _tocar(self, vc, texto):
        # O `VOZES` e' um dicionario nosso (apelido -> nome da voz da
        # Microsoft). O edge-tts nao expoe uma lista de vozes, por isso
        # validar com `edge_tts.VOICES` rebentava com AttributeError.
        pedida = self.cfg.get("voz", "pt-BR-Female")
        voz = VOZES.get(pedida, pedida)
        if not isinstance(voz, str) or not voz:
            voz = VOZES["pt-BR-Female"]

        # `parar` e' local a esta frase: e' o botao de "cala-te" que corta
        # a fala a meio sem matar as restantes da fila.
        parar = threading.Event()
        fonte = _FonteEdgeTTS(_para_fala(texto), voz, parar).start()

        try:
            # O discord.py escreve o que `read()` devolve no stdin do
            # ffmpeg, numa thread. Por isso a fonte tem de ter `read()` e
            # nao pode ser um `async def` que devolve audio: passava o
            # gerador ao ffmpeg como se fosse um ficheiro.
            audio = discord.FFmpegOpusAudio(
                fonte, executable=_ffmpeg(), pipe=True,
                before_options=_ENTRADA_FFMPEG)
        except Exception as e:
            self.log(f" [DISCORD] ffmpeg falhou: {e}")
            return

        try:
            vc.play(audio)
        except Exception as e:
            self.log(f" [DISCORD] Nao foi possivel falar: {e}")
            parar.set()
            return

        try:
            while vc.is_playing():
                if self._cortar.is_set():
                    parar.set()
                    vc.stop_playing()
                    self.log(" [DISCORD] Fala cortada a pedido de alguem.")
                    break
                await asyncio.sleep(0.05)
        finally:
            parar.set()
            # Garante que o ffmpeg do turno anterior morreu: se nao, o
            # proximo play rebenta com 'Already playing audio'.
            try:
                vc.stop_playing()
            except Exception:
                pass

    async def interromper(self, quem=None):
        """Cala a IA e limpa a fila. E' o 'pode ser interrompida enquanto fala'."""
        self._cortar.set()
        vc = self._voice_client()
        if vc is not None and vc.is_connected():
            try:
                vc.stop_playing()
            except Exception:
                pass
        quantos = self.fila.qsize() if self.fila is not None else 0
        if self.fila is not None:
            while not self.fila.empty():
                try:
                    self.fila.get_nowait()
                    self.fila.task_done()
                except Exception:
                    break
        self._cortar.clear()
        self.log(f" [DISCORD] Interrompida por {quem or 'alguem'} "
                 f"({quantos} pedidos descartados).")

    # ------------------------------------------------------------------
    # escuta por pessoa
    # ------------------------------------------------------------------
    async def _comecar_a_ouvir(self, vc):
        await self._parar_de_ouvir()
        self.escuta = _EscutaSeparada(self, vc)
        await self.escuta.iniciar()

    async def _parar_de_ouvir(self):
        escuta, self.escuta = self.escuta, None
        if escuta is not None:
            await escuta.parar()

    async def _ao_entrar_numa_call(self, vc):
        await self._comecar_a_ouvir(vc)
        self._arrancar_trabalhador()
        self.log(f" [DISCORD](call)Ligada a '{vc.channel.name}'. "
                 f"A ouvir cada pessoa em separado.")

    async def _ao_sair_da_call(self):
        await self._parar_de_ouvir()
        self.log(" [DISCORD](call) Saiu da call.")

    def _falas_prontas(self):
        """Esvazia o que a escuta apanhou. Chamado pela _EscutaSeparada.

        Nao pode ser `await`: esta funcao corre dentro do `vc.listen()`, e o
        discord.py espera pelo callback ali mesmo. Por isso cria tarefas e
        devolve logo - o audio nunca para de entrar.
        """
        escuta = self.escuta
        if escuta is None:
            return
        while True:
            try:
                user_id, pcm = escuta.saida.get_nowait()
            except asyncio.QueueEmpty:
                return
            asyncio.create_task(self._tratar_fala(user_id, pcm))

    async def _tratar_fala(self, user_id, pcm):
        """Transcreve uma fala e mete o pedido na fila."""
        if self.parar_bot.is_set():
            return
        member = self._procurar(user_id)
        guild = member.guild if member is not None else None
        papel = self.permissoes.papel_de(user_id, guild, member)
        nome = str(member.display_name) if member is not None else f"utilizador {user_id}"

        if not self.api_whisper:
            self.log(" [DISCORD] Sem GROQ_API_KEY_LLM: nao ha como ouvir a call.")
            return

        texto = await asyncio.to_thread(
            stt.transcrever_pcm, pcm, 48000, self.api_whisper)
        if not texto:
            return

        # Voz e' barata, voz errada e' cara: a limpeza e' a mesma de sempre.
        texto = re.sub(r"\s+", " ", texto).strip(" .,!?")
        if not texto or len(texto) > LIMITE_TEXTO:
            return

        self.log(f" [DISCORD](voz) {nome} [{papel}]: {texto}")

        if self._e_pedido_de_parar(texto, papel):
            await self.interromper(quem=nome)
            return

        pedido = Pedido(
            texto=texto, user_id=user_id, nome=nome, papel=papel,
            guild_id=guild.id if guild is not None else None,
            canal_id=None, origem="voz",
        )
        self._enfileirar(pedido)

    def _enfileirar(self, pedido):
        self._arrancar_trabalhador()
        self._contador += 1
        pedido.ordem = self._contador
        try:
            self.fila.put_nowait(pedido)
        except asyncio.QueueFull:
            self.log(" [DISCORD] Fila cheia: pedido descartado. "
                     "Muitos a falar ao mesmo tempo.")
            # `_avisar` e' uma coroutine: chamar sem await nao avisava
            # ninguem e deixava um "coroutine was never awaited" no log.
            alvo = self._avisar(pedido, "a fila esta cheia, espera um bocado")
            try:
                asyncio.get_running_loop().create_task(alvo)
            except RuntimeError:
                alvo.close()          # sem loop: nao ha para onde avisar

    async def _avisar(self, pedido, texto):
        if pedido.responde is not None:
            try:
                await pedido.responde(texto)
            except Exception:
                pass

    def _procurar(self, user_id):
        for guild in self.guilds:
            member = guild.get_member(user_id)
            if member is not None:
                return member
        return None

    # ------------------------------------------------------------------
    # chat / DM
    # ------------------------------------------------------------------
    async def _ao_mensagem(self, mensagem):
        """Responde por mencao, por DM ou a texto livre nos servidores ativos.

        Em servidor so' responde a quem a chamou: mencao, reply a uma
        mensagem da IA, ou a pessoa em foco. Sem isso, num servidor com
        movimento, a IA comentava tudo o que alguem disse.
        """
        if mensagem.author.bot:
            return
        # O autor pode nao estar ligado: em DM e' um `discord.User`, nao um
        # `discord.Member`. A versao anterior descartava a mensagem toda
        # neste ponto e as DMs nunca funcionavam.
        if self.user is not None and mensagem.author.id == self.user.id:
            return

        # Deixa o bot tratar primeiro os comandos (!entrar, !papeis, ...).
        await super().on_message(mensagem)

        cfg = self.cfg
        guild = mensagem.guild
        e_dm = guild is None

        # --- o servidor esta ligado a este bot? ---
        if e_dm:
            if not cfg.get("dm_ativo", True):
                return
        else:
            if not cfg.get("servidor_ativo", True):
                return
            desligados = {str(x) for x in (cfg.get("servidores_desligados") or [])}
            if str(guild.id) in desligados:
                return

            respondendo = await self._e_reply_para_si(mensagem)
            mencionada = any(u.id == self.user.id for u in (mensagem.mentions or []))
            em_foco = self._em_foco(mensagem.author)

            # Numa sala ligada a IA ouve o que se diz, mesmo sem mencao.
            # Quem nao quer isto desliga 'texto_livre' no painel.
            texto_livre = cfg.get("texto_livre", True)
            if not (respondendo or em_foco or texto_livre):
                return
            if mencionada and not cfg.get("mencoes", True):
                return

        texto = re.sub(r"<@!?\d+>", " ", mensagem.content).strip()
        if not texto:
            return

        papel = self.permissoes.papel_de(mensagem.author.id, guild, mensagem.author)
        origem = "dm" if e_dm else "chat"
        self.log(f" [DISCORD]({origem}) {mensagem.author.display_name} [{papel}]: {texto}")

        canal = mensagem.channel

        async def responde(saida):
            for parte in _dividir(saida):
                try:
                    await canal.send(parte)
                except Exception:
                    return
                await asyncio.sleep(0.4)     # para nao apanhar rate limit

        self._enfileirar(Pedido(
            texto=texto, user_id=mensagem.author.id,
            nome=str(mensagem.author.display_name), papel=papel,
            guild_id=guild.id if guild is not None else None,
            canal_id=canal.id, origem=origem, responde=responde,
        ))

    def _em_foco(self, member):
        alvo = (self.cfg.get("alvo_nome") or "").strip().lower()
        if not alvo:
            return False
        return alvo in (str(member.name).lower(), str(member.display_name).lower())

    async def _e_reply_para_si(self, mensagem):
        if mensagem.reference is None:
            return False
        try:
            ref = await mensagem.reference.resolved
        except Exception:
            return False
        return ref is not None and ref.author.id == self.user.id

    # ------------------------------------------------------------------
    # comandos
    # ------------------------------------------------------------------
    # Os comandos registam-se com o decorador em cima do metodo (e nao com
    # `add_command` no __init__) porque o discord.py 2.x le o signature da
    # funcao crua, incluindo o `self`. O nome e' escrito a mao para o user
    # digitar !entrar e nao !cmd_entrar.
    @commands.command(name="entrar")
    async def cmd_entrar(self, ctx: commands.Context):
        """Entra na call de voz."""
        destino = None
        canal = getattr(ctx.author, "voice", None)
        if canal is not None:
            destino = canal.channel
        else:
            alvo_id = self.cfg.get("canal_voz_id")
            for g in ctx.guilds:
                if alvo_id and str(g.id) == str(alvo_id):
                    for c in g.voice_channels:
                        if str(c.id) == str(alvo_id):
                            destino = c
                if destino is None:
                    for c in g.voice_channels:
                        if sum(1 for m in c.members if not m.bot) > 0:
                            destino = c
                            break
        if destino is None:
            await ctx.send("Nao encontrei um sitio para entrar. Entra numa call primeiro.")
            return
        await self._ligar_call(ctx.guild, destino)
        await ctx.send(f"Entrei em {destino.name}. Fala e eu respondo.")

    async def _ligar_call(self, guild, canal):
        try:
            if guild.voice_client is not None:
                await guild.voice_client.disconnect()
            vc = await canal.connect(self_deaf=True)
        except Exception as e:
            self.log(f" [DISCORD] Nao foi possivel entrar na call: {e}")
            return None
        await self._ao_entrar_numa_call(vc)
        return vc

    async def _entrar_por_initros(self):
        alvo_id = self.cfg.get("canal_voz_id")
        for guild in self.guilds:
            for c in guild.voice_channels:
                if not alvo_id or str(c.id) == str(alvo_id):
                    await self._ligar_call(guild, c)
                    return

    @commands.command(name="sair")
    async def cmd_sair(self, ctx: commands.Context):
        """Sai da call."""
        vc = ctx.guild.voice_client
        if vc is not None:
            await self._ao_sair_da_call()
            await vc.disconnect()
            await ctx.send("Saí da call.")
        else:
            await ctx.send("Ja nao estou em call nenhuma.")

    @commands.command(name="parar")
    async def cmd_parar(self, ctx: commands.Context):
        """Cala a IA e limpa a fila."""
        papel = self.permissoes.papel_de(ctx.author.id, ctx.guild, ctx.author)
        if papel == PAPEL_COMUM:
            await ctx.send("So o dono ou um admin podem calar-me.")
            return
        quantos = self.fila.qsize() if self.fila is not None else 0
        await self.interromper(quem=str(ctx.author.display_name))
        await ctx.send(f"Cala. {quantos} pedidos foram deitados fora.")

    @commands.command(name="fila")
    async def cmd_fila(self, ctx: commands.Context):
        """Mostra o que esta a espera de resposta."""
        pendentes = self._pendentes()
        if not pendentes:
            await ctx.send("Fila vazia.")
            return
        linhas = [f"{i+1}. {p.nome} [{p.papel}]: {p.texto[:60]}"
                  for i, p in enumerate(pendentes[:10])]
        await ctx.send(f"Na fila ({len(pendentes)}):\n" + "\n".join(linhas))

    def _pendentes(self):
        if self.fila is None:
            return []
        try:
            return sorted(self.fila._queue)      # leitura, so' para mostrar
        except Exception:
            return []

    @commands.command(name="papeis")
    async def cmd_papeis(self, ctx: commands.Context):
        """Mostra o teu papel e o que cada papel pode pedir."""
        from Arcana.Tools.permissions import CAPACIDADES
        papel = self.permissoes.papel_de(ctx.author.id, ctx.guild, ctx.author)
        linhas = [f"O teu papel e' **{papel}**.", ""]
        for nome in (PAPEL_DONO, PAPEL_ADMIN, PAPEL_COMUM):
            marcas = " <- tu" if nome == papel else ""
            linhas.append(f"**{nome}**{marcas}: "
                          f"{', '.join(sorted(CAPACIDADES[nome]))}")
        await ctx.send("\n".join(linhas))


class _EscutaSeparada:
    """O unico consumidor de `vc.listen()`, a separar o audio por pessoa."""

    def __init__(self, bot, voice_client):
        self.bot = bot
        self.vc = voice_client
        self.falas = {}
        self.saida = asyncio.Queue()
        self._task = None

    async def iniciar(self):
        if not self.vc.is_connected():
            return
        self._task = asyncio.create_task(self._ciclo())

    async def parar(self):
        task, self._task = self._task, None
        if task is not None:
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass

    async def _ciclo(self):
        try:
            # Um `AudioSource` de cada vez, com o user_id de quem falou.
            # E' este detalhe que faz a escuta ser 'separada': sem ele so'
            # haveria a mistura de toda a sala.
            #
            # O callback tem de ser rapido: o discord.py chama-o de dentro
            # do `listen()` e espera. Por isso aqui so' se empurra os bytes
            # para uma fila, e quem transcreve e' outra task.
            ao_falar = self.bot._falas_prontas
            async for fonte in self.vc.listen():
                user_id = getattr(fonte.source, "user_id", None)
                pcm = fonte.data
                if user_id is None or not pcm:
                    continue
                voz = self.falas.get(user_id)
                if voz is None:
                    voz = self.falas[user_id] = _FalaDe(48000)
                fala = voz.offer(pcm)
                if fala:
                    self.saida.put_nowait((user_id, fala))
                    ao_falar()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            self.bot.log(f" [DISCORD] A escuta parou: {e}")


# ----------------------------------------------------------------------
# ligacao ao run.py
# ----------------------------------------------------------------------
class _Controlador:
    """Corre o bot num loop proprio, separado do loop principal.

    O run.py ja tem o seu loop ocupado com o microfone e os menus. Se o bot
    partilhasse esse loop, um pedido lento da API do Discord pararia a
    leitura do microfone. Por isso corre numa thread com o loop dele.
    """

    def __init__(self, token, responder, **opcoes):
        self.token = token
        self.opcoes = opcoes
        self.loop = None
        self.bot = None
        self.thread = None
        self.erro = None
        self._responder = responder

    def arrancar(self):
        self.thread = threading.Thread(target=self._correr, daemon=True,
                                       name="discord-bot")
        self.thread.start()

    def _correr(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_until_complete(self._main())
        except Exception as e:
            self.erro = str(e)
        finally:
            try:
                self.loop.close()
            except Exception:
                pass

    async def _main(self):
        self.bot = RemDoDiscord(self._responder, **self.opcoes)
        try:
            await self.bot.start(self.token)      # bloqueia ate fechar
        except discord.LoginFailure:
            self.erro = ("token do Discord invalido. Copia-o outra vez do "
                         "Developer Portal e confirma que tem as scopes right.")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            self.erro = str(e)

    def _agendar(self, coro):
        if self.loop is None or not self.loop.is_running():
            return None
        return asyncio.run_coroutine_threadsafe(coro, self.loop)

    def parar(self):
        if self.bot is not None:
            self._agendar(self.bot.close())
        if self.loop is not None and self.loop.is_running():
            self.loop.call_soon_threadsafe(self.loop.stop)

    def estado(self):
        if self.erro is not None:
            return f"erro: {self.erro}"
        if self.bot is not None and self.bot.is_ready():
            return f"ligada como {self.bot.user}"
        return "a ligar"


# O painel (gui_handler) grava tudo com o prefixo `discord_`, mas o resto do
# codigo antigo do run.py gravava sem. As duas coisas sao lidas aqui, com o
# `discord_*` a ganhar, para o painel ter efeito sem se perder nada do que
# ja estava no brain.json.
_ALIASES_CFG = {
    "prefixo":              "discord_prefix",
    "servidor_ativo":       "discord_server_active",
    "mencoes":              "discord_mentions",
    "dinamismo":            "discord_dinamismo",
    "dm_ativo":             "discord_dm_active",
    "dm_dono_responde_sempre": "discord_dm_dono_always",
    "texto_livre":          "discord_texto_livre",
    "alvo_nome":            "discord_target_user_name",
    "auto_entrar":          "discord_auto_join",
    "canal_voz_id":         "discord_voice_channel_id",
    "voz":                  "discord_voice",
    "fila_max":             "discord_queue_max",
    "music_mode":           "discord_music_mode",
    "auto_post":            "discord_auto_post",
    "auto_post_unidade":    "discord_auto_post_unit",
    "servidores_desligados": "discord_disabled_guilds",
}


def carregar_config(caminho_brain="Arcana/armazen/brain.json"):
    """Le a configuracao do Discord do brain.json."""
    cfg = dict(_PADRAO_CFG)
    try:
        with open(caminho_brain, "r", encoding="utf-8") as f:
            dados = json.load(f)
        for chave in _PADRAO_CFG:
            # 1a escolha: a chave do painel. 2a: a chave antiga sem prefixo.
            for candidata in (dados.get(_ALIASES_CFG.get(chave, chave)),
                              dados.get(chave)):
                if candidata is not None:
                    cfg[chave] = candidata
                    break
    except Exception:
        pass
    # Um numero de fila a menos de 1 rebentava a PriorityQueue.
    try:
        cfg["fila_max"] = max(1, int(cfg["fila_max"]))
    except Exception:
        cfg["fila_max"] = 40
    return cfg


def iniciar_bot_discord(responder, nome_ai="Rem", api_whisper=None,
                        caminho_brain="Arcana/armazen/brain.json",
                        loop_principal=None, log=print):
    """Liga o bot. Devolve o controlador (para poder parar)."""
    token = os.getenv("DISCORD_TOKEN", "").strip()
    if not token:
        raise RuntimeError("DISCORD_TOKEN em falta no .env.")
    cfg = carregar_config(caminho_brain)
    permissoes = Permissoes(caminho=caminho_brain)
    controlador = _Controlador(
        token, responder,
        permissoes=permissoes,
        nome_ai=nome_ai,
        config=cfg,
        loop_principal=loop_principal,
        api_whisper=api_whisper,
        log=log,
    )
    controlador.arrancar()
    return controlador


# ----------------------------------------------------------------------
# utilitarios
# ----------------------------------------------------------------------
_PADRAO_CFG = {
    "prefixo": "!",
    "servidor_ativo": True,
    "mencoes": True,
    "dm_ativo": True,
    "dm_dono_responde_sempre": True,
    "texto_livre": True,
    "alvo_nome": "",
    "auto_entrar": False,
    "canal_voz_id": "",
    "voz": "pt-BR-Female",
    "fila_max": 40,
    "music_mode": False,
    "auto_post": 0,
    "auto_post_unidade": "Minutos",
    "servidores_desligados": [],
    "dinamismo": True,
}


async def _talvez_await(valor):
    if asyncio.iscoroutine(valor):
        return await valor
    return valor


def _para_fala(texto):
    """Limpa o texto antes do edge-tts o ler.

    O Whisper devolve pontuacao feita de pontos e o TTS le isso como
    pontuacao a mais. O asterisco e' lido literalmente ('abre asterisco'),
    por isso saem todos.
    """
    t = re.sub(r"\s+", " ", texto or "").strip()
    t = t.replace("*", "")
    return t[:600]


def _dividir(texto, tamanho=1900):
    """Parte para caber no limite do Discord, sem cortar palavras ao meio."""
    texto = texto or ""
    if len(texto) <= tamanho:
        return [texto]
    partes, atual = [], ""
    for frase in re.split(r"(?<=[.!?…])\s+", texto):
        while len(frase) > tamanho:
            partes.append(frase[:tamanho])
            frase = frase[tamanho:]
        if len(atual) + len(frase) + 1 > tamanho:
            partes.append(atual.strip())
            atual = frase
        else:
            atual = f"{atual} {frase}".strip()
    if atual:
        partes.append(atual)
    return [p for p in partes if p]