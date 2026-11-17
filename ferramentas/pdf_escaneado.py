import re, sys, random, io
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import fitz
ps1 = open(sys.argv[1], encoding="utf-8-sig").read()
frases = re.findall(r'@\("[^"]+","([^"]+)"\)', ps1)
random.seed(7)
fonte = ImageFont.truetype(r"C:\Windows\Fonts\times.ttf", 30)
W, H = 1240, 1754   # A4 a 150 dpi
doc = fitz.open()
n_paginas, k = 8, 0
for p in range(n_paginas):
    img = Image.new("L", (W, H), 255)
    d = ImageDraw.Draw(img)
    y = 140
    d.text((120, 70), f"PROCESSO Nº 0012345-67.2026.8.26.0100 - FL. {p+1}", font=fonte, fill=0)
    while y < H - 160:
        texto = frases[k % len(frases)]; k += 1
        linha, linhas = "", []
        for pal in texto.split():
            teste = (linha + " " + pal).strip()
            if d.textlength(teste, font=fonte) > W - 240:
                linhas.append(linha); linha = pal
            else:
                linha = teste
        linhas.append(linha)
        for l in linhas:
            d.text((120, y), l, font=fonte, fill=0); y += 44
        y += 28
    img = img.rotate(random.uniform(-0.6, 0.6), expand=False, fillcolor=255).filter(ImageFilter.GaussianBlur(0.7))
    buf = io.BytesIO(); img.save(buf, "JPEG", quality=70)
    page = doc.new_page(width=595, height=842)
    page.insert_image(page.rect, stream=buf.getvalue())
doc.save(sys.argv[2]); print("paginas", len(doc), "tamanho_kb", round(len(open(sys.argv[2],'rb').read())/1024))
