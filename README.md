# Extrator de Texto - serviço (Spark)

Serviço self-hosted que transcreve áudio e vídeo na GPU da Spark (Whisper, modelos abertos) para o programa
**Extrator de Texto** do Windows. É um **motor remoto opcional**: o programa continua funcionando sozinho, offline.
Roda como os outros serviços sob demanda da Spark (Sablier): o contêiner de GPU só existe quando alguém chama
e desliga sozinho depois de 15 min ocioso.

- Projeto: `pessoal/extrator-de-texto-servico` (GitLab da Spark). Pasta na Spark: `~/EtherLake/extrator-servico`.
- Endereço: `http://100.91.153.82:8110` (só na tailnet; autenticação por token em tudo, menos `/saude`).
- Áudio confidencial: nada sai da Spark. O áudio original é apagado assim que o job termina; resultados ficam
  24 h (ou até o cliente dar `DELETE`). Os logs não contêm o texto falado.

## Origem do fork

Este fork adapta o [Extrator de Texto](https://github.com/8Dream/extrator-de-texto) para operar como uma API na Spark. A branch `main` deste projeto conserva o Compose e a API na raiz para manter a mesma estrutura do ambiente em uso. O aplicativo para Windows continua no projeto original e seu histórico pode ser consultado pelo segundo pai do commit que uniu os dois projetos. A integração do aplicativo com a API está descrita em [Integração com o programa](docs/INTEGRACAO-PROGRAMA.md).

## Como funciona

```
PC (Windows) ──Tailscale──> extrator-gateway :8110 (Caddy + Sablier, sempre ligado, 128 MB)
                               └─ liga/espera ─> extrator-servico (FastAPI + PyTorch, GPU, sob demanda)
```

- **Gateway** (`sob-demanda-caddy` com o plugin do Sablier): a primeira chamada (`GET /saude`) espera o contêiner ligar
  (~7 s) e renova a sessão a cada pedido. Quem chama deve fazer `/saude` primeiro e só depois enviar o arquivo.
- **Serviço**: um trabalhador de GPU por vez (fila), áudio cortado nos silêncios em janelas de ~28 s e
  transcrito em lotes; o progresso é real (segundos de áudio processados) e o ETA usa o ritmo observado
  mais o histórico por modelo. Enquanto há job, o serviço renova a própria sessão do Sablier (o PC pode dormir
  sem o serviço ser desligado no meio).
- **Memória**: contêiner com `mem_limit 14g`, 8 CPUs; lote por modelo medido (large-v3: 4, turbo: 8). O modelo carregado
  é descarregado após 10 min sem uso.

## API (JSON; `Authorization: Bearer <token>`)

| Chamada | O que faz |
|---|---|
| `GET /saude` | Sem token. Liga o serviço (via gateway) e responde `{"ok": true}`. |
| `GET /v1/info` | Modelos, idiomas, limites, retenção, GPU, se há diarização. |
| `POST /v1/arquivos` `{nome, tamanho}` | Cria o envio em partes. |
| `PUT /v1/arquivos/{id}?deslocamento=N` | Envia uma parte (corpo binário, até 64 MB). `409` com `recebido` se o deslocamento não bater: o cliente retoma dali. |
| `GET /v1/arquivos/{id}` | `{recebido, tamanho, completo}`. |
| `POST /v1/jobs` `{arquivo_id, parametros:{modelo, idioma, diarizar:{ativar,min,max}}}` | Cria o job (`202`). |
| `GET /v1/jobs/{id}` | Estado, etapa, `progresso` (0 a 1), `atual`/`total` em s, `eta_s`, avisos, meta. |
| `GET /v1/jobs/{id}/eventos` | O mesmo por SSE. |
| `GET /v1/jobs/{id}/log?desde=N` | Linhas do log do job (sem o texto da fala). |
| `POST /v1/jobs/{id}/cancelar` | Cancela (entre lotes). |
| `GET /v1/jobs/{id}/resultado?formato=txt\|md\|srt\|json` | Mesmos formatos do programa. |
| `DELETE /v1/jobs/{id}` | Apaga job e resultados. |

Modelos: `tiny`, `base`, `small`, `medium`, `large-v3`, `large-v3-turbo` (padrão). Formatos de entrada: tudo o que o
ffmpeg decodifica (wav, mp3, m4a, mp4, ogg, opus, flac, webm…).

## Desempenho medido (16/11/2026)

Áudio de teste: diálogo sintético em pt-BR (duas vozes), 14,9 min; e o mesmo repetido 4 vezes (59,6 min).
PC do Rafael: Intel i5-7200U (2 núcleos, 4 threads), 12 GB, sem GPU, motor atual do programa (faster-whisper, CPU, float32).

| Motor | Modelo | 14,9 min de áudio | Velocidade |
|---|---|---|---|
| PC (programa) | small | cerca de 12,2 min (medido: 98,6 s para 2 min de áudio) | 1,2x o tempo real |
| PC (programa) | large-v3 | cerca de 78 min (estimativa pela razão de parâmetros; **não medido**) | 0,2x |
| Spark, serviço | large-v3-turbo | 25,9 s o job inteiro da primeira chamada (10 s só para carregar o modelo) | 35 a 60x |
| Spark, serviço | large-v3 | 73 s | 12x |
| Spark, serviço | large-v3, 59,6 min de áudio | 454 s (7,6 min) | 7,9x |

- **Ponta a ponta** a partir do PC, com o turbo: 39 s (envio 9,6 s + processamento 25,9 s) contra mais de 12 min no PC com um modelo bem pior.
- **Erro de palavras** no áudio sintético: small 10,5% (PC e Spark iguais, mesmo modelo), turbo 8,0%, large-v3 6,0%. Voz sintética é fácil;
  áudio real de audiência, com ruído e sobreposição, só se mede com áudio real.
- **Memória** (queda da memória disponível do host): turbo cerca de 5 GB; large-v3 com lote 4 cerca de 12 GB (com lote 8, 18 GB).
- **vLLM em produção** (resposta mínima do modelo utilitário a cada 1 s): parado 91 a 120 ms; durante o turbo 127 ms (máx. 281);
  durante o large-v3 de 1 h 187 ms (máx. 375). Sem falhas. Carga pesada no vLLM principal durante uma transcrição **não foi medida**.
- **Rede PC para Spark** (Tailscale direto, IPv6): 24 Mbit/s em partes HTTP de 8 MB, 40 a 60 Mbit/s por SSH; 1 h de WAV (109 MB) leva ~1 min
  para subir; comprimir antes (opus mono, ~1,5 MB por 8 min) reduz isso a segundos.
- **Ligar a frio** pelo Sablier: 6,7 a 6,9 s. Desligamento por ociosidade comprovado (sessão de 1 min: contêiner parou em 60 s).
  Job de 7,6 min completou com a sessão do Sablier em 1 min e o PC sem consultar: a renovação própria do serviço funciona.
- **OCR** (PDF escaneado de 8 páginas, 200 dpi, Tesseract por): PC 6,6 s/página; Spark em ARM 1,0 s/página com 1 processo e 0,3 s/página com 8;
  Docling da Spark 1,8 s/página (liga em 12 s) e devolve Markdown estruturado.

## Identificação de interlocutores

Há um ponto de extensão (`app/diarizacao.py`): quando uma biblioteca for registrada, o job com
`diarizar.ativar = true` atribui o interlocutor a cada trecho (maior sobreposição), devolve a quantidade, o tempo de
fala de cada um e as trocas, e os formatos ganham o rótulo "Interlocutor N". **Sem biblioteca registrada, o job termina
normalmente e avisa `diarizacao_indisponivel`**: nada é inventado.

## Operar

```bash
cd ~/EtherLake/extrator-servico
docker compose -p extrator build extrator-servico
docker compose -p extrator up --no-start --force-recreate extrator-servico   # cria parado (o Sablier liga)
docker compose -p extrator up -d gateway                                     # gateway sempre ligado

curl http://100.91.153.82:8110/saude            # liga a frio (~7 s)
docker logs -f extrator-servico                 # logs estruturados (uma linha JSON por evento)
docker stop extrator-servico                    # desligar na mão (o Sablier religa no próximo pedido)
docker compose -p extrator down                 # remove os dois contêineres (modelos e dados ficam em ./modelos e ./dados)
```

Tokens: `~/.config/extrator-servico/tokens` (uma linha `cliente:token`, mínimo 24 caracteres, modo 600; **fora do
repositório**). O serviço **não sobe sem esse arquivo**. Para gerar: `echo "cliente:$(openssl rand -hex 24)" >> ...`.
Para revogar: apagar a linha e `docker restart extrator-servico`.

## Testes

```bash
EXTRATOR_TOKEN=... EXTRATOR_TOKEN2=... python ferramentas/teste_servico.py http://100.91.153.82:8110 audio.wav basicos
python ferramentas/teste_servico.py <url> audio.wav cancelamento
python ferramentas/cliente_teste.py <url> audio.wav [modelo] [idioma]     # ponta a ponta, com tempos
```

`ferramentas/bench/` guarda os benchmarks (GPU, OCR em ARM, Docling, memória, sonda de latência do vLLM).

## Segurança

- Só na tailnet (porta publicada no IP da tailnet, nunca na LAN); a ACL deixa outros membros chegarem à porta, então o token é obrigatório.
- Token por cliente, comparação em tempo constante; sem token = 401.
- Limites: 4 GB por arquivo, 6 h de áudio, partes de até 64 MB; uploads parciais expiram em 6 h.
- Mensagens de erro sem caminhos internos; logs sem conteúdo da fala.
