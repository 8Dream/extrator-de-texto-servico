"""Configuracao do servico Extrator de Texto (tudo por variavel de ambiente)."""
import os
from pathlib import Path

VERSAO = "0.1.0"

DADOS = Path(os.environ.get("EXTRATOR_DADOS", "/dados"))
ARQUIVOS = DADOS / "arquivos"
JOBS = DADOS / "jobs"
HISTORICO = DADOS / "historico.json"

# Arquivo com um cliente por linha: "nome:token". Nunca vai para o repositorio.
TOKENS_ARQ = Path(os.environ.get("EXTRATOR_TOKENS", "/run/secrets/extrator_tokens"))

RETENCAO_HORAS = float(os.environ.get("EXTRATOR_RETENCAO_HORAS", "24"))
UPLOAD_PARCIAL_HORAS = float(os.environ.get("EXTRATOR_UPLOAD_PARCIAL_HORAS", "6"))
TAMANHO_MAX = int(float(os.environ.get("EXTRATOR_TAMANHO_MAX_GB", "4")) * 2**30)
DURACAO_MAX_S = int(float(os.environ.get("EXTRATOR_DURACAO_MAX_H", "6")) * 3600)
CHUNK_MAX = 64 * 2**20

# Sablier: enquanto houver trabalho, o proprio servico renova a sessao para nao ser desligado no meio.
SABLIER_URL = os.environ.get("SABLIER_URL", "http://sablier:10000")
SABLIER_NOME = os.environ.get("SABLIER_NOME", "extrator-servico")
SABLIER_SESSAO = os.environ.get("SABLIER_SESSAO", "15m")

# Nomes iguais aos do programa -> modelos Whisper abertos (licenca MIT/Apache-2.0), baixados sem login.
MODELOS = {
    "tiny": "openai/whisper-tiny",
    "base": "openai/whisper-base",
    "small": "openai/whisper-small",
    "medium": "openai/whisper-medium",
    "large-v3": "openai/whisper-large-v3",
    "large-v3-turbo": "openai/whisper-large-v3-turbo",
}
MODELO_PADRAO = os.environ.get("EXTRATOR_MODELO_PADRAO", "large-v3")
# Lote por modelo: medido na Spark, e a memoria unificada e apertada. large-v3 com lote 8 derruba ~18 GB da memoria
# disponivel do host, com lote 4 ~12 GB (4,5x o tempo real); o turbo com lote 8 usa uns 5 GB e passa de 30x.
LOTE_POR_MODELO = {"large-v3": 4, "medium": 8, "large-v3-turbo": 8, "small": 16, "base": 16, "tiny": 16}


def lote_para(modelo: str) -> int:
    return int(os.environ.get("EXTRATOR_LOTE", "0")) or LOTE_POR_MODELO.get(modelo, 4)
OCIOSO_DESCARREGAR_S = int(os.environ.get("EXTRATOR_OCIOSO_DESCARREGAR_S", "600"))

IDIOMAS = {"pt": "portuguese", "en": "english", "es": "spanish", "fr": "french", "de": "german", "it": "italian"}
