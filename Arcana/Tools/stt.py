"""Voz -> texto. O mesmo pedido Whisper para toda a gente.

Existia uma copia disto dentro do run.py, so' para a voz local. O Discord
precisa de transcreverundreds de falas seguidas e nao devia ter a sua propria
versao: quando o modelo ou a chave mudam, tm de mudar nos dois sitios. Por
isso o run.py passou a chamar aqui.
"""

import io
import wave

import numpy as np
import requests

MODELO_TRANSCRICAO = "whisper-large-v3-turbo"
URL_GROQ = "https://api.groq.com/openai/v1/audio/transcriptions"


def em_wav(audio_int16, taxa=16000):
    """Empacota PCM int16 mono em bytes de WAV.

    Devolve bytes e nao um ficheiro: a escuta da call do Discord nunca toca
    no disco, o audio vive so' em memoria ate ir para a API.
    """
    if isinstance(audio_int16, (bytes, bytearray, memoryview)):
        bruto = bytes(audio_int16)
    else:
        bruto = b"".join(audio_int16)
    with io.BytesIO() as wb:
        with wave.open(wb, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(taxa)
            wf.writeframes(bruto)
        wb.seek(0)
        return wb.read()


def reamostrar(audio_int16, origem, destino=16000):
    """PCM int16 de `origem` Hz para `destino` Hz, por interpolacao.

    A call do Discord devolve 48 kHz e o Whisper quer 16 kHz. `audioop` faz
    isto melhor, mas foi removido do Python 3.13; como o numpy ja e'
    dependencia do projecto, fica a interpolar em numpy e nao ha uma segunda
    coisa a poder partir com aupgrade.
    """
    if origem == destino:
        return bytes(audio_int16)
    amostras = np.frombuffer(bytes(audio_int16), dtype=np.int16)
    if amostras.size == 0:
        return b""
    destino_n = int(round(amostras.size * destino / origem))
    if destino_n <= 0:
        return b""
    x_origem = np.arange(amostras.size, dtype=np.float64)
    x_destino = np.linspace(0, amostras.size - 1, destino_n, dtype=np.float64)
    convertidas = np.interp(x_destino, x_origem, amostras.astype(np.float64))
    return convertidas.astype(np.int16).tobytes()


def nivel(audio_int16):
    """Volume medio do PCM, de 0 (silencio) a 1 (maximo)."""
    amostras = np.frombuffer(bytes(audio_int16), dtype=np.int16)
    if amostras.size == 0:
        return 0.0
    amostras = amostras.astype(np.float32) / 32768.0
    return float(np.sqrt(np.mean(amostras ** 2)))


def transcrever(wav_bytes, api_key, modelo=MODELO_TRANSCRICAO, idioma="pt",
                timeout=60):
    """Manda um WAV ao Whisper da Groq. Devolve o texto, ou None."""
    if not wav_bytes or not api_key:
        return None
    cabecalho = {"Authorization": f"Bearer {api_key}"}
    ficheiros = {"file": ("audio.wav", wav_bytes, "audio/wav"),
                 "model": (None, modelo), "language": (None, idioma)}
    # temperature=0 trava o loop de repeticoes do Whisper quando o audio nao
    # e' fala (musica, silencio): com temperatura >0 ele inventa frases.
    dados = {"temperature": "0"}
    try:
        resp = requests.post(URL_GROQ, headers=cabecalho, files=ficheiros,
                             data=dados, timeout=timeout)
    except Exception:
        return None
    if resp.status_code != 200:
        return None
    try:
        return resp.json().get("text", "").strip()
    except Exception:
        return None


def transcrever_pcm(audio_int16, taxa, api_key, **kw):
    """PCM cru -> texto. Junta reamostragem e WAV numa so' chamada."""
    if taxa != 16000:
        audio_int16 = reamostrar(audio_int16, taxa, 16000)
    return transcrever(em_wav(audio_int16, 16000), api_key, **kw)