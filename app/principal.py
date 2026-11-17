"""API HTTP do Extrator de Texto (servico). Tudo exige token, menos /saude (usado pelo Sablier e pelo healthcheck)."""
import asyncio
import json
import logging
import time
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse, PlainTextResponse, Response, StreamingResponse
from pydantic import BaseModel, Field

from . import armazenamento, auth, config, diarizacao, motor_gpu
from .jobs import ATIVOS, GER

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("extrator")
INICIO = time.time()


@asynccontextmanager
async def ciclo(_app):
    armazenamento.iniciar()
    n = auth.carregar()
    GER.iniciar()
    log.info(json.dumps({"evento": "servico_iniciado", "versao": config.VERSAO, "clientes": n}))
    yield


app = FastAPI(title="Extrator de Texto - servico", version=config.VERSAO, lifespan=ciclo, docs_url=None, redoc_url=None, openapi_url=None)


@app.get("/saude")
def saude():
    return {"ok": True, "versao": config.VERSAO}


@app.get("/v1/info")
def info(cliente: str = Depends(auth.cliente_autenticado)):
    gpu = None
    try:
        import torch
        gpu = torch.cuda.get_device_name(0) if torch.cuda.is_available() else None
    except Exception:
        pass
    return {
        "versao": config.VERSAO, "cliente": cliente, "motor": "gpu-pytorch-whisper", "gpu": gpu,
        "modelos": list(config.MODELOS), "modelo_padrao": config.MODELO_PADRAO, "idiomas": ["auto", *config.IDIOMAS],
        "formatos": ["txt", "md", "srt", "json"], "diarizacao_disponivel": diarizacao.disponivel(),
        "limites": {"tamanho_max_bytes": config.TAMANHO_MAX, "duracao_max_s": config.DURACAO_MAX_S, "parte_max_bytes": config.CHUNK_MAX},
        "retencao_horas": config.RETENCAO_HORAS, "jobs_ativos": GER.ativos(), "modelo_carregado": motor_gpu.modelo_carregado(),
        "espaco_livre_gb": armazenamento.espaco_livre_gb(), "no_ar_ha_s": round(time.time() - INICIO),
    }


# ------------------------- envio em partes (resumivel) -------------------------
class NovoArquivo(BaseModel):
    nome: str = Field(min_length=1, max_length=200)
    tamanho: int = Field(gt=0)


@app.post("/v1/arquivos", status_code=201)
def novo_arquivo(corpo: NovoArquivo, cliente: str = Depends(auth.cliente_autenticado)):
    try:
        return armazenamento.criar(cliente, corpo.nome, corpo.tamanho)
    except ValueError as exc:
        raise HTTPException(413, str(exc))


def _meu_arquivo(arquivo_id: str, cliente: str) -> dict:
    m = armazenamento.meta(arquivo_id)
    if m is None or m["cliente"] != cliente:
        raise HTTPException(404, "arquivo nao encontrado")
    return m


@app.get("/v1/arquivos/{arquivo_id}")
def estado_arquivo(arquivo_id: str, cliente: str = Depends(auth.cliente_autenticado)):
    m = _meu_arquivo(arquivo_id, cliente)
    return {"id": m["id"], "recebido": m["recebido"], "tamanho": m["tamanho"], "completo": m["recebido"] == m["tamanho"]}


@app.put("/v1/arquivos/{arquivo_id}")
async def enviar_parte(arquivo_id: str, request: Request, deslocamento: int = Query(ge=0), cliente: str = Depends(auth.cliente_autenticado)):
    m = _meu_arquivo(arquivo_id, cliente)
    partes, total = [], 0
    async for pedaco in request.stream():
        total += len(pedaco)
        if total > config.CHUNK_MAX:
            raise HTTPException(413, f"parte maior que {config.CHUNK_MAX} bytes")
        partes.append(pedaco)
    try:
        recebido = armazenamento.acrescentar(arquivo_id, deslocamento, b"".join(partes))
    except ValueError:
        # o cliente retoma de onde o servidor parou
        return JSONResponse({"erro": "deslocamento_errado", "recebido": armazenamento.meta(arquivo_id)["recebido"]}, status_code=409)
    except OverflowError as exc:
        raise HTTPException(413, str(exc))
    return {"recebido": recebido, "tamanho": m["tamanho"], "completo": recebido == m["tamanho"]}


# ------------------------------- jobs -------------------------------
class Diarizar(BaseModel):
    ativar: bool = False
    min: int | None = Field(default=None, ge=1, le=20)
    max: int | None = Field(default=None, ge=1, le=20)


class Parametros(BaseModel):
    modelo: str = config.MODELO_PADRAO
    idioma: str = "pt"
    diarizar: Diarizar = Diarizar()


class NovoJob(BaseModel):
    arquivo_id: str
    tipo: str = "transcricao"
    parametros: Parametros = Parametros()


@app.post("/v1/jobs", status_code=202)
def novo_job(corpo: NovoJob, cliente: str = Depends(auth.cliente_autenticado)):
    if corpo.tipo != "transcricao":
        raise HTTPException(422, "tipo nao suportado (por enquanto: transcricao)")
    p = corpo.parametros
    if p.modelo not in config.MODELOS:
        raise HTTPException(422, f"modelo invalido; use um de {list(config.MODELOS)}")
    if p.idioma != "auto" and p.idioma not in config.IDIOMAS:
        raise HTTPException(422, f"idioma invalido; use auto ou um de {list(config.IDIOMAS)}")
    m = _meu_arquivo(corpo.arquivo_id, cliente)
    if m["recebido"] != m["tamanho"]:
        raise HTTPException(409, f"envio incompleto: {m['recebido']} de {m['tamanho']} bytes")
    job = GER.criar(cliente, corpo.arquivo_id, m["nome"], p.model_dump())
    return job.publico()


def _meu_job(job_id: str, cliente: str):
    j = GER.obter(job_id, cliente)
    if j is None:
        raise HTTPException(404, "job nao encontrado")
    return j


@app.get("/v1/jobs")
def listar(cliente: str = Depends(auth.cliente_autenticado)):
    return [j.publico() for j in GER.listar(cliente)]


@app.get("/v1/jobs/{job_id}")
def ver_job(job_id: str, cliente: str = Depends(auth.cliente_autenticado)):
    return _meu_job(job_id, cliente).publico()


@app.get("/v1/jobs/{job_id}/eventos")
async def eventos(job_id: str, cliente: str = Depends(auth.cliente_autenticado)):
    j = _meu_job(job_id, cliente)

    async def gerar():
        ultimo = ""
        while True:
            atual = json.dumps(j.publico(), ensure_ascii=False)
            if atual != ultimo:
                yield f"data: {atual}\n\n"
                ultimo = atual
            else:
                yield ": ping\n\n"
            if j.estado not in ATIVOS:
                break
            await asyncio.sleep(1)

    return StreamingResponse(gerar(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/v1/jobs/{job_id}/log")
def log_job(job_id: str, desde: int = Query(default=0, ge=0), cliente: str = Depends(auth.cliente_autenticado)):
    j = _meu_job(job_id, cliente)
    return {"desde": desde, "total": len(j.linhas), "linhas": j.linhas[desde:]}


@app.post("/v1/jobs/{job_id}/cancelar")
def cancelar(job_id: str, cliente: str = Depends(auth.cliente_autenticado)):
    j = _meu_job(job_id, cliente)
    if j.estado in ATIVOS:
        j.cancelar.set()
        j.registrar("cancelamento pedido")
    return j.publico()


@app.get("/v1/jobs/{job_id}/resultado")
def resultado(job_id: str, formato: str = Query(default="json", pattern="^(txt|md|srt|json)$"), cliente: str = Depends(auth.cliente_autenticado)):
    j = _meu_job(job_id, cliente)
    if j.estado != "concluida":
        raise HTTPException(409, f"job em '{j.estado}'")
    texto, tipo = GER.resultado(j, formato)
    return Response(texto, media_type=tipo)


@app.delete("/v1/jobs/{job_id}", status_code=204)
def apagar(job_id: str, cliente: str = Depends(auth.cliente_autenticado)):
    GER.apagar(_meu_job(job_id, cliente))
    return Response(status_code=204)
