"""Arquivos enviados em partes (resumivel) e limpeza por retencao. O audio e apagado assim que o job termina."""
import json
import logging
import shutil
import threading
import time
import uuid

from . import config

log = logging.getLogger("extrator.armazenamento")
_trava = threading.Lock()


def iniciar() -> None:
    config.ARQUIVOS.mkdir(parents=True, exist_ok=True)
    config.JOBS.mkdir(parents=True, exist_ok=True)


def _pasta(arquivo_id: str):
    if not arquivo_id.isalnum():  # evita caminho fora da pasta
        raise ValueError("id invalido")
    return config.ARQUIVOS / arquivo_id


def criar(cliente: str, nome: str, tamanho: int) -> dict:
    if tamanho <= 0 or tamanho > config.TAMANHO_MAX:
        raise ValueError(f"tamanho invalido (maximo {config.TAMANHO_MAX} bytes)")
    arquivo_id = uuid.uuid4().hex[:16]
    pasta = _pasta(arquivo_id)
    pasta.mkdir(parents=True)
    meta = {"id": arquivo_id, "cliente": cliente, "nome": nome[:200], "tamanho": tamanho, "criado": time.time()}
    (pasta / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    (pasta / "dados.bin").write_bytes(b"")
    return {"id": arquivo_id, "recebido": 0, "tamanho": tamanho, "parte_maxima": config.CHUNK_MAX}


def meta(arquivo_id: str) -> dict | None:
    try:
        pasta = _pasta(arquivo_id)
        m = json.loads((pasta / "meta.json").read_text(encoding="utf-8"))
        m["recebido"] = (pasta / "dados.bin").stat().st_size
        return m
    except (OSError, ValueError, json.JSONDecodeError):
        return None


def caminho(arquivo_id: str):
    return _pasta(arquivo_id) / "dados.bin"


def acrescentar(arquivo_id: str, deslocamento: int, dados: bytes) -> int:
    """Grava a parte SOMENTE se o deslocamento bater com o que ja foi recebido (senao o cliente retoma)."""
    with _trava:
        m = meta(arquivo_id)
        if m is None:
            raise FileNotFoundError(arquivo_id)
        if deslocamento != m["recebido"]:
            raise ValueError(f"deslocamento {deslocamento} diferente do recebido {m['recebido']}")
        if m["recebido"] + len(dados) > m["tamanho"]:
            raise OverflowError("parte excede o tamanho declarado")
        with open(caminho(arquivo_id), "ab") as f:
            f.write(dados)
        return m["recebido"] + len(dados)


def apagar(arquivo_id: str) -> None:
    try:
        shutil.rmtree(_pasta(arquivo_id), ignore_errors=True)
    except ValueError:
        pass


def limpar_antigos() -> int:
    """Retencao: uploads parciais antigos e jobs/resultados vencidos."""
    agora, removidos = time.time(), 0
    for pasta in config.ARQUIVOS.glob("*"):
        try:
            if agora - pasta.stat().st_mtime > config.UPLOAD_PARCIAL_HORAS * 3600:
                shutil.rmtree(pasta, ignore_errors=True)
                removidos += 1
        except OSError:
            pass
    for pasta in config.JOBS.glob("*"):
        try:
            if agora - pasta.stat().st_mtime > config.RETENCAO_HORAS * 3600:
                shutil.rmtree(pasta, ignore_errors=True)
                removidos += 1
        except OSError:
            pass
    if removidos:
        log.info(json.dumps({"evento": "retencao", "removidos": removidos}))
    return removidos


def espaco_livre_gb() -> float:
    return round(shutil.disk_usage(config.DADOS).free / 2**30, 1)
