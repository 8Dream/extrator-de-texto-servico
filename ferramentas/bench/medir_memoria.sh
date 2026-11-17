#!/bin/bash
# uso: medir_memoria.sh <modelo> <segundos> <lote>   (mede a memoria disponivel do host durante o benchmark)
cd ~/EtherLake/extrator-servico
M=$1; SEG=$2; B=$3
LOG=teste/mem_$(basename $M)_b$B.log; : > $LOG
base=$(awk "/MemAvailable/ {print int(\$2/1024)}" /proc/meminfo)
( while :; do awk "/MemAvailable/ {printf \"%d\n\", \$2/1024}" /proc/meminfo >> $LOG; sleep 0.5; done ) &
SP=$!
timeout 900 docker run --rm --gpus all --memory 20g --cpus 8 -e HF_HOME=/modelos -v $PWD/modelos:/modelos -v $PWD/teste:/teste -v $PWD/app:/app --entrypoint python nvcr.io/nvidia/vllm:26.08-py3 /app/bench_gpu.py /teste/dialogo.wav $M $SEG $B 2>&1 | grep RESULTADO
kill $SP 2>/dev/null
min=$(sort -n $LOG | head -1)
echo "MEMORIA modelo=$M lote=$B disponivel_antes_MB=$base disponivel_minimo_MB=$min queda_MB=$((base-min))"
