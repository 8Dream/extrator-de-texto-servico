import time, sys, requests
base = "http://sob-demanda:5001"
pdf = open("/teste/escaneado.pdf", "rb").read()
def converter(rotulo, dados):
    t = time.time()
    r = requests.post(base + "/v1/convert/file", files={"files": ("escaneado.pdf", pdf, "application/pdf")}, data=dados, timeout=900)
    dt = time.time() - t
    if r.status_code != 200:
        print("DOCLING", rotulo, "http", r.status_code, r.text[:300]); return
    d = r.json()
    md = (d.get("document", {}) or {}).get("md_content") or ""
    open(f"/teste/docling_{rotulo}.md", "w", encoding="utf-8").write(md)
    print("DOCLING", rotulo, f"{dt:.1f}s", f"{dt/8:.1f}s/pagina", "chars", len(md), "status", d.get("status"), flush=True)
base_d = {"to_formats": "md", "do_ocr": "true", "force_ocr": "true", "do_table_structure": "false"}
converter("padrao_1a", dict(base_d))
converter("padrao_2a", dict(base_d))
converter("tesseract_por", dict(base_d, ocr_engine="tesseract", ocr_lang="por"))
