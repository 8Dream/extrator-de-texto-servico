const $ = (id) => document.getElementById(id);
const caminhos = {
  transcricao: "/v1/info",
  documentos: "/documentos/info",
};
const idiomas = {
  auto: "Detectar automaticamente", pt: "Português", en: "Inglês",
  es: "Espanhol", fr: "Francês", de: "Alemão", it: "Italiano",
};
const modosPdf = new Set(["searchable", "force-pdf", "redo-pdf"]);
const audios = "audio/*,video/*,.opus,.ogg,.mkv,.m4a,.wma,.aac,.flac,.avi,.wmv,.m4v";
const imagens = ".png,.jpg,.jpeg,.tif,.tiff,.bmp,.webp";
const documentos = ".pdf,.docx,.pptx,.xlsx,.html,.htm,.txt,.csv,.json,.xml";
const filas = { transcricao: [], documentos: [] };
const capacidade = {};
let aba = "transcricao";
let token = "";
let conectando = false;
let execucao = null;

function aviso(id, texto, erro = false) {
  $(id).textContent = texto;
  $(id).classList.toggle("erro", erro);
}

async function pedir(caminho, opcoes = {}, tipo = "json") {
  const headers = new Headers(opcoes.headers);
  headers.set("Authorization", `Bearer ${token}`);
  let resposta;
  try {
    resposta = await fetch(caminho, { ...opcoes, headers, cache: "no-store" });
  } catch (erro) {
    if (erro.name === "AbortError") throw erro;
    throw new Error("A conexão caiu. Inicie a fila novamente para tentar continuar.");
  }
  if (resposta.status === 401) throw new Error("Token inválido. Conecte novamente com um token válido.");
  if (!resposta.ok && !(resposta.status === 409 && opcoes.method === "PUT")) {
    const erro = await resposta.json().catch(() => ({}));
    throw new Error(typeof erro.detail === "string" ? erro.detail : `O serviço retornou HTTP ${resposta.status}.`);
  }
  if (resposta.status === 204) return;
  return tipo === "blob" ? resposta.blob() : resposta.json();
}

function post(dados) {
  return { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados) };
}

function opcoes(id, valores, padrao, rotulo = (valor) => valor) {
  $(id).replaceChildren(...valores.map((valor) => new Option(rotulo(valor), valor)));
  if (valores.includes(padrao)) $(id).value = padrao;
}

function ajustarDocumentos() {
  const modo = $("modo").value;
  $("campo-paginas").hidden = modo === "direct" || modo === "imagem";
  opcoes("formato", modo === "direct" ? ["md"] : modosPdf.has(modo) ? ["pdf"] : ["md", "txt"], "md", (f) => f.toUpperCase());
  if (aba !== "documentos") return;
  $("arquivos").accept = modo === "direct" ? documentos : modo === "imagem" ? imagens : ".pdf";
  $("formatos-arquivo").textContent = $("arquivos").accept.replaceAll(",", ", ").toUpperCase();
}

function trocarAba(nova) {
  if (execucao || conectando) return;
  aba = nova;
  const transcrevendo = aba === "transcricao";
  $("aba-transcricao").setAttribute("aria-pressed", String(transcrevendo));
  $("aba-documentos").setAttribute("aria-pressed", String(!transcrevendo));
  $("ajustes-transcricao").hidden = !transcrevendo;
  $("ajustes-documentos").hidden = transcrevendo;
  $("modelo").disabled = !transcrevendo;
  $("idioma").disabled = !transcrevendo;
  $("tipo-arquivo").textContent = transcrevendo ? "Selecione ou arraste áudios e vídeos" : "Selecione ou arraste documentos";
  $("arquivos").accept = audios;
  $("formatos-arquivo").textContent = "MP3, WAV, M4A, MP4, entre outros";
  if (!transcrevendo) ajustarDocumentos();
  $("iniciar").textContent = transcrevendo ? "Transcrever fila" : "Converter fila";
  aviso("estado-fila", "");
  atualizar();
  if (token && !capacidade[aba]) conectar(aba);
}

async function conectar(modo) {
  conectando = true;
  aviso("estado-conexao", modo === "transcricao" ? "Ligando o motor de transcrição…" : "Conectando ao conversor…");
  atualizar();
  try {
    capacidade[modo] = await pedir(caminhos[modo]);
    if (modo === "transcricao") {
      const info = capacidade[modo];
      opcoes("modelo", info.modelos, info.modelo_padrao);
      opcoes("idioma", info.idiomas, "pt", (codigo) => idiomas[codigo] || codigo);
    }
    $("token").value = "";
    aviso("estado-conexao", "Conectado. O token fica na memória desta página.");
  } catch (erro) {
    delete capacidade[modo];
    aviso("estado-conexao", erro.message, true);
  } finally {
    conectando = false;
    atualizar();
  }
}

function botao(rotulo, acao) {
  const elemento = document.createElement("button");
  elemento.type = "button";
  elemento.textContent = rotulo;
  elemento.addEventListener("click", acao);
  return elemento;
}

function baixar(blob, nome) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = nome;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 30000);
}

function nomeSaida(item, formato) {
  return `${item.arquivo.name.replace(/\.[^.]+$/, "") || "resultado"}.${formato}`;
}

async function resultado(item, formato) {
  try {
    const dados = item.blob ?? await pedir(`/v1/jobs/${item.job}/resultado?formato=${formato}`, {}, "blob");
    baixar(dados, nomeSaida(item, formato));
  } catch (erro) {
    aviso("estado-fila", erro.message, true);
  }
}

function criarItem(arquivo) {
  const linha = document.createElement("li");
  const nome = document.createElement("strong");
  nome.textContent = arquivo.name;
  const estado = document.createElement("p");
  const progresso = document.createElement("progress");
  progresso.max = 100;
  progresso.setAttribute("aria-label", `Progresso de ${arquivo.name}`);
  const acoes = document.createElement("div");
  acoes.className = "linha acoes-item";
  linha.append(nome, estado, progresso, acoes);
  const item = { arquivo, linha, estado, progresso, acoes, situacao: "pendente" };
  item.remover = botao("Remover", () => {
    if (execucao) return;
    filas[aba].splice(filas[aba].indexOf(item), 1);
    item.linha.remove();
    atualizar();
  });
  acoes.append(item.remover);
  mostrar(item, "Na fila", null, true);
  return item;
}

function mostrar(item, mensagem, valor, ocultar = false) {
  item.estado.textContent = mensagem;
  item.estado.classList.toggle("erro", item.situacao === "erro");
  item.progresso.hidden = ocultar;
  if (valor == null) item.progresso.removeAttribute("value");
  else item.progresso.value = Math.round(valor * 100);
}

function atualizar() {
  const fila = filas[aba];
  const travado = Boolean(execucao || conectando);
  $("iniciar").disabled = travado || !capacidade[aba] || !fila.some((item) => item.situacao !== "pronto");
  $("limpar").disabled = travado || !fila.length;
  $("fila-vazia").hidden = Boolean(fila.length);
  $("cancelar").hidden = !execucao || aba !== "transcricao";
  $("cancelar").disabled = !execucao?.item || Boolean(execucao?.cancelada);
  for (const id of ["token", "conectar", "aba-transcricao", "aba-documentos", "arquivos", "modo", "formato", "paginas"]) {
    $(id).disabled = travado;
  }
  $("modelo").disabled = travado || aba !== "transcricao";
  $("idioma").disabled = travado || aba !== "transcricao";
  $("seletor").classList.toggle("bloqueado", travado);
  for (const item of fila) item.remover.disabled = travado;
}

function adicionar(arquivos) {
  if (execucao || conectando) return;
  for (const arquivo of arquivos) {
    const fila = filas[aba];
    if (fila.some((item) => item.arquivo.name === arquivo.name && item.arquivo.size === arquivo.size && item.arquivo.lastModified === arquivo.lastModified)) continue;
    const item = criarItem(arquivo);
    fila.push(item);
    $("itens-fila").append(item.linha);
  }
  atualizar();
}

function conferirCancelamento() {
  if (execucao.cancelada) throw new DOMException("Execução cancelada.", "AbortError");
}

async function enviar(item, info) {
  const arquivo = item.arquivo;
  if (arquivo.size > info.limites.tamanho_max_bytes) throw new Error("O arquivo excede o limite de tamanho da transcrição.");
  let recebido = 0;
  if (item.envio) {
    try {
      ({ recebido } = await pedir(`/v1/arquivos/${item.envio}`));
    } catch (erro) {
      if (erro.message !== "arquivo nao encontrado") throw erro;
      item.envio = null;
    }
  }
  conferirCancelamento();
  if (!item.envio) {
    const envio = await pedir("/v1/arquivos", post({ nome: arquivo.name, tamanho: arquivo.size }));
    item.envio = envio.id;
  }
  const parte = Math.min(8 * 2 ** 20, info.limites.parte_max_bytes);
  let semProgresso = 0;
  while (recebido < arquivo.size) {
    conferirCancelamento();
    mostrar(item, `Enviando arquivo · ${Math.floor(recebido * 100 / arquivo.size)}%`, recebido / arquivo.size);
    const inicio = recebido;
    const resposta = await pedir(`/v1/arquivos/${item.envio}?deslocamento=${inicio}`, {
      method: "PUT", headers: { "Content-Type": "application/octet-stream" },
      body: arquivo.slice(inicio, inicio + parte), signal: execucao.envio.signal,
    });
    recebido = resposta.recebido;
    if (!Number.isSafeInteger(recebido) || recebido < 0 || recebido > arquivo.size) throw new Error("O serviço informou um ponto de retomada inválido.");
    semProgresso = recebido === inicio ? semProgresso + 1 : 0;
    if (semProgresso > 2) throw new Error("O envio parou de avançar. Inicie a fila para tentar retomar.");
  }
}

async function transcrever(item, parametros) {
  if (!item.job) {
    await enviar(item, capacidade.transcricao);
    conferirCancelamento();
    mostrar(item, "Entrando na fila da Spark…");
    const job = await pedir("/v1/jobs", post({ arquivo_id: item.envio, parametros }));
    item.job = job.id;
    item.envio = null;
  }
  let cancelamentoEnviado = false;
  for (;;) {
    if (execucao.cancelada && !cancelamentoEnviado) {
      await pedir(`/v1/jobs/${item.job}/cancelar`, { method: "POST" });
      cancelamentoEnviado = true;
    }
    const job = await pedir(`/v1/jobs/${item.job}`);
    if (job.estado === "concluida") return capacidade.transcricao.formatos;
    if (job.estado === "falhou" || job.estado === "cancelada") {
      item.job = null;
      if (job.estado === "cancelada") throw new DOMException("Execução cancelada.", "AbortError");
      throw new Error(job.erro || "A transcrição falhou.");
    }
    const etapa = {
      fila: "Na fila da Spark", decodificando: "Decodificando áudio",
      carregando_modelo: "Carregando modelo", transcrevendo: "Transcrevendo",
    }[job.etapa] || job.etapa.replaceAll("_", " ");
    const percentual = job.progresso == null ? "" : ` · ${Math.round(job.progresso * 100)}%`;
    const eta = job.eta_s > 0 ? ` · cerca de ${Math.ceil(job.eta_s)} s restantes` : "";
    mostrar(item, cancelamentoEnviado ? "Cancelando…" : etapa + percentual + eta, job.progresso);
    await new Promise((resolver) => setTimeout(resolver, 900));
  }
}

async function converter(item, ajustes) {
  if (item.arquivo.size > capacidade.documentos.tamanho_max_bytes) throw new Error("O documento excede o limite de 100 MiB.");
  mostrar(item, "Enviando e processando documento…");
  const query = new URLSearchParams({ nome: item.arquivo.name, ...ajustes });
  item.blob = await pedir(`/documentos/converter?${query}`, {
    method: "POST", body: item.arquivo, headers: { "Content-Type": "application/octet-stream" },
  }, "blob");
  return [ajustes.formato];
}

$("conexao").addEventListener("submit", (evento) => {
  evento.preventDefault();
  if (execucao || conectando) return;
  const novo = $("token").value.trim();
  if (!novo) return;
  if (token && token !== novo && Object.values(filas).some((fila) => fila.some((item) => item.job || item.envio))) {
    aviso("estado-conexao", "Limpe as filas antes de trocar o token.", true);
    return;
  }
  token = novo;
  for (const modo of Object.keys(capacidade)) delete capacidade[modo];
  conectar(aba);
});

for (const [modo, id] of [["transcricao", "aba-transcricao"], ["documentos", "aba-documentos"]]) {
  $(id).addEventListener("click", () => {
    trocarAba(modo);
    $("itens-fila").replaceChildren(...filas[aba].map((item) => item.linha));
  });
}
$("modo").addEventListener("change", ajustarDocumentos);
$("arquivos").addEventListener("change", (evento) => {
  adicionar(evento.target.files);
  evento.target.value = "";
});
for (const tipo of ["dragenter", "dragover", "dragleave", "drop"]) {
  $("seletor").addEventListener(tipo, (evento) => {
    evento.preventDefault();
    $("seletor").classList.toggle("arrastando", tipo === "dragenter" || tipo === "dragover");
    if (tipo === "drop") adicionar(evento.dataTransfer.files);
  });
}
$("limpar").addEventListener("click", () => {
  filas[aba].length = 0;
  $("itens-fila").replaceChildren();
  aviso("estado-fila", "");
  atualizar();
});
$("cancelar").addEventListener("click", () => {
  if (!execucao?.item) return;
  execucao.cancelada = true;
  execucao.envio.abort();
  atualizar();
});

$("processamento").addEventListener("submit", async (evento) => {
  evento.preventDefault();
  if (execucao || !capacidade[aba]) return;
  const ajustes = aba === "transcricao"
    ? { modelo: $("modelo").value, idioma: $("idioma").value }
    : { modo: $("modo").value, formato: $("formato").value, paginas: $("campo-paginas").hidden ? "" : $("paginas").value.trim() };
  execucao = { cancelada: false, envio: new AbortController(), item: null };
  aviso("estado-fila", "");
  atualizar();
  try {
    for (const item of filas[aba]) {
      if (execucao.cancelada) break;
      if (item.situacao === "pronto") continue;
      execucao.item = item;
      item.situacao = "processando";
      atualizar();
      try {
        if (!item.arquivo.size) throw new Error("O arquivo está vazio.");
        const formatos = await (aba === "transcricao" ? transcrever(item, ajustes) : converter(item, ajustes));
        item.situacao = "pronto";
        mostrar(item, "Concluído", 1);
        item.acoes.prepend(...formatos.map((formato) => botao(`Baixar ${formato.toUpperCase()}`, () => resultado(item, formato))));
      } catch (erro) {
        item.situacao = erro.name === "AbortError" ? "cancelado" : "erro";
        mostrar(item, item.situacao === "cancelado" ? "Cancelado" : erro.message, null, true);
      }
    }
    if (execucao.cancelada) aviso("estado-fila", "Execução cancelada. Os arquivos pendentes continuam na fila.");
  } finally {
    execucao = null;
    atualizar();
  }
});

ajustarDocumentos();
atualizar();
