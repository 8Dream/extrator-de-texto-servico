"""Autenticacao por token (Bearer). O servico RECUSA subir sem arquivo de tokens: nao existe modo aberto."""
import hmac
import logging

from fastapi import Header, HTTPException

from . import config

log = logging.getLogger("extrator.auth")
_tokens: dict[str, str] = {}


def carregar() -> int:
    """Le 'cliente:token' por linha. Retorna quantos clientes; levanta erro se nao houver nenhum."""
    _tokens.clear()
    if not config.TOKENS_ARQ.is_file():
        raise RuntimeError(f"arquivo de tokens ausente: {config.TOKENS_ARQ} (o servico nao sobe aberto)")
    for linha in config.TOKENS_ARQ.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or ":" not in linha:
            continue
        cliente, token = linha.split(":", 1)
        if len(token.strip()) >= 24:
            _tokens[cliente.strip()] = token.strip()
    if not _tokens:
        raise RuntimeError("nenhum token valido (minimo 24 caracteres) no arquivo de tokens")
    return len(_tokens)


def cliente_autenticado(authorization: str | None = Header(default=None)) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "token ausente", headers={"WWW-Authenticate": "Bearer"})
    enviado = authorization[7:].strip()
    achado = None
    for cliente, token in _tokens.items():  # percorre todos: tempo constante por token
        if hmac.compare_digest(enviado.encode(), token.encode()):
            achado = cliente
    if achado is None:
        log.warning("token recusado")
        raise HTTPException(401, "token invalido", headers={"WWW-Authenticate": "Bearer"})
    return achado
