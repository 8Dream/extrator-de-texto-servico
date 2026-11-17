#!/bin/bash
# Mede a latencia de uma resposta minima do vLLM utilitario (porta 8003) a cada ~1 s ate existir o arquivo de parada.
M=$(curl -s --max-time 5 http://100.91.153.82:8003/v1/models | python3 -c "import sys,json;print(json.load(sys.stdin)[\"data\"][0][\"id\"])")
: > "$1"
while [ ! -f "$2" ]; do
  t=$(curl -s -o /dev/null -w "%{time_total}" --max-time 30 -H "Content-Type: application/json" -d "{\"model\":\"$M\",\"prompt\":\"Diga ok.\",\"max_tokens\":6,\"temperature\":0}" http://100.91.153.82:8003/v1/completions)
  echo "$(date +%s) $t" >> "$1"
  sleep 1
done
