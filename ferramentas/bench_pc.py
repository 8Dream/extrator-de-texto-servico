import sys, time, json, soundfile as sf, numpy as np, os
wav, modelo, segundos, saida = sys.argv[1], sys.argv[2], float(sys.argv[3]), sys.argv[4]
dados, sr = sf.read(wav, dtype="float32")
dados = dados[: int(segundos * sr)]
from faster_whisper import WhisperModel
t0 = time.time()
m = WhisperModel(modelo, device="cpu", compute_type="float32", download_root=os.path.join(os.path.dirname(wav), "modelos_pc"))
t1 = time.time()
segs, info = m.transcribe(dados, language="pt", beam_size=5, vad_filter=True)
texto = " ".join(s.text.strip() for s in segs)
t2 = time.time()
r = {"modelo": modelo, "audio_s": round(len(dados)/sr,1), "carregar_s": round(t1-t0,1), "transcrever_s": round(t2-t1,1), "rtf": round((t2-t1)/(len(dados)/sr),2)}
open(saida, "w", encoding="utf-8").write(texto)
print(json.dumps(r))
