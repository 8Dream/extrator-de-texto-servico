"""PONTO DE EXTENSAO da identificacao de interlocutores.

A biblioteca definitiva sai da pesquisa feita a parte. Para plugar uma, basta implementar `diarizar` e
registrar em REGISTRO["padrao"]. Enquanto nao houver nenhuma, o job termina normalmente e avisa
"diarizacao_indisponivel" (nada e inventado)."""
from typing import Callable, Protocol

import numpy as np

from .formatos import Seg

Turno = tuple[float, float, int]  # (inicio_s, fim_s, interlocutor 1..N)


class Diarizador(Protocol):
    nome: str

    def diarizar(self, audio: np.ndarray, sr: int, minimo: int | None, maximo: int | None,
                 progresso: Callable[[float], None]) -> list[Turno]: ...


REGISTRO: dict[str, Diarizador] = {}


def disponivel() -> bool:
    return "padrao" in REGISTRO


def atribuir(segs: list[Seg], turnos: list[Turno]) -> list[int]:
    """Atribui a cada segmento o interlocutor de MAIOR sobreposicao. Devolve os interlocutores presentes."""
    presentes: set[int] = set()
    for s in segs:
        melhor, melhor_ov = None, 0.0
        for ini, fim, quem in turnos:
            ov = min(s.end, fim) - max(s.start, ini)
            if ov > melhor_ov:
                melhor, melhor_ov = quem, ov
        s.interlocutor = melhor
        if melhor is not None:
            presentes.add(melhor)
    return sorted(presentes)


def resumo(segs: list[Seg]) -> dict:
    """Quantidade de interlocutores, tempo de fala de cada um e numero de trocas de turno."""
    fala: dict[int, float] = {}
    trocas, anterior = 0, None
    for s in segs:
        if s.interlocutor is None:
            continue
        fala[s.interlocutor] = fala.get(s.interlocutor, 0.0) + max(0.0, s.end - s.start)
        if anterior is not None and s.interlocutor != anterior:
            trocas += 1
        anterior = s.interlocutor
    return {"quantidade": len(fala), "tempo_fala_s": {str(k): round(v, 1) for k, v in sorted(fala.items())}, "trocas": trocas}
