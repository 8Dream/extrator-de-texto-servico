import time, json, sys, requests
base = "http://sob-demanda:5001"
t = time.time()
r = requests.get(base + "/openapi.json", timeout=420)
print("LIGOU_EM_S", round(time.time() - t, 1), "http", r.status_code, flush=True)
spec = r.json()
print("TITULO", spec.get("info", {}).get("title"), spec.get("info", {}).get("version"))
for p, v in spec["paths"].items():
    if "convert" in p and "file" in p and "post" in v:
        print("ENDPOINT", p)
        corpo = v["post"].get("requestBody", {}).get("content", {})
        for tipo, d in corpo.items():
            ref = d.get("schema", {}).get("$ref", "")
            nome = ref.split("/")[-1]
            props = spec.get("components", {}).get("schemas", {}).get(nome, {}).get("properties", {})
            print("CAMPOS", tipo, [k for k in props if "ocr" in k or "format" in k or "pdf" in k or "table" in k][:25])
