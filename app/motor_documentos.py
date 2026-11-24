"""Executa uma operação do motor do aplicativo em uma pasta descartável."""

import sys
from pathlib import Path

import extrator_core as motor


def executar():
    modo, entrada, saidas, formato, paginas = sys.argv[1:]
    arquivo = Path(entrada)
    destino = Path(saidas)
    motor.WORK_DIR = arquivo.parent / "work"
    motor.LOG_DIR = arquivo.parent / "logs"
    motor.get_jobs = lambda: 2

    if modo == "imagem":
        motor.ocr_images([arquivo], destino, formato)
    elif modo == "direct":
        motor.direct_convert(arquivo, destino)
    elif modo in {"auto-ocr", "force-ocr"}:
        motor.ocr_pdf_to_text(arquivo, destino, modo.split("-", 1)[0], paginas, formato)
    else:
        pdf_modo = {"searchable": "skip", "force-pdf": "force", "redo-pdf": "redo"}[modo]
        motor.searchable_pdf(arquivo, destino, pdf_modo, paginas)


if __name__ == "__main__":
    try:
        executar()
    finally:
        motor.SESSION_LOG.unlink(missing_ok=True)
