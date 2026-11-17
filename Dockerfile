# Servico "Extrator de Texto" (transcricao na GPU da Spark).
# Base: a mesma imagem NGC que ja roda na Spark (PyTorch 2.14 + CUDA + transformers 5 + FastAPI), compartilha camadas.
FROM nvcr.io/nvidia/vllm:26.08-py3

ENV PYTHONUNBUFFERED=1 \
    HF_HOME=/modelos \
    EXTRATOR_DADOS=/dados

# ffmpeg: decodifica mp3, m4a, mp4, ogg, opus etc. (a base so traz libsndfile).
RUN apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv
COPY app /srv/app
EXPOSE 8110

ENTRYPOINT []
CMD ["python", "-m", "uvicorn", "app.principal:app", "--host", "0.0.0.0", "--port", "8110", "--no-access-log"]
