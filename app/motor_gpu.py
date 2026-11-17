"""Motor de transcricao: Whisper (modelos abertos) na GPU via PyTorch/transformers.

Por que nao faster-whisper: o wheel do ctranslate2 para aarch64 e so CPU; a GPU GB10 so aparece pelo PyTorch.
O audio e cortado em janelas de ate ~28 s nos silencios (sem cortar palavra), transcrito em lotes e o
progresso real (segundos de audio processados) sai a cada lote."""
import gc
import json
import logging
import subprocess
import threading
import time
from typing import Callable

import numpy as np

from . import config
from .formatos import Seg

log = logging.getLogger("extrator.motor")
SR = 16000
_pipe = None
_pipe_modelo = None
_ultimo_uso = time.time()
_trava = threading.Lock()


class Cancelado(Exception):
    pass


def decodificar(caminho: str) -> np.ndarray:
    """Qualquer audio/video -> float32 mono 16 kHz. Usa ffmpeg; cai para soundfile se nao houver."""
    # /usr/bin/ffmpeg (apt, completo, com AAC/m4a/mp4) primeiro; o "ffmpeg" da imagem NGC e uma versao restrita sem AAC.
    for binario in ("/usr/bin/ffmpeg", "ffmpeg"):
        try:
            proc = subprocess.run(
                [binario, "-v", "error", "-nostdin", "-i", caminho, "-vn", "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"],
                capture_output=True, check=True)
            audio = np.frombuffer(proc.stdout, dtype=np.float32)
            if audio.size:
                return audio
        except (FileNotFoundError, subprocess.CalledProcessError) as exc:
            log.info(json.dumps({"evento": "ffmpeg_falhou", "binario": binario, "erro": str(exc)[:160]}))
    import soundfile as sf
    dados, sr = sf.read(caminho, dtype="float32", always_2d=True)
    dados = dados.mean(axis=1)
    if sr != SR:
        import librosa
        dados = librosa.resample(dados, orig_sr=sr, target_sr=SR)
    return dados.astype(np.float32)


def dividir(audio: np.ndarray, alvo: float = 28.0, minimo: float = 8.0) -> list[tuple[int, int]]:
    """Janelas (inicio, fim) em amostras, cortadas no meio de silencios; descarta janelas sem fala."""
    frame = int(0.02 * SR)
    n = len(audio) // frame
    if n == 0:
        return []
    rms = np.sqrt((audio[: n * frame].reshape(n, frame) ** 2).mean(axis=1) + 1e-12)
    limiar = max(float(np.percentile(rms, 20)) * 2.0, 0.004)
    silencio = rms < limiar
    cortes, i = [], 0
    while i < n:
        if silencio[i]:
            j = i
            while j < n and silencio[j]:
                j += 1
            if (j - i) * 0.02 >= 0.3:
                cortes.append(((i + j) // 2) * frame)
            i = j
        else:
            i += 1
    janelas, ini, total = [], 0, len(audio)
    while ini < total:
        fim_max = ini + int(alvo * SR)
        if fim_max >= total:
            janelas.append((ini, total))
            break
        cand = [c for c in cortes if ini + int(minimo * SR) <= c <= fim_max]
        fim = cand[-1] if cand else fim_max
        janelas.append((ini, fim))
        ini = fim
    return [(a, b) for a, b in janelas if float(np.abs(audio[a:b]).max()) >= 0.01]


def _carregar(modelo_id: str):
    global _pipe, _pipe_modelo
    with _trava:
        if _pipe is not None and _pipe_modelo == modelo_id:
            return _pipe
        _descarregar_sem_trava()
        import torch
        from transformers import pipeline
        t0 = time.time()
        _pipe = pipeline("automatic-speech-recognition", model=modelo_id, dtype=torch.float16, device="cuda:0")
        _pipe_modelo = modelo_id
        log.info(json.dumps({"evento": "modelo_carregado", "modelo": modelo_id, "segundos": round(time.time() - t0, 1)}))
        return _pipe


def _descarregar_sem_trava() -> None:
    global _pipe, _pipe_modelo
    if _pipe is not None:
        _pipe = None
        _pipe_modelo = None
        gc.collect()
        try:
            import torch
            torch.cuda.empty_cache()
        except Exception:
            pass


def descarregar_se_ocioso() -> bool:
    """Libera a memoria do modelo depois de um tempo sem uso (memoria da Spark e orcamento apertado)."""
    with _trava:
        if _pipe is not None and time.time() - _ultimo_uso > config.OCIOSO_DESCARREGAR_S:
            _descarregar_sem_trava()
            log.info(json.dumps({"evento": "modelo_descarregado_por_ociosidade"}))
            return True
    return False


def modelo_carregado() -> str | None:
    return _pipe_modelo


def transcrever(caminho: str, modelo_id: str, idioma: str, lote: int, cancelar: threading.Event,
                etapa: Callable[[str], None], progresso: Callable[[float, float], None]) -> tuple[list[Seg], dict]:
    global _ultimo_uso
    etapa("decodificando")
    audio = decodificar(caminho)
    duracao = len(audio) / SR
    if duracao > config.DURACAO_MAX_S:
        raise ValueError(f"duracao_maxima: {duracao:.0f} s excede {config.DURACAO_MAX_S} s")
    if cancelar.is_set():
        raise Cancelado()
    etapa("carregando modelo")
    pipe = _carregar(modelo_id)
    janelas = dividir(audio)
    gk = {"task": "transcribe"}
    if idioma in config.IDIOMAS:
        gk["language"] = config.IDIOMAS[idioma]
    etapa("transcrevendo")
    progresso(0.0, duracao)
    segs: list[Seg] = []
    for k in range(0, len(janelas), lote):
        if cancelar.is_set():
            raise Cancelado()
        grupo = janelas[k: k + lote]
        entradas = [{"raw": audio[a:b], "sampling_rate": SR} for a, b in grupo]
        saidas = pipe(entradas, batch_size=lote, return_timestamps=True, generate_kwargs=gk)
        for (a, b), saida in zip(grupo, saidas):
            base, dur_j = a / SR, (b - a) / SR
            pedacos = saida.get("chunks") or []
            if not pedacos:
                texto = (saida.get("text") or "").strip()
                if texto:
                    segs.append(Seg(base, base + dur_j, texto))
                continue
            for c in pedacos:
                ini, fim = c.get("timestamp") or (None, None)
                ini = base + (ini if ini is not None else 0.0)
                fim = base + (fim if fim is not None else dur_j)
                texto = (c.get("text") or "").strip()
                if texto:
                    segs.append(Seg(ini, max(fim, ini), texto))
        progresso(min(grupo[-1][1] / SR, duracao), duracao)
        _ultimo_uso = time.time()
    progresso(duracao, duracao)
    _ultimo_uso = time.time()
    return segs, {"duracao_s": round(duracao, 1), "janelas": len(janelas), "idioma": idioma}
