import sys, time, json, os, resource
import numpy as np, soundfile as sf, torch
from transformers import pipeline
wav, modelo, segundos = sys.argv[1], sys.argv[2], float(sys.argv[3])
batch = int(sys.argv[4]) if len(sys.argv) > 4 else 16
audio, sr = sf.read(wav, dtype="float32")
audio = audio[: int(segundos * sr)]
t0 = time.time()
pipe = pipeline("automatic-speech-recognition", model=modelo, dtype=torch.float16, device="cuda:0")
torch.cuda.synchronize(); t1 = time.time()
gk = {"language": "portuguese", "task": "transcribe"}
pipe({"raw": audio[: 16000 * 30], "sampling_rate": sr}, chunk_length_s=30, batch_size=batch, generate_kwargs=gk)
torch.cuda.synchronize(); t2 = time.time()
out = pipe({"raw": audio, "sampling_rate": sr}, chunk_length_s=30, batch_size=batch, return_timestamps=True, generate_kwargs=gk)
torch.cuda.synchronize(); t3 = time.time()
dur = len(audio) / sr
r = {"modelo": modelo, "audio_s": round(dur, 1), "batch": batch, "carregar_s": round(t1 - t0, 1), "aquecer_s": round(t2 - t1, 1),
     "transcrever_s": round(t3 - t2, 1), "rtf": round((t3 - t2) / dur, 3), "x_tempo_real": round(dur / (t3 - t2), 1),
     "gpu_pico_gb": round(torch.cuda.max_memory_allocated() / 2**30, 2), "rss_pico_gb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 2**20, 2)}
nome = modelo.split("/")[-1]
open(f"/teste/gpu_{nome}_{int(dur)}s.txt", "w", encoding="utf-8").write(out["text"].strip())
print("RESULTADO " + json.dumps(r))
