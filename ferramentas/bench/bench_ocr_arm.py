import sys, time, io, subprocess
from multiprocessing import Pool
import pymupdf
def ocr(args):
    i, png = args
    t = time.time()
    r = subprocess.run(["tesseract", "stdin", "stdout", "-l", "por"], input=png, capture_output=True)
    return i, time.time() - t, r.stdout.decode("utf-8", "replace")
if __name__ == "__main__":
    pdf, dpi, procs = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
    doc = pymupdf.open(pdf)
    pngs = [(i, p.get_pixmap(dpi=dpi).tobytes("png")) for i, p in enumerate(doc)]
    t0 = time.time()
    with Pool(procs) as pool:
        res = sorted(pool.map(ocr, pngs))
    tot = time.time() - t0
    por_pagina = [round(t, 1) for _, t, _ in res]
    open("/teste/ocr_arm.txt", "w").write("\n".join(r for *_, r in res))
    print(f"TESSERACT_ARM paginas={len(res)} dpi={dpi} processos={procs} total={tot:.1f}s ({tot/len(res):.1f}s/pagina efetivo) tempo_por_pagina_1_nucleo={por_pagina}")
