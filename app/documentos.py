"""Adaptador HTTP para o motor de documentos do Extrator de Texto."""

import asyncio
import logging
import os
import shutil
import signal
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from . import auth

LIMITE = 100 * 2**20
IMAGENS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}
DIRETOS = {".pdf", ".docx", ".pptx", ".xlsx", ".html", ".htm", ".txt", ".csv", ".json", ".xml"}
PROCESSOS = asyncio.Semaphore(1)
log = logging.getLogger(__name__)


@asynccontextmanager
async def ciclo(_app):
    auth.carregar()
    yield


api = FastAPI(lifespan=ciclo, docs_url=None, redoc_url=None, openapi_url=None)


@api.get("/documentos/info", dependencies=[Depends(auth.cliente_autenticado)])
def info():
    return {"tamanho_max_bytes": LIMITE}


@api.post("/documentos/converter", dependencies=[Depends(auth.cliente_autenticado)])
async def converter(
    request: Request,
    nome: str = Query(min_length=1, max_length=200),
    modo: str = Query(pattern="^(direct|auto-ocr|force-ocr|searchable|force-pdf|redo-pdf|imagem)$"),
    formato: str = Query(default="md", pattern="^(md|txt|pdf)$"),
    paginas: str = Query(default="", pattern=r"^[0-9,\s\-]*$", max_length=150),
):
    nome = nome.replace("\\", "/").rsplit("/", 1)[-1]
    extensao = Path(nome).suffix.lower()
    aceitos = DIRETOS if modo == "direct" else IMAGENS if modo == "imagem" else {".pdf"}
    formatos = {"md"} if modo == "direct" else {"pdf"} if modo in {"searchable", "force-pdf", "redo-pdf"} else {"md", "txt"}
    if extensao not in aceitos or formato not in formatos:
        raise HTTPException(422, "O tipo de arquivo ou de saída não é compatível com o modo selecionado.")
    if PROCESSOS.locked():
        raise HTTPException(429, "O conversor está ocupado. Tente novamente quando a outra conversão terminar.")

    async with PROCESSOS:
        pasta = Path(tempfile.mkdtemp(prefix="extrator-"))
        entrada = pasta / f"entrada{extensao}"
        saidas = pasta / "saida"
        saidas.mkdir()
        try:
            total = 0
            with entrada.open("wb") as arquivo:
                async for parte in request.stream():
                    total += len(parte)
                    if total > LIMITE:
                        raise HTTPException(413, "O limite por documento é de 100 MiB.")
                    arquivo.write(parte)
            if not total:
                raise HTTPException(422, "O arquivo está vazio.")

            processo = await asyncio.create_subprocess_exec(
                "python", "-m", "app.motor_documentos", modo, str(entrada), str(saidas), formato, paginas,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL, start_new_session=True,
            )
            try:
                codigo = await asyncio.wait_for(processo.wait(), 600)
            except (TimeoutError, asyncio.CancelledError):
                try:
                    os.killpg(processo.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                await processo.wait()
                raise
            resultado = next(saidas.glob(f"*.{formato}"), None)
            if codigo or resultado is None:
                log.warning("Falha no motor de documentos: modo=%s, código=%s", modo, codigo)
                raise HTTPException(422, "O motor não conseguiu processar o arquivo. Confira o formato, a proteção e a assinatura do documento.")
        except TimeoutError as exc:
            shutil.rmtree(pasta)
            raise HTTPException(504, "A conversão excedeu dez minutos.") from exc
        except BaseException:
            shutil.rmtree(pasta)
            raise
        return FileResponse(
            resultado, filename=f"{Path(nome).stem}.{formato}", media_type="application/octet-stream",
            background=BackgroundTask(shutil.rmtree, pasta),
        )
