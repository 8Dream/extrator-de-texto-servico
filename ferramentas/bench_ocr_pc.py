import sys, time, fitz, pytesseract, io, os
from PIL import Image
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
os.environ["TESSDATA_PREFIX"] = r"C:\Users\rafae\AppData\Local\Programs\ExtratorDeTexto\dados\tessdata"
doc = fitz.open(sys.argv[1]); dpi = int(sys.argv[2]); t0 = time.time(); textos = []
for i, pg in enumerate(doc):
    pix = pg.get_pixmap(dpi=dpi); img = Image.open(io.BytesIO(pix.tobytes("png")))
    ts = time.time(); textos.append(pytesseract.image_to_string(img, lang="por")); print(f"pagina {i+1}: {time.time()-ts:.1f}s", flush=True)
tot = time.time() - t0
open(sys.argv[3], "w", encoding="utf-8").write("\n".join(textos))
print(f"TOTAL {tot:.1f}s para {len(doc)} paginas = {tot/len(doc):.1f}s/pagina a {dpi} dpi")
