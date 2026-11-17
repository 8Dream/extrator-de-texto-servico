# Integração do programa (Windows) com o serviço da Spark

Só desenho: nada disto foi implementado no programa. O modo local continua existindo e funcionando sem rede.

## Comportamento

| Item | Decisão |
|---|---|
| Escolha do motor | Configurações da transcrição: **Motor: Este computador | Spark** (padrão: este computador). |
| Endereço e token | URL `http://100.91.153.82:8110` (só tailnet). O token fica **criptografado no perfil do usuário do Windows** (DPAPI via `ctypes`, sem dependência nova), nunca em `dados\config.json`. |
| Testar conexão | Botão na própria tela. Estados em texto: "Ligando a Spark…" (barra indeterminada, ~7 s a frio), "Conectado: GPU NVIDIA GB10, 6 modelos", "Spark fora do ar: a transcrição usará este computador". Sem pop-up. |
| Fallback automático | `GET /saude` com limite de 8 s (a frio, até 40 s: o gateway liga o contêiner). Se falhar por rede, DNS ou 5xx **antes** de enviar o arquivo, a execução segue no motor local e a Central mostra o aviso "Spark indisponível, rodou neste computador". Se a Spark cair **durante** o job, o job fica "falhou" com o motivo e o botão **Repetir** (local ou Spark) aparece; não se repete sozinho, para não gastar horas em duplicidade. |
| Envio | Em partes de 8 MB, retomável: após queda ou suspensão do PC, consulta `GET /v1/arquivos/{id}` e continua do `recebido`. Arquivos acima de 50 MB podem ser comprimidos antes (opus mono 16 kHz, ou FLAC sem perdas) com o ffmpeg que o programa já usa; o servidor aceita qualquer formato do ffmpeg. |
| Progresso | Polling de 1 s em `GET /v1/jobs/{id}` (ou SSE em `/eventos`). `progresso` real (segundos de áudio processados); `eta_s` do servidor entra no ETA da Central; antes de haver dados, "estimando…". |
| Cancelar / Repetir | Cancelar chama `POST /v1/jobs/{id}/cancelar`; Repetir cria novo job com os mesmos parâmetros (o áudio original é apagado no servidor assim que o job termina, então o reenvio é necessário). |
| Resultado | `GET /v1/jobs/{id}/resultado?formato=txt|md|srt|json`: já vem no mesmo formato do programa; é salvo com o mesmo `salvar_saida`. Depois do download, `DELETE /v1/jobs/{id}` apaga tudo no servidor. |
| Origem na Central | Chip **Spark** ou **Este computador** no cartão e no resumo; histórico de ETA separado por motor (a velocidade é outra). |
| Privacidade | Aviso fixo ao escolher a Spark: "O áudio é enviado à Spark pela rede privada (Tailscale, criptografada), transcrito lá e apagado ao terminar." |
| Interlocutores | A API já aceita `diarizar: {ativar, min, max}`. O interruptor só aparece quando `/v1/info` diz `diarizacao_disponivel: true`. |

## Mudanças em `src\` (implementação futura)

| Arquivo | Mudança |
|---|---|
| `src\motor_remoto.py` (novo) | Cliente HTTP só com `urllib`: `saude()`, `info()`, `enviar(caminho, progresso, cancelar)` (partes + retomada), `criar_job()`, `acompanhar()` (alimenta a `Execucao`), `resultado()`, `cancelar()`, `apagar()`, mapeamento de erros para mensagens em português, guarda do token (DPAPI). |
| `src\transcricao_core.py` | Em `transcrever_arquivo` (por volta da linha 400): se `motor == "spark"`, chamar o cliente; falha de rede antes do envio cai no ramo local. Acrescentar `large-v3-turbo` ao dicionário de modelos (só vale na Spark; o motor local usa faster-whisper e mantém os atuais). |
| `src\extrator_core.py` | `DEFAULT_CONFIG`: `motor_transcricao`, `servico_url`, `servico_modelo`. O token **não** entra aqui. |
| `src\extrator_api.py` | Novos métodos `servico_testar()`, `servico_salvar(url, token)`, `servico_modelos()`; `save_settings` com lista de campos permitidos; a transcrição passa o motor escolhido. |
| `src\execucoes.py` | Campo `origem` na `Execucao` (`para_dict`, `para_disco`, `de_disco`) e histórico de ETA por (ferramenta, origem). |
| `src\web\index.html`, `app.js`, `styles.css` | Seção "Motor da transcrição" nas configurações (rádio, URL, token, Testar conexão, status), chip de origem nos cartões da Central, aviso de privacidade. |
| `tests\test_motor_remoto.py` (novo) | Servidor falso (`http.server`): saúde ok, saúde com tempo esgotado e fallback, envio com 409 e retomada, cancelamento, erro do servidor, ETA, token criptografado (ida e volta, só no Windows). |
| `requirements.txt` | Nenhuma dependência nova. |
| `installer\Extrator.iss` | Nada: o instalador já copia `src\*.py`. |

## Ordem sugerida

1. `motor_remoto.py` + testes com servidor falso.
2. Ligação em `transcricao_core.py` e `extrator_api.py`.
3. Interface (configurações, chip, aviso).
4. Teste real contra o serviço, com o token do PC, em áudio de verdade.
