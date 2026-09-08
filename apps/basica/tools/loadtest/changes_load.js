/**
 * Carga sustentada contra POST /v1/changes, para os RNFs de performance
 * (10 mil eventos/min) e como gerador de tráfego de fundo nos cenários de
 * resiliência (fila cheia, timeout) descritos no plano de teste.
 *
 * Não reaproveita `tools/replay_events.py`: aquele script fala com
 * `/v1/events` (telemetria de sessão, schema de `worker/src/argus_worker/keys.py`).
 * Este fala com `/v1/changes` (CDC, schema de
 * `worker/src/argus_worker/changes.py` — `source_table`/`op`/`pk`/`before`/
 * `after`/`captured_at`), que é o fluxo que o simulador usa e o que a Sprint
 * pede pra testar.
 *
 * `captured_at` aqui é hora de parede, não `sim.now()`: este teste anda por
 * fora do simulador e do seu relógio virtual, de propósito — mede o caminho
 * de ingestão isoladamente, sem depender do estado do simulador.
 *
 * Uso:
 *   ARGUS_CHANGES_URL=... ARGUS_INGEST_TOKEN=... \
 *     k6 run -e EVENTOS_POR_MINUTO=10000 -e MINUTOS=10 changes_load.js
 *
 * Ou, de dentro de apps/basica: `make carga-changes EVENTOS_POR_MINUTO=10000 MINUTOS=10`.
 */

import http from 'k6/http';
import { check } from 'k6';
import { Counter, Trend } from 'k6/metrics';
import { loteAleatorio } from './payloads.js';

const URL = __ENV.ARGUS_CHANGES_URL;
const TOKEN = __ENV.ARGUS_INGEST_TOKEN;
if (!URL) {
  throw new Error('ARGUS_CHANGES_URL nao definida (veja .env / .env.example)');
}
if (!TOKEN) {
  throw new Error('ARGUS_INGEST_TOKEN nao definida (veja .env / .env.example)');
}

// Alvo nominal da Sprint: 10 mil eventos/min. Configurável para permitir os
// testes de escala (RNF03, dobrar carga) e cenários de resiliência com outra
// taxa, sem duplicar o script.
const EVENTOS_POR_MINUTO = Number(__ENV.EVENTOS_POR_MINUTO || 10000);
const MINUTOS = Number(__ENV.MINUTOS || 5);

// Eventos por POST. Bem abaixo do teto de 48 KB por corpo que o simulador
// respeita (ver `simulator/src/argus_simulator/emitter.py`, TETO_DO_CORPO_BYTES)
// — a integração do API Gateway manda o corpo pela query string do
// SQS-SendMessage, e um corpo grande demais já causou 414 em produção. Não
// replicamos o corte por bytes do emissor aqui: um lote pequeno e fixo já
// fica com folga confortável para o tamanho dos payloads gerados abaixo.
const TAMANHO_DO_LOTE = 20;

// Requisições por segundo que o executor precisa sustentar para atingir a
// meta de eventos/min com este tamanho de lote. Arredondado — a contagem real
// de eventos enviados (não a taxa nominal) é o número que entra na
// reconciliação do resultado, ver handleSummary.
const REQS_POR_SEGUNDO = Math.max(1, Math.round(EVENTOS_POR_MINUTO / 60 / TAMANHO_DO_LOTE));

export const options = {
  // p(99) nao vem nas estatisticas padrao do k6 -- pedimos explicitamente
  // porque o item (3) do artefato quer latencia de cauda, nao so media/p95.
  summaryTrendStats: ['avg', 'min', 'med', 'max', 'p(90)', 'p(95)', 'p(99)'],
  scenarios: {
    carga_changes: {
      executor: 'constant-arrival-rate',
      rate: REQS_POR_SEGUNDO,
      timeUnit: '1s',
      duration: `${MINUTOS}m`,
      // VUs pré-alocadas com folga de 3x: a latência do POST pode variar sob
      // carga (é justamente o que estamos medindo), e VUs insuficientes
      // fariam o próprio k6 virar o gargalo em vez do sistema sob teste.
      preAllocatedVUs: Math.min(300, Math.max(10, REQS_POR_SEGUNDO * 3)),
      maxVUs: Math.min(600, Math.max(20, REQS_POR_SEGUNDO * 6)),
    },
  },
  // Sem threshold que aborte o teste: nos cenários de resiliência, taxa de
  // erro alta É o comportamento esperado durante a janela de falha. O
  // threshold abaixo só marca o resumo final como "atenção", não interrompe
  // a coleta (comportamento padrão do k6 — thresholds não abortam sozinhos).
  thresholds: {
    http_req_failed: ['rate<0.05'],
  },
};

const eventosEnviados = new Counter('eventos_enviados');
const eventosAceitos = new Counter('eventos_aceitos');
const latenciaLote = new Trend('latencia_lote_ms', true);

export default function () {
  const lote = loteAleatorio(TAMANHO_DO_LOTE);
  const corpo = JSON.stringify({ changes: lote });

  const resposta = http.post(URL, corpo, {
    headers: {
      'content-type': 'application/json',
      authorization: `Bearer ${TOKEN}`,
    },
  });

  const aceito = check(resposta, {
    'status < 300': (r) => r.status < 300,
  });

  eventosEnviados.add(lote.length);
  latenciaLote.add(resposta.timings.duration);
  if (aceito) {
    eventosAceitos.add(lote.length);
  }
}

/**
 * Resumo compacto em texto + o resumo completo do k6 em JSON, para virar o
 * item (2) do artefato (resultado do teste de carga). Sem depender de jslib
 * externa — só os agregados que já vêm em `data.metrics`.
 */
export function handleSummary(data) {
  const m = data.metrics;
  const enviados = m.eventos_enviados ? m.eventos_enviados.values.count : 0;
  const aceitos = m.eventos_aceitos ? m.eventos_aceitos.values.count : 0;
  const p95 = m.latencia_lote_ms ? m.latencia_lote_ms.values['p(95)'].toFixed(1) : 'n/d';
  const p99 = m.latencia_lote_ms ? m.latencia_lote_ms.values['p(99)'].toFixed(1) : 'n/d';
  const falhaPct = m.http_req_failed
    ? (m.http_req_failed.values.rate * 100).toFixed(2)
    : 'n/d';

  const resumo =
    `\n== carga /v1/changes ==\n` +
    `alvo nominal: ${EVENTOS_POR_MINUTO} eventos/min por ${MINUTOS} min\n` +
    `eventos enviados: ${enviados}\n` +
    `eventos aceitos (status < 300): ${aceitos}\n` +
    `taxa de falha de requisicao: ${falhaPct}%\n` +
    `latencia do POST (lote de ${TAMANHO_DO_LOTE}): p95=${p95}ms p99=${p99}ms\n`;

  return {
    stdout: resumo,
    'resultado.json': JSON.stringify(data, null, 2),
  };
}
