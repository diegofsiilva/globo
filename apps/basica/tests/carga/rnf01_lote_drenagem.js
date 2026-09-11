/**
 * RNF01 revisado — injeta lotes logicos de 150 mil eventos.
 *
 * O endpoint transforma cada corpo HTTP em uma mensagem SQS. Por isso o lote
 * logico e fragmentado por bytes: nenhuma mensagem se aproxima do limite de
 * 256 KiB do SQS, independentemente da quantidade de eventos no fragmento.
 * A drenagem posterior e medida pela AWS, fora do k6.
 */

import http from "k6/http";
import { check } from "k6";
import exec from "k6/execution";
import { Counter, Rate, Trend } from "k6/metrics";
import {
  gerarEvento,
  headersIngestao,
  headersLeitura,
  INGEST_ENDPOINT,
  numero,
  READ_URL,
  TEST_ID,
  validarConfiguracao,
} from "./helpers.js";

const EVENTOS_POR_LOTE = inteiroNoIntervalo(
  __ENV.K6_EVENTOS_POR_LOTE || "150000",
  1,
  150000,
);
const QUANTIDADE_LOTES = inteiroNoIntervalo(__ENV.K6_QUANTIDADE_LOTES || "1", 1, 4);
const TOTAL_EVENTOS = EVENTOS_POR_LOTE * QUANTIDADE_LOTES;
const VUS_INJECAO = inteiroNoIntervalo(__ENV.K6_VUS_INJECAO || "50", 1, 50);
// A integracao SQS-SendMessage do API Gateway serializa parametros na chamada
// ao servico e devolve 414 antes do limite bruto de 256 KiB do SQS. O teto de
// 40 KiB foi validado contra a borda publicada e deixa margem para encoding.
const MAX_BODY_BYTES = inteiroNoIntervalo(__ENV.K6_MAX_BODY_BYTES || "40000", 1024, 240000);
const SENTINELA_SESSION_ID = `${TEST_ID}-sentinela`;

const eventosAceitos = new Counter("eventos_lote_aceitos");
const eventosRejeitados = new Counter("eventos_lote_rejeitados");
const requisicoesLote = new Counter("requisicoes_lote");
const falhasLote = new Rate("falhas_lote");
const latenciaFragmento = new Trend("latencia_fragmento_ms", true);
const eventosPorFragmento = new Trend("eventos_por_fragmento");
const bytesPorFragmento = new Trend("bytes_por_fragmento");

export const options = {
  discardResponseBodies: true,
  scenarios: {
    injecao_lotes: {
      executor: "per-vu-iterations",
      vus: VUS_INJECAO,
      iterations: 1,
      maxDuration: "45m",
      exec: "injetarLotes",
    },
  },
  thresholds: {
    eventos_lote_aceitos: [`count>=${TOTAL_EVENTOS}`],
    eventos_lote_rejeitados: ["count==0"],
    falhas_lote: ["rate==0"],
    latencia_fragmento_ms: ["p(95)<5000"],
  },
};

export function setup() {
  validarConfiguracao({ ingestao: true, leitura: true });
  const respostaRelogio = http.get(`${READ_URL}/api/v1/clock`, {
    headers: headersLeitura(),
    responseType: "text",
    timeout: "7s",
    tags: { name: "GET /api/v1/clock", fase: "preflight_lote" },
  });
  if (respostaRelogio.status !== 200) {
    throw new Error(`relogio virtual respondeu HTTP ${respostaRelogio.status}`);
  }
  const simNow = respostaRelogio.json("sim_now");
  if (!simNow) throw new Error("resposta de /api/v1/clock nao contem sim_now");
  return {
    testId: TEST_ID,
    quantidadeLotes: QUANTIDADE_LOTES,
    totalEventos: TOTAL_EVENTOS,
    vusInjecao: VUS_INJECAO,
    simNow,
  };
}

export function injetarLotes(configuracao) {
  let fragmento = [];
  let bytes = 2;

  const primeiroIndice = exec.vu.idInTest - 1;
  for (let indice = primeiroIndice; indice < TOTAL_EVENTOS; indice += VUS_INJECAO) {
    const numeroLote = Math.floor(indice / EVENTOS_POR_LOTE) + 1;
    const ultimoEvento = indice === TOTAL_EVENTOS - 1;
    const identificadores = {
      timestamp: configuracao.simNow,
      load_test_sent_at: new Date().toISOString(),
      batch_id: `${TEST_ID}-lote-${String(numeroLote).padStart(2, "0")}`,
      batch_event_index: indice % EVENTOS_POR_LOTE,
    };
    if (ultimoEvento) identificadores.session_id = SENTINELA_SESSION_ID;
    const evento = gerarEvento(identificadores);
    const serializado = JSON.stringify(evento);
    const bytesAdicionais = serializado.length + (fragmento.length > 0 ? 1 : 0);

    if (fragmento.length > 0 && bytes + bytesAdicionais > MAX_BODY_BYTES) {
      enviarFragmento(fragmento, bytes);
      fragmento = [];
      bytes = 2;
    }

    fragmento.push(serializado);
    bytes += serializado.length + (fragmento.length > 1 ? 1 : 0);
  }

  if (fragmento.length > 0) enviarFragmento(fragmento, bytes);
}

function enviarFragmento(eventosSerializados, bytes) {
  const quantidade = eventosSerializados.length;
  const resposta = http.post(
    INGEST_ENDPOINT,
    `[${eventosSerializados.join(",")}]`,
    {
      headers: headersIngestao(),
      timeout: "10s",
      tags: { name: "POST /v1/events", fase: "injecao_lote" },
    },
  );
  const sucesso = resposta.status >= 200 && resposta.status < 300;

  requisicoesLote.add(1);
  falhasLote.add(!sucesso);
  latenciaFragmento.add(resposta.timings.duration);
  eventosPorFragmento.add(quantidade);
  bytesPorFragmento.add(bytes);
  if (sucesso) eventosAceitos.add(quantidade);
  else eventosRejeitados.add(quantidade);

  check(resposta, {
    "fragmento foi aceito": () => sucesso,
    "fragmento respondeu em ate 5s": (r) => r.timings.duration <= 5000,
  });
}

function inteiroNoIntervalo(valor, minimo, maximo) {
  const numeroInteiro = Number.parseInt(valor, 10);
  if (!Number.isInteger(numeroInteiro) || numeroInteiro < minimo || numeroInteiro > maximo) {
    throw new Error(`valor ${valor} deve ser inteiro entre ${minimo} e ${maximo}`);
  }
  return numeroInteiro;
}

export function handleSummary(data) {
  const inicio = new Date(data.state.testRunDurationMs
    ? Date.now() - data.state.testRunDurationMs
    : Date.now());
  const duracaoS = numero(data.metrics.iteration_duration, "max") / 1000;
  const aceitos = numero(data.metrics.eventos_lote_aceitos, "count");
  const resumo = {
    requisito: "RNF01-lotes",
    test_id: TEST_ID,
    configuracao: {
      eventos_por_lote: EVENTOS_POR_LOTE,
      quantidade_lotes: QUANTIDADE_LOTES,
      total_eventos: TOTAL_EVENTOS,
      vus_injecao: VUS_INJECAO,
      maximo_bytes_por_fragmento: MAX_BODY_BYTES,
    },
    injecao: {
      inicio_aproximado_utc: inicio.toISOString(),
      fim_utc: new Date().toISOString(),
      duracao_s: duracaoS.toFixed(3),
      eventos_aceitos: aceitos,
      eventos_rejeitados: numero(data.metrics.eventos_lote_rejeitados, "count"),
      requisicoes: numero(data.metrics.requisicoes_lote, "count"),
      vazao_aceite_eventos_s: duracaoS > 0 ? (aceitos / duracaoS).toFixed(2) : "0.00",
      fragmento_p95_ms: numero(data.metrics.latencia_fragmento_ms, "p(95)").toFixed(1),
      fragmento_max_ms: numero(data.metrics.latencia_fragmento_ms, "max").toFixed(1),
    },
    sentinela_session_id: SENTINELA_SESSION_ID,
    drenagem: "PENDENTE: medir fila, persistencia, DLQ e disponibilidade na API apos o aceite",
  };
  const arquivo = __ENV.K6_RESULT_FILE || "resultados/rnf01_lotes_resultado.json";
  return {
    stdout: `${JSON.stringify(resumo, null, 2)}\n`,
    [arquivo]: JSON.stringify(resumo, null, 2),
  };
}
