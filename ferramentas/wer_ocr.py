import re, sys, unicodedata
def norm(t):
    t = unicodedata.normalize("NFKD", t.lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.findall(r"[a-z0-9]+", t)
ref = norm(open(sys.argv[1], encoding="utf-8").read()); m = len(ref)
for arq in sys.argv[2:]:
    hip = norm(open(arq, encoding="utf-8").read())
    prev = list(range(m + 1))
    for i, x in enumerate(hip, 1):
        cur = [i] + [0] * m
        for j in range(1, m + 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (x != ref[j - 1]))
        prev = cur
    d = min(prev)
    print(f"{arq.split('/')[-1]:24s} palavras_hip={len(hip):5d} ref={m:5d} erros={d:4d} WER~{d / m * 100:5.1f}%")
