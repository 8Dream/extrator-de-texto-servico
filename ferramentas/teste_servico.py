"""Testes de comportamento do servico pela rede (so biblioteca padrao).
uso: EXTRATOR_TOKEN=... EXTRATOR_TOKEN2=... python teste_servico.py <url> <audio.wav> [parte]
TOKEN2 e o de OUTRO cliente (isolamento). Nenhum token e impresso."""
import json
import os
import sys
import time
import urllib.error
import urllib.request

BASE, AUDIO = sys.argv[1].rstrip("/"), sys.argv[2]
FASE = sys.argv[3] if len(sys.argv) > 3 else "basicos"
T1, T2 = os.environ["EXTRATOR_TOKEN"], os.environ.get("EXTRATOR_TOKEN2", "")
resultados = []


def req(caminho, metodo="GET", corpo=None, tipo="application/json", token=T1, timeout=120):
    r = urllib.request.Request(BASE + caminho, data=corpo, method=metodo)
    if token:
        r.add_header("Authorization", f"Bearer {token}")
    if corpo is not None:
        r.add_header("Content-Type", tipo)
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def j(b):
    try:
        return json.loads(b)
    except Exception:
        return {}


def ok(nome, cond, detalhe=""):
    resultados.append(cond)
    print(("PASSOU " if cond else "FALHOU ") + nome + (f"  [{detalhe}]" if detalhe else ""), flush=True)


def enviar(dados: bytes, nome="teste.wav"):
    st, b = req("/v1/arquivos", "POST", json.dumps({"nome": nome, "tamanho": len(dados)}).encode())
    arq = j(b)
    st, b = req(f"/v1/arquivos/{arq['id']}?deslocamento=0", "PUT", dados, "application/octet-stream")
    return arq["id"], st


def esperar(job_id, alvo=("concluida", "falhou", "cancelada"), teto=900, token=T1):
    t = time.time()
    while time.time() - t < teto:
        st, b = req(f"/v1/jobs/{job_id}", token=token)
        d = j(b)
        if d.get("estado") in alvo:
            return d
        time.sleep(0.3)
    return {"estado": "tempo_esgotado"}


def basicos():
    dados = open(AUDIO, "rb").read()
    # --- envio resumivel
    st, b = req("/v1/arquivos", "POST", json.dumps({"nome": "dialogo.wav", "tamanho": len(dados)}).encode())
    arq = j(b)
    parte = 8 * 2**20
    st, b = req(f"/v1/arquivos/{arq['id']}?deslocamento=0", "PUT", dados[:parte], "application/octet-stream")
    ok("envio: primeira parte aceita", st == 200 and j(b)["recebido"] == parte)
    st, b = req(f"/v1/arquivos/{arq['id']}?deslocamento=123", "PUT", dados[parte:2 * parte], "application/octet-stream")
    ok("envio: deslocamento errado -> 409 com onde retomar", st == 409 and j(b).get("recebido") == parte, f"http={st}")
    st, b = req("/v1/jobs", "POST", json.dumps({"arquivo_id": arq["id"]}).encode())
    ok("job com envio incompleto -> 409", st == 409, f"http={st}")
    st, b = req(f"/v1/arquivos/{arq['id']}", token=T2) if T2 else (404, b"")
    ok("isolamento: outro cliente nao enxerga o arquivo", st == 404, f"http={st}")
    pos = parte
    while pos < len(dados):
        st, b = req(f"/v1/arquivos/{arq['id']}?deslocamento={pos}", "PUT", dados[pos:pos + parte], "application/octet-stream")
        pos = j(b)["recebido"]
    st, b = req(f"/v1/arquivos/{arq['id']}")
    ok("envio: retomado e completo", j(b).get("completo") is True)
    # --- validacoes
    st, b = req("/v1/jobs", "POST", json.dumps({"arquivo_id": arq["id"], "parametros": {"modelo": "nao-existe"}}).encode())
    ok("modelo invalido -> 422", st == 422, f"http={st}")
    st, b = req("/v1/jobs", "POST", json.dumps({"arquivo_id": arq["id"], "parametros": {"idioma": "klingon"}}).encode())
    ok("idioma invalido -> 422", st == 422, f"http={st}")
    # --- job com diarizacao pedida e SSE
    st, b = req("/v1/jobs", "POST", json.dumps({"arquivo_id": arq["id"], "parametros": {"modelo": "small", "diarizar": {"ativar": True}}}).encode())
    job = j(b)
    ok("job criado (small, diarizar pedido)", st == 202, f"http={st}")
    r = urllib.request.Request(BASE + f"/v1/jobs/{job['id']}/eventos")
    r.add_header("Authorization", f"Bearer {T1}")
    eventos, ultimo = 0, {}
    with urllib.request.urlopen(r, timeout=300) as resp:
        for linha in resp:
            linha = linha.decode().strip()
            if linha.startswith("data: "):
                eventos += 1
                ultimo = json.loads(linha[6:])
    ok("SSE: recebeu eventos e terminou em concluida", eventos >= 3 and ultimo.get("estado") == "concluida", f"eventos={eventos} estado={ultimo.get('estado')}")
    ok("diarizacao pedida sem biblioteca -> aviso honesto, job concluiu", "diarizacao_indisponivel" in ultimo.get("avisos", []), str(ultimo.get("avisos")))
    st, b = req(f"/v1/jobs/{job['id']}", token=T2) if T2 else (404, b"")
    ok("isolamento: outro cliente nao enxerga o job", st == 404, f"http={st}")
    st, b = req(f"/v1/arquivos/{arq['id']}")
    ok("audio original apagado apos o job", st == 404, f"http={st}")
    for fmt, marca in (("txt", b""), ("srt", b"-->"), ("md", b"## Transcricao"), ("json", b'"full_text"')):
        st, b = req(f"/v1/jobs/{job['id']}/resultado?formato={fmt}")
        ok(f"resultado {fmt}", st == 200 and marca in b and len(b) > 500, f"{len(b)} bytes")
    st, b = req(f"/v1/jobs/{job['id']}/log")
    linhas = j(b).get("linhas", [])
    ok("log do job sem o texto da fala", linhas and not any("honorarios" in l.lower() or "embargos" in l.lower() for l in linhas), f"{len(linhas)} linhas")
    req(f"/v1/jobs/{job['id']}", "DELETE")
    st, b = req(f"/v1/jobs/{job['id']}")
    ok("DELETE remove o job", st == 404, f"http={st}")
    # --- arquivo que nao e audio: o job falha, o servico continua
    id_ruim, _ = enviar(os.urandom(300_000), "lixo.wav")
    st, b = req("/v1/jobs", "POST", json.dumps({"arquivo_id": id_ruim, "parametros": {"modelo": "small"}}).encode())
    d = esperar(j(b)["id"])
    ok("arquivo invalido -> job falhou com erro claro", d.get("estado") == "falhou" and bool(d.get("erro")), str(d.get("erro"))[:90])
    st, b = req("/saude", token=None)
    ok("servico segue saudavel depois da falha", st == 200)


def cancelamento():
    dados = open(AUDIO, "rb").read()
    arq_id, _ = enviar(dados)
    st, b = req("/v1/jobs", "POST", json.dumps({"arquivo_id": arq_id, "parametros": {"modelo": "large-v3"}}).encode())
    job = j(b)
    esperar(job["id"], alvo=("transcrevendo",), teto=120)
    time.sleep(3)
    st, b = req(f"/v1/jobs/{job['id']}/cancelar", "POST")
    d = esperar(job["id"], teto=120)
    ok("cancelamento no meio do trabalho", d.get("estado") == "cancelada", f"estado={d.get('estado')} progresso={d.get('progresso')}")
    st, b = req(f"/v1/arquivos/{arq_id}")
    ok("audio apagado depois de cancelar", st == 404)


def longo():
    """Job de varios minutos com a sessao do Sablier curta: o servico tem que se manter ligado ate o fim."""
    dados = open(AUDIO, "rb").read()
    arq_id, _ = enviar(dados)
    t0 = time.time()
    st, b = req("/v1/jobs", "POST", json.dumps({"arquivo_id": arq_id, "parametros": {"modelo": "large-v3"}}).encode())
    job = j(b)
    d = esperar(job["id"], teto=1200)
    ok("job longo terminou sem o Sablier desligar o servico", d.get("estado") == "concluida", f"estado={d.get('estado')} em {time.time() - t0:.0f} s, erro={d.get('erro')}")
    print("meta:", d.get("meta"))


def disparar():
    """Envia, cria o job e SAI sem acompanhar (simula o PC que dorme): so imprime o id do job."""
    arq_id, _ = enviar(open(AUDIO, "rb").read()) if os.path.getsize(AUDIO) < 60 * 2**20 else enviar_grande()
    st, b = req("/v1/jobs", "POST", json.dumps({"arquivo_id": arq_id, "parametros": {"modelo": "large-v3"}}).encode())
    print("JOB", j(b).get("id"))
    resultados.append(st == 202)


def enviar_grande():
    tamanho = os.path.getsize(AUDIO)
    st, b = req("/v1/arquivos", "POST", json.dumps({"nome": "longo.wav", "tamanho": tamanho}).encode())
    arq = j(b)
    pos = 0
    with open(AUDIO, "rb") as f:
        while pos < tamanho:
            f.seek(pos)
            st, b = req(f"/v1/arquivos/{arq['id']}?deslocamento={pos}", "PUT", f.read(8 * 2**20), "application/octet-stream", timeout=300)
            pos = j(b)["recebido"]
    return arq["id"], st


{"basicos": basicos, "cancelamento": cancelamento, "longo": longo, "disparar": disparar}[FASE]()
print(f"\n{sum(resultados)} de {len(resultados)} verificacoes passaram")
sys.exit(0 if all(resultados) else 1)
