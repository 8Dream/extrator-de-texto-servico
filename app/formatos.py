"""Saidas no MESMO formato do programa (src/transcricao_core.py): txt, md, srt, json.
Com interlocutores, o rotulo entra em cada trecho; sem diarizacao, a saida e identica a do programa."""
import json
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Seg:
    start: float
    end: float
    text: str
    avg_logprob: float | None = None
    interlocutor: int | None = None  # 1, 2, 3... (preenchido pela diarizacao)
    words: list = field(default_factory=list)


def hhmmss(segundos: float) -> str:
    s = int(segundos)
    return f"{s // 3600:02d}:{(s % 3600) // 60:02d}:{s % 60:02d}"


def _srt_time(segundos: float) -> str:
    h = int(segundos // 3600)
    m = int((segundos % 3600) // 60)
    s = int(segundos % 60)
    ms = int(round((segundos % 1) * 1000))
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _rotulo(seg: Seg, nomes: dict | None) -> str:
    if seg.interlocutor is None:
        return ""
    nome = (nomes or {}).get(str(seg.interlocutor)) or f"Interlocutor {seg.interlocutor}"
    return f"{nome}: "


def txt(segs: list[Seg], nomes: dict | None = None) -> str:
    return "\n".join(_rotulo(s, nomes) + s.text.strip() for s in segs if s.text.strip())


def srt(segs: list[Seg], nomes: dict | None = None) -> str:
    linhas = []
    for i, s in enumerate(segs, 1):
        t = s.text.strip()
        if not t:
            continue
        linhas.append(f"{i}\n{_srt_time(s.start)} --> {_srt_time(s.end)}\n{_rotulo(s, nomes)}{t}\n")
    return "\n".join(linhas)


def json_(segs: list[Seg], extra: dict | None = None, nomes: dict | None = None) -> str:
    data = {"segments": [], "full_text": " ".join(s.text.strip() for s in segs if s.text.strip())}
    for s in segs:
        e = {"start": round(s.start, 3), "end": round(s.end, 3), "text": s.text.strip(),
             "confidence": round(s.avg_logprob, 3) if s.avg_logprob is not None else None}
        if s.interlocutor is not None:
            e["interlocutor"] = s.interlocutor
        data["segments"].append(e)
    if extra:
        data.update(extra)
    return json.dumps(data, ensure_ascii=False, indent=2)


def md(segs: list[Seg], meta: dict, nomes: dict | None = None) -> str:
    linhas = [f"# {meta.get('titulo', 'Transcricao')}", ""]
    linhas.append(f"- Arquivo de origem: `{meta.get('nome_arquivo', '')}`")
    if meta.get("idioma_detectado"):
        linhas.append(f"- Idioma: {meta['idioma_detectado']}")
    if meta.get("duracao_s") is not None:
        linhas.append(f"- Duracao: {hhmmss(meta['duracao_s'])}")
    if meta.get("modelo"):
        linhas.append(f"- Modelo: {meta['modelo']}")
    if meta.get("interlocutores"):
        linhas.append(f"- Interlocutores: {len(meta['interlocutores'])}")
    linhas.append(f"- Gerado em: {meta.get('gerado_em', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))}")
    linhas += ["", "## Transcricao", ""]
    for s in segs:
        t = s.text.strip()
        if not t:
            continue
        linhas.append(f"**[{hhmmss(s.start)} - {hhmmss(s.end)}]** {_rotulo(s, nomes)}{t}")
        linhas.append("")
    return "\n".join(linhas).rstrip() + "\n"
