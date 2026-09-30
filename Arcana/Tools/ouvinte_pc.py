# -*- coding: utf-8 -*-
"""Ouvinte do audio do PC (loopback WASAPI) que funciona SEM gastar tokens.

Ideia: ela fica sempre a ouvir o que o PC reproduz, mas nunca chama a API
por iniciativa propria. So' guarda o audio num buffer rolante e responde a
perguntas sobre o que esta a acontecer:

  - tem_som()           -> neste momento ha som a tocar?
  - fala_detetada()     -> houve fala (nao so' musica) nos ultimos segundos?
  - ultimos_segundos(n) -> esse audio em WAV 16 kHz, pronto para o Whisper

Os tokens so' sao gastos no sitio unico onde e' mesmo preciso: quando o
utilizador pergunta 'o que esta a tocar?' ou 'ouviste o que eu disse?'.
A deteccao de fala e' so' energetica (nenhuma chamada a rede), portanto
ficar sempre a escutar custa zero tokens.
"""
import io
import re
import threading
import wave
from collections import deque

import numpy as np

try:
    import soundcard as sc
    TEM_SOUNDCARD = True
except Exception:
    sc = None
    TEM_SOUNDCARD = False

TAXA_CAPTURA = 48000          # taxa dos teus dispositivos WASAPI
TAXA_WHISPER = 16000          # o Whisper da Groq quer 16 kHz mono
CHUNK = 4800                  # 100 ms por leitura
SEGUNDOS_BUFFER = 30          # buffer rolante de 30 s

# Voz ultrapassa normalmente 0.015 de RMS; musica alta tambem passa, por isso
# a fala exige ainda variacao de volume (a voz oscila, a musica e' mais
# constante). Um limiar acima de 0.008 significa "ha som audivel".
LIMIAR_RMS_FALA = 0.015
LIMIAR_VARIACAO = 0.006
LIMIAR_RMS_SOM = 0.008

# Tudo o que o PC reproduz esta cheio de graves (musica, sons de sistema), e
# o Whisper recebe isso e responde com frases inventadas. Cortamos para a
# banda da voz ANTES de mandar para a Groq: e' a banda onde a fala vive.
FAIXA_VOZ = (200.0, 3400.0)


def banda_voz(audio, taxa, faixa=FAIXA_VOZ):
    """Passa-fita (200-3400 Hz) para ficar so' a voz."""
    n = len(audio)
    if n < 32:
        return audio
    spec = np.fft.rfft(audio)
    freqs = np.fft.rfftfreq(n, 1.0 / taxa)
    spec[(freqs < faixa[0]) | (freqs > faixa[1])] = 0.0
    return np.fft.irfft(spec, n)


def reduzir_ruido(audio, taxa, forca=1.5, piso=0.08):
    """Tira o zumbido de fundo (subtracao espectral).

    O teu PC tem sempre som a sair, mesmo sem musica (medi ~0.05 RMS contra
    ~0.10 da voz: sinal com 6 dB de razao, onde o Whisper le mal). Aqui
    medimos o 'fundo' em cada frequencia e subtraimo, o que da +10 a 15 dB.

    Dois cuidados que custaram horas de depuracao:
      - se a janela for SO' fala (sem silencio nenhum), nao ha como medir o
        fundo: subtrair a propria voz deixa o audio mudo;
      - piso espectral em vez de zero, para nao ficar com ruido musical.

    So' corre no momento em que vamos transcrever (um pedido pago), nunca
    durante a escuta continua.
    """
    x = np.asarray(audio, dtype=np.float32)
    n = len(x)
    tam = int(0.032 * taxa)                     # 32 ms
    salto = max(1, tam // 4)
    if n < tam * 3:
        return x
    janela = np.hanning(tam + 1)[:tam].astype(np.float32)
    quadros = (n - tam) // salto + 1
    spec = np.empty((quadros, tam // 2 + 1), dtype=np.complex128)
    for i in range(quadros):
        spec[i] = np.fft.rfft(x[i * salto:i * salto + tam] * janela)
    mag = np.abs(spec)

    energias = mag.sum(axis=1)
    if np.percentile(energias, 20) > 0.5 * np.percentile(energias, 95):
        return x                            # janela so' com voz: nao mexer

    fundo = np.percentile(mag, 20, axis=0)   # o que la esta sempre
    limpo = np.maximum(mag - forca * fundo, piso * fundo)
    maximo = np.max(limpo)
    if maximo > 0:
        limpo = limpo / maximo
    saida = np.zeros(n, dtype=np.float32)
    soma_janela = np.zeros(n, dtype=np.float32)
    for i in range(quadros):
        seg = np.fft.irfft(limpo[i] * np.exp(1j * np.angle(spec[i])), tam)
        saida[i * salto:i * salto + tam] += seg * janela
        soma_janela[i * salto:i * salto + tam] += janela
    return (saida / np.maximum(soma_janela, 1e-6)).astype(np.float32)


def _cortar_calado(y, taxa, minimo=0.8, folga=0.35):
    """Tira o silencio do inicio e do fim.

    O Whisper fica a inventar texto quando recebe silencio depois da frase
    ('O bestseller e uma loja online... O cara cascou.'), por isso ficamos so'
    com o que tem voz e um bocado de folga.
    """
    pico = float(np.max(np.abs(y))) if y.size else 0.0
    if pico <= 0:
        return y
    limiar = max(pico * 0.06, 0.004)
    com_som = np.where(np.abs(y) > limiar)[0]
    if com_som.size == 0:
        return y
    inicio = max(0, int(com_som[0] - folga * taxa))
    fim = min(len(y), int(com_som[-1] + folga * taxa))
    if (fim - inicio) < int(minimo * taxa):
        return y
    return y[inicio:fim]


def _wav_16k_bytes(audio_48k, segundos=None):
    """Audio a 48 kHz -> WAV 16 kHz mono, pronto para o Whisper.

    Atencao ao detalhe que custou horas: reamostrar NAO e recortar. Se em
    vez de reduzir as amostras de 48k para 16k nos limitassemos a ficar so'
    com o ultimo terco, a voz ficava 3x mais rapida e o Whisper escrevia
    'E ai' em vez da frase.
    """
    x = np.asarray(audio_48k, dtype=np.float32)
    if x.ndim > 1:
        x = x.mean(axis=1)
    if segundos:
        x = x[-int(segundos * TAXA_CAPTURA):]
    n = len(x)
    if n < TAXA_CAPTURA // 5:
        return None
    alvo = max(1, int(n * TAXA_WHISPER / TAXA_CAPTURA))
    pos = np.linspace(0, n - 1, alvo)                    # 48 kHz -> 16 kHz
    y = np.interp(pos, np.arange(n), x).astype(np.float32)
    # tira o zumbido e fica so' com a banda da voz
    y = banda_voz(reduzir_ruido(y, TAXA_WHISPER), TAXA_WHISPER).astype(np.float32)
    y = _cortar_calado(y, TAXA_WHISPER)
    pico = float(np.max(np.abs(y))) if y.size else 0.0
    if pico > 0.98:
        y = y * (0.98 / pico)
    elif 0 < pico < 0.05:
        y = y * (0.5 / pico)                             # nivel baixo: Whisper le mal
    with io.BytesIO() as wb:
        with wave.open(wb, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(TAXA_WHISPER)
            wf.writeframes((np.clip(y, -1, 1) * 32767).astype(np.int16).tobytes())
        return wb.getvalue()


class OuvintePC:
    """Escuta o audio reproduzido pelo PC (loopback) sem chamar a rede."""

    def __init__(self, segundos=SEGUNDOS_BUFFER):
        self.segundos = segundos
        max_blocos = max(1, int(TAXA_CAPTURA * segundos / CHUNK))
        self._buffer = deque(maxlen=max_blocos)
        self._lock = threading.Lock()
        self._thread = None
        self._parar = threading.Event()
        self.dispositivo = None
        self.erro = None
        self.rms_atual = 0.0
        self.pico = 0.0
        self._rms_historico = deque(maxlen=max(1, int(segundos * 10)))
        self._rms_por_bloco = deque(maxlen=max_blocos)   # energia na banda da voz
        self._nivel_bruto = deque(maxlen=max_blocos)     # energia total (qualquer som)
        self.total_lido = 0
        # Piso de ruido: o teu PC tem som quase sempre (musica, sons de
        # sistema). Um limiar fixo disparava sem parar; com o piso justo,
        # so' conta como fala o que estiver bem ACIMA do que ja la estava.
        self._piso_voz = 0.0
        self._contador_piso = 0

    # ------------------------------------------------------------------ API
    def iniciar(self):
        """Arranca a escuta em segundo plano. True se ficou mesmo a ouvir."""
        if self._thread is not None and not self._parar.is_set():
            return True
        if not TEM_SOUNDCARD:
            self.erro = "pacote 'soundcard' nao instalado"
            return False
        self._parar.clear()
        self._thread = threading.Thread(target=self._gravar_loop, daemon=True,
                                        name="ouvinte-pc")
        self._thread.start()
        return True

    def parar(self):
        self._parar.set()
        self._thread = None

    def a_viver(self):
        return self._thread is not None and self.total_lido > CHUNK * 2

    def tem_som(self):
        """Ha algum som a sair do PC neste momento?"""
        if self._nivel_bruto:
            return self._nivel_bruto[-1] > LIMIAR_RMS_SOM
        return self.rms_atual > LIMIAR_RMS_SOM

    def fala_agora(self):
        """Ha FALA (nao so' som) neste momento?

        Medido no teu PC: o zumbido de fundo fica em ~0.05 RMS e a voz sobe
        a ~0.10 com picos a ~0.22. Por isso medimos o pico do ultimo segundo
        e comparamos com o piso: o fundo (max 0.075) nunca chega a 2x o piso,
        a voz chega. Um limiar fixo disparava sem parar.
        """
        with self._lock:
            ultimos = list(self._rms_por_bloco)[-10:]     # ~1 s
        if not ultimos:
            return False
        limiar = max(LIMIAR_RMS_FALA, self._piso_voz * 2.0)
        return max(ultimos) > limiar

    def fala_detetada(self, ultimos=8):
        """True se houve fala (e nao so' musica) nos ultimos `ultimos` s."""
        with self._lock:
            hist = list(self._rms_historico)
        if not hist:
            return False
        fatia = hist[-max(1, int(ultimos * 10)):]
        loud = [r for r in fatia if r > LIMIAR_RMS_FALA]
        if not loud:
            return False
        # a voz varia de volume; uma musica alta e' mais constante
        variacao = max(loud) - min(loud)
        return variacao > LIMIAR_VARIACAO

    def ultimos_segundos(self, segundos=12, so_fala=True):
        """Audio recente em WAV 16 kHz mono (pronto para o Whisper).

        so_fala=True corta para o troco com voz e passa um filtro de banda
        (200-3400 Hz). Sem isto, o Whisper recebe o audio todo do PC (graves
        de musica, sons de sistema) e inventa frases em vez de repetir.
        """
        with self._lock:
            blocos = list(self._buffer)
            rmss = list(self._rms_por_bloco)
        if not blocos:
            return None
        inicio = 0
        if so_fala and len(rmss) == len(blocos):
            # fala = pico de 1 s acima do dobro do piso de ruido
            limiar = max(LIMIAR_RMS_FALA, self._piso_voz * 2.0)
            pico = [max(rmss[max(0, k - 9):k + 1]) for k in range(len(rmss))]
            loud = [p > limiar for p in pico]
            i = len(loud) - 1
            while i >= 0 and not loud[i]:
                i -= 1
            if i < 0:
                return None                    # so' musica/silencio
            j = i
            quietos = 0
            while j > 0 and quietos <= 8:      # ~0.8 s de pausa dentro da frase
                j -= 1
                quietos = 0 if loud[j] else quietos + 1
            max_blocos = int(segundos * TAXA_CAPTURA / CHUNK)
            inicio = max(j - 3, i - max_blocos + 1, len(blocos) - max_blocos)
        audio = np.concatenate(blocos[inicio:], axis=0)
        return _wav_16k_bytes(audio, segundos)

    def _wav_de(self, blocos, segundos=None):
        """WAV 16 kHz a partir de blocos de 100 ms do loopback.

        E' isto que o loop de escuta em tempo real usa: junta a fala que
        acabou de acontecer e devolve logo o WAV pronto para o Whisper.
        """
        if not blocos:
            return None
        audio = np.concatenate([np.asarray(b, dtype=np.float32) for b in blocos],
                               axis=0)
        return _wav_16k_bytes(audio, segundos)

    def estado(self):
        return {
            "vivo": self.a_viver(),
            "dispositivo": self.dispositivo,
            "rms": round(self.rms_atual, 5),
            "pico": round(self.pico, 4),
            "tem_som": self.tem_som(),
            "fala_agora": self.fala_agora(),
            "piso_voz": round(self._piso_voz, 4),
            "buffer_s": round(len(self._buffer) * CHUNK / TAXA_CAPTURA, 1),
            "lido_s": round(self.total_lido / TAXA_CAPTURA, 1),
            "erro": self.erro,
        }

    # ------------------------------------------------------------- interno
    def _gravar_loop(self):
        try:
            altifalante = sc.default_speaker()
            microfone = sc.get_microphone(id=altifalante.name,
                                          include_loopback=True)
            self.dispositivo = f"{microfone.name} (loopback)"
            with microfone.recorder(samplerate=TAXA_CAPTURA, channels=2) as rec:
                while not self._parar.is_set():
                    try:
                        bloco = rec.record(numframes=CHUNK)
                    except Exception as e:
                        self.erro = f"falha a ler: {e}"
                        self._parar.set()
                        break
                    if bloco is None or getattr(bloco, "size", 0) == 0:
                        self._parar.set()
                        break
                    self.total_lido += len(bloco)
                    mono = bloco.mean(axis=1).astype(np.float32)
                    bruto = float(np.sqrt(np.mean(mono ** 2))) if mono.size else 0.0
                    # energia so' na banda da voz: e' o que distingue fala de
                    # musica (que tem muito grave mas pouca voz)
                    voz = banda_voz(mono, TAXA_CAPTURA)
                    self.rms_atual = float(np.sqrt(np.mean(voz ** 2))) if voz.size else 0.0
                    self.pico = float(np.max(np.abs(mono))) if mono.size else 0.0
                    self._rms_historico.append(self.rms_atual)
                    with self._lock:
                        self._buffer.append(bloco.astype(np.float32))
                        self._rms_por_bloco.append(self.rms_atual)
                        self._nivel_bruto.append(bruto)
                    # recalcula o piso de ruido de 2 em 2 segundos
                    self._contador_piso += 1
                    if self._contador_piso >= 20:
                        self._contador_piso = 0
                        self._piso_voz = float(np.percentile(
                            list(self._rms_por_bloco), 20))
        except Exception as e:
            self.erro = str(e)
            self._parar.set()


_ouvinte = None


def obter_ouvinte(segundos=SEGUNDOS_BUFFER):
    """Ouvinte partilhado (arranca uma vez so)."""
    global _ouvinte
    if _ouvinte is None:
        _ouvinte = OuvintePC(segundos=segundos)
    return _ouvinte


def requer_escuta_pc(texto):
    """O utilizador quer saber o que se ouve no PC?"""
    t = (texto or "").lower()
    padroes = (r"\bo que (?:está|esta|tava) a tocar\b",
               r"\bque (?:música|musica|canção|cricao|som) (?:é|e) (?:esta|essa|este)\b",
               r"\bo que (?:se )?ouve\b",
               r"\bouviste\b", r"\bouviu\b",
               r"\bo que (?:eu )?disse\b",
               r"\bestou a ouvir\b", r"\bque se ouve\b",
               r"\bo que está a ser (?:dito|falado)\b")
    return any(re.search(p, t) for p in padroes)