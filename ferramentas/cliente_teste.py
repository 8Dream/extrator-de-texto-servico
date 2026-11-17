"""Cliente de teste do servico (so biblioteca padrao). Mostra o que o programa do Windows vai fazer.

uso: python cliente_teste.py <url> <arquivo_de_audio> [modelo] [idioma]
O token vem da variavel EXTRATOR_TOKEN (nunca como argumento, para nao ficar no historico do terminal)."""
import json
import os
import sys
import time
import urllib.error
import urllib.request

PARTE = 8 * 2**20


def req(url, metodo="GET", corpo=None, tipo="application/json", token=None, timeout=600):
    r = urllib.request.Request(url, data=corpo, method=metodo)
    if token:
        r.add_header("Authorization", f"Bearer {token}")
    if corpo is not None:
        r.add_header("Content-Type", tipo)
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def main():
    base, arq = sys.argv[1].rstrip("/"), sys.argv[2]
    modelo = sys.argv[3] if len(sys.argv) > 3 else None
    idioma = sys.argv[4] if len(sys.argv) > 4 else "pt"
    token = os.environ.get("EXTRATOR_TOKEN", "")
    t_ini = time.time()

    t = time.time()
    st, corpo = req(base + "/saude", timeout=360)  # espera o Sablier ligar o servico
    print(f"[saude] http={st} em {time.time() - t:.1f} s (liga a frio incluso) {corpo.decode()[:80]}")

    st, corpo = req(base + "/v1/info", token=token)
    print(f"[info] http={st}")
    if st != 200:
        print(corpo.decode()[:200])
        return 1
    info = json.loads(corpo)
    print("   modelos:", info["modelos"], "| gpu:", info["gpu"], "| diarizacao:", info["diarizacao_disponivel"])

    tamanho = os.path.getsize(arq)
    st, corpo = req(base + "/v1/arquivos", "POST", json.dumps({"nome": os.path.basename(arq), "tamanho": tamanho}).encode(), token=token)
    arquivo = json.loads(corpo)
    t = time.time()
    recebido = 0
    with open(arq, "rb") as f:
        while recebido < tamanho:
            f.seek(recebido)
            pedaco = f.read(PARTE)
            st, corpo = req(f"{base}/v1/arquivos/{arquivo['id']}?deslocamento={recebido}", "PUT", pedaco, "application/octet-stream", token)
            if st == 409:  # retoma de onde o servidor parou
                recebido = json.loads(corpo)["recebido"]
                continue
            recebido = json.loads(corpo)["recebido"]
    up = time.time() - t
    print(f"[envio] {tamanho / 2**20:.1f} MB em {up:.1f} s = {tamanho * 8 / up / 1e6:.0f} Mbit/s")

    params = {"idioma": idioma}
    if modelo:
        params["modelo"] = modelo
    st, corpo = req(base + "/v1/jobs", "POST", json.dumps({"arquivo_id": arquivo["id"], "parametros": params}).encode(), token=token)
    job = json.loads(corpo)
    print(f"[job] http={st} id={job.get('id')}")
    t_job = time.time()
    visto = ""
    while True:
        st, corpo = req(f"{base}/v1/jobs/{job['id']}", token=token)
        j = json.loads(corpo)
        linha = f"{j['estado']:14s} {j['etapa']:28s} progresso={j['progresso']} eta_s={j['eta_s']}"
        if linha != visto:
            print("  ", f"{time.time() - t_job:6.1f}s", linha)
            visto = linha
        if j["estado"] in ("concluida", "falhou", "cancelada"):
            break
        time.sleep(0.5)
    proc = time.time() - t_job
    if j["estado"] != "concluida":
        print("ERRO:", j.get("erro"))
        return 2
    print(f"[processamento] {proc:.1f} s para {j['meta'].get('duracao_s')} s de audio -> {j['meta'].get('duracao_s') / proc:.1f}x tempo real")

    saida = os.path.splitext(arq)[0]
    for fmt in ("txt", "md", "srt", "json"):
        st, corpo = req(f"{base}/v1/jobs/{job['id']}/resultado?formato={fmt}", token=token)
        open(f"{saida}.servico.{fmt}", "wb").write(corpo)
        print(f"[resultado] {fmt}: http={st} {len(corpo)} bytes")
    st, corpo = req(f"{base}/v1/jobs/{job['id']}/log", token=token)
    print("[log do job]", *json.loads(corpo)["linhas"][-6:], sep="\n   ")
    req(f"{base}/v1/jobs/{job['id']}", "DELETE", token=token)
    print(f"[total ponta a ponta] {time.time() - t_ini:.1f} s (envio {up:.1f} s + processamento {proc:.1f} s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
