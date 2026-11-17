"""Fila de jobs: estado, progresso real, ETA, log (sem o texto da fala) e UM trabalhador de GPU por vez."""
import json
import logging
import queue
import re
import threading
import time
import urllib.request
import uuid
from dataclasses import dataclass, field
from datetime import datetime

from . import armazenamento, config, diarizacao, formatos, motor_gpu

log = logging.getLogger("extrator.jobs")
ATIVOS = ("na_fila", "preparando", "transcrevendo", "diarizando", "finalizando")


@dataclass
class Job:
    id: str
    cliente: str
    arquivo_id: str
    nome: str
    parametros: dict
    estado: str = "na_fila"
    etapa: str = "na fila"
    atual: float = 0.0
    total: float | None = None
    unidade: str = "s"
    eta_s: float | None = None
    criado_em: float = field(default_factory=time.time)
    iniciado_em: float | None = None
    concluido_em: float | None = None
    erro: str | None = None
    avisos: list = field(default_factory=list)
    meta: dict = field(default_factory=dict)
    linhas: list = field(default_factory=list)
    cancelar: threading.Event = field(default_factory=threading.Event, repr=False)
    _taxa: float | None = field(default=None, repr=False)
    _ultimo: tuple | None = field(default=None, repr=False)

    def registrar(self, msg: str) -> None:
        """Log do job: tempos e contagens. NUNCA o texto transcrito (audio confidencial)."""
        linha = f"{datetime.now().strftime('%H:%M:%S')} {msg}"
        self.linhas.append(linha)
        log.info(json.dumps({"job": self.id, "msg": msg}))

    def publico(self) -> dict:
        pct = None
        if self.total and self.total > 0:
            pct = round(min(self.atual / self.total, 1.0), 4)
        return {
            "id": self.id, "estado": self.estado, "etapa": self.etapa, "origem": "spark",
            "progresso": pct, "atual": round(self.atual, 1), "total": round(self.total, 1) if self.total else None,
            "unidade": self.unidade, "eta_s": round(self.eta_s) if self.eta_s is not None else None,
            "criado_em": self.criado_em, "iniciado_em": self.iniciado_em, "concluido_em": self.concluido_em,
            "erro": self.erro, "avisos": self.avisos, "meta": self.meta, "nome": self.nome,
            "parametros": self.parametros, "linhas_log": len(self.linhas),
        }


class Gerenciador:
    def __init__(self) -> None:
        self.jobs: dict[str, Job] = {}
        self.fila: queue.Queue = queue.Queue()
        self.hist: dict = {}
        self._trava = threading.Lock()

    # ---------- ciclo de vida ----------
    def iniciar(self) -> None:
        try:
            self.hist = json.loads(config.HISTORICO.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            self.hist = {}
        self._recarregar_jobs_antigos()
        for alvo in (self._trabalhador, self._manutencao, self._manter_sessao):
            threading.Thread(target=alvo, daemon=True, name=alvo.__name__).start()

    def _recarregar_jobs_antigos(self) -> None:
        """Jobs concluidos de antes do reinicio continuam consultaveis; os que estavam rodando viram 'interrompida'."""
        for pasta in config.JOBS.glob("*"):
            try:
                d = json.loads((pasta / "job.json").read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            estado = d.get("estado")
            if estado in ATIVOS:
                estado, d["erro"] = "falhou", "interrompido: o servico reiniciou durante o trabalho"
            j = Job(id=d["id"], cliente=d["cliente"], arquivo_id=d.get("arquivo_id", ""), nome=d.get("nome", ""),
                    parametros=d.get("parametros", {}), estado=estado, etapa=d.get("etapa", ""),
                    atual=d.get("atual", 0), total=d.get("total"), criado_em=d.get("criado_em", time.time()),
                    iniciado_em=d.get("iniciado_em"), concluido_em=d.get("concluido_em"), erro=d.get("erro"),
                    avisos=d.get("avisos", []), meta=d.get("meta", {}))
            try:
                j.linhas = (pasta / "log.txt").read_text(encoding="utf-8").splitlines()
            except OSError:
                pass
            self.jobs[j.id] = j

    # ---------- API interna ----------
    def criar(self, cliente: str, arquivo_id: str, nome: str, parametros: dict) -> Job:
        job = Job(id=uuid.uuid4().hex[:16], cliente=cliente, arquivo_id=arquivo_id, nome=nome, parametros=parametros)
        (config.JOBS / job.id).mkdir(parents=True, exist_ok=True)
        with self._trava:
            self.jobs[job.id] = job
        job.registrar(f"job criado (modelo={parametros['modelo']}, idioma={parametros['idioma']})")
        self._salvar(job)
        self.fila.put(job.id)
        return job

    def obter(self, job_id: str, cliente: str) -> Job | None:
        j = self.jobs.get(job_id)
        return j if j and j.cliente == cliente else None

    def listar(self, cliente: str) -> list[Job]:
        return sorted((j for j in self.jobs.values() if j.cliente == cliente), key=lambda j: j.criado_em, reverse=True)

    def ativos(self) -> int:
        return sum(1 for j in self.jobs.values() if j.estado in ATIVOS)

    def apagar(self, job: Job) -> None:
        import shutil
        job.cancelar.set()
        self.jobs.pop(job.id, None)
        shutil.rmtree(config.JOBS / job.id, ignore_errors=True)
        armazenamento.apagar(job.arquivo_id)

    # ---------- persistencia ----------
    def _salvar(self, job: Job) -> None:
        d = job.publico()
        d.update({"cliente": job.cliente, "arquivo_id": job.arquivo_id})
        pasta = config.JOBS / job.id
        pasta.mkdir(parents=True, exist_ok=True)
        tmp = pasta / "job.json.tmp"
        tmp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        tmp.replace(pasta / "job.json")
        (pasta / "log.txt").write_text("\n".join(job.linhas), encoding="utf-8")

    # ---------- progresso e ETA ----------
    def _progresso(self, job: Job, atual: float, total: float) -> None:
        agora = time.monotonic()
        job.atual, job.total = atual, total
        if job._ultimo is not None:
            t_ant, a_ant = job._ultimo
            if agora > t_ant and atual > a_ant:
                inst = (atual - a_ant) / (agora - t_ant)  # segundos de audio por segundo
                job._taxa = inst if job._taxa is None else 0.7 * job._taxa + 0.3 * inst
        job._ultimo = (agora, atual)
        hist = self.hist.get(job.parametros["modelo"], {}).get("x_tempo_real")
        restante = max(total - atual, 0.0)
        if job._taxa:
            eta = restante / job._taxa
            if hist and total > 0 and atual / total < 0.2:  # no comeco, pesa o historico
                eta = 0.5 * eta + 0.5 * (restante / hist)
            job.eta_s = eta
        elif hist:
            job.eta_s = restante / hist
        else:
            job.eta_s = None  # "estimando..."

    def _gravar_historico(self, job: Job, segundos_proc: float) -> None:
        dur = job.meta.get("duracao_s") or 0
        if dur < 20 or segundos_proc <= 0:
            return
        x = dur / segundos_proc
        m = job.parametros["modelo"]
        antigo = self.hist.get(m, {}).get("x_tempo_real")
        self.hist[m] = {"x_tempo_real": round(x if antigo is None else 0.6 * antigo + 0.4 * x, 2), "execucoes": self.hist.get(m, {}).get("execucoes", 0) + 1}
        try:
            tmp = config.HISTORICO.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.hist), encoding="utf-8")
            tmp.replace(config.HISTORICO)
        except OSError:
            pass

    # ---------- trabalhador ----------
    def _trabalhador(self) -> None:
        while True:
            job_id = self.fila.get()
            job = self.jobs.get(job_id)
            if job is None or job.cancelar.is_set():
                if job is not None and job.estado == "na_fila":
                    job.estado, job.etapa, job.concluido_em = "cancelada", "cancelada antes de começar", time.time()
                    self._salvar(job)
                continue
            try:
                self._executar(job)
            except motor_gpu.Cancelado:
                job.estado, job.etapa = "cancelada", "cancelada"
                job.registrar("cancelado pelo cliente")
            except Exception as exc:  # o job falha, o servico continua
                # sem caminhos internos do servidor na mensagem devolvida ao cliente
                msg = re.sub(r"/dados/\S+|/modelos/\S+|/srv/\S+", "<arquivo>", str(exc))[:300]
                job.estado, job.etapa, job.erro = "falhou", "falhou", f"{type(exc).__name__}: {msg}"
                job.registrar(f"falhou: {job.erro}")
            finally:
                job.concluido_em = time.time()
                armazenamento.apagar(job.arquivo_id)  # o audio nao fica guardado
                job.registrar("audio original apagado do servidor")
                self._salvar(job)

    def _executar(self, job: Job) -> None:
        p = job.parametros
        job.estado, job.iniciado_em = "preparando", time.time()
        self._salvar(job)
        caminho = armazenamento.caminho(job.arquivo_id)
        if not caminho.is_file():
            raise FileNotFoundError("arquivo enviado nao encontrado")

        def etapa(txt: str) -> None:
            job.etapa = txt
            if txt == "transcrevendo":
                job.estado = "transcrevendo"
            job.registrar(f"etapa: {txt}")

        t0 = time.time()
        segs, meta = motor_gpu.transcrever(
            str(caminho), config.MODELOS[p["modelo"]], p["idioma"], config.lote_para(p["modelo"]), job.cancelar, etapa,
            lambda a, t: self._progresso(job, a, t))
        proc = time.time() - t0
        job.meta.update(meta)
        job.meta.update({"modelo": p["modelo"], "segmentos": len(segs), "segundos_processamento": round(proc, 1)})
        job.registrar(f"transcricao concluida: {len(segs)} segmentos em {proc:.1f} s")

        d = p.get("diarizar") or {}
        if d.get("ativar"):
            if diarizacao.disponivel():
                job.estado, job.etapa = "diarizando", "identificando interlocutores"
                job.registrar("etapa: diarizacao")
                import numpy as np  # noqa: F401
                audio = motor_gpu.decodificar(str(caminho))
                turnos = diarizacao.REGISTRO["padrao"].diarizar(audio, motor_gpu.SR, d.get("min"), d.get("max"), lambda f: None)
                presentes = diarizacao.atribuir(segs, turnos)
                job.meta["interlocutores"] = presentes
                job.meta["resumo_interlocutores"] = diarizacao.resumo(segs)
            else:
                job.avisos.append("diarizacao_indisponivel")
                job.registrar("aviso: identificacao de interlocutores indisponivel neste servidor (sem biblioteca registrada)")

        job.estado, job.etapa = "finalizando", "gravando resultados"
        pasta = config.JOBS / job.id
        (pasta / "segmentos.json").write_text(json.dumps(
            {"meta": job.meta, "segmentos": [{"inicio": s.start, "fim": s.end, "texto": s.text, "interlocutor": s.interlocutor} for s in segs]},
            ensure_ascii=False), encoding="utf-8")
        self._gravar_historico(job, proc)
        job.estado, job.etapa, job.eta_s = "concluida", "concluida", 0.0
        job.atual = job.total or job.atual

    def resultado(self, job: Job, formato: str, nomes: dict | None = None) -> tuple[str, str]:
        d = json.loads((config.JOBS / job.id / "segmentos.json").read_text(encoding="utf-8"))
        segs = [formatos.Seg(s["inicio"], s["fim"], s["texto"], None, s.get("interlocutor")) for s in d["segmentos"]]
        meta = dict(d["meta"])
        stem = job.nome.rsplit(".", 1)[0] if "." in job.nome else job.nome
        meta.update({"titulo": stem, "nome_arquivo": job.nome, "idioma_detectado": job.parametros["idioma"]})
        if formato == "txt":
            return formatos.txt(segs, nomes), "text/plain; charset=utf-8"
        if formato == "srt":
            return formatos.srt(segs, nomes), "text/plain; charset=utf-8"
        if formato == "md":
            return formatos.md(segs, meta, nomes), "text/markdown; charset=utf-8"
        extra = {"meta": meta, "avisos": job.avisos}
        return formatos.json_(segs, extra, nomes), "application/json"

    # ---------- manutencao e sessao do Sablier ----------
    def _manutencao(self) -> None:
        ev = threading.Event()
        while not ev.wait(300):
            armazenamento.limpar_antigos()
            vivos = {p.name for p in config.JOBS.glob("*")}
            for jid in [k for k in self.jobs if k not in vivos]:
                self.jobs.pop(jid, None)
            motor_gpu.descarregar_se_ocioso()

    def _manter_sessao(self) -> None:
        """Enquanto houver trabalho, renova a sessao do Sablier para ele nao desligar o servico no meio."""
        ev = threading.Event()
        url = f"{config.SABLIER_URL}/api/strategies/blocking?names={config.SABLIER_NOME}&session_duration={config.SABLIER_SESSAO}&timeout=10s"
        while not ev.wait(30):
            if self.ativos() == 0:
                continue
            try:
                urllib.request.urlopen(url, timeout=15).read()
            except Exception as exc:
                log.info(json.dumps({"evento": "sablier_indisponivel", "erro": str(exc)[:120]}))


GER = Gerenciador()
