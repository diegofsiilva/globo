/**
 * Gerador de tráfego para o RNF04 ("evento inválido não trava os demais").
 *
 * Não dá pra verificar RNF04 só com o que o k6 vê: a integração do API
 * Gateway com `SQS-SendMessage` (`apigateway_changes.tf`) encaminha o corpo
 * cru para a fila sem validar conteúdo -- toda POST desta suíte volta 2xx,
 * inclusive as com payload quebrado. A validação de verdade acontece
 * assíncrona, dentro do merge worker (`consumer.py::_process_message`), e só
 * aparece depois, em `make dlq` (o `FailureReason`) e `make count` (as linhas
 * válidas que sobreviveram). Este script só garante que o tráfego certo saiu
 * -- a checagem de aceite mora no plano de teste, não aqui.
 *
 * Dois grupos de caso, porque o worker trata os dois níveis de forma
 * diferente (ver `consumer.py::_extract` vs `_process_message`):
 *
 *   1. Item inválido DENTRO de um lote por outro lado válido. `_extract` já
 *      separou a lista, e cada item é parseado e quarentenado
 *      INDIVIDUALMENTE em `_process_message` -- os demais itens do mesmo
 *      lote sobrevivem. É a forma "forte" do RNF04.
 *   2. Corpo do POST inteiro malformado (JSON quebrado). `_extract` falha
 *      ANTES de separar itens, e a mensagem inteira (não um item) vai pra
 *      DLQ via `_quarantine`. Testa a forma "fraca": um POST ruim não some
 *      em silêncio, mas leva junto qualquer evento válido que estivesse no
 *      MESMO corpo -- por isso o script nunca mistura este caso com
 *      eventos válidos no mesmo POST.
 *
 * Os dois casos vão para a DLQ na PRIMEIRA tentativa (`_quarantine` roda
 * antes de qualquer redrive do SQS) -- não é preciso esperar as 5 tentativas
 * de `max_receive_count` para ver o `FailureReason` em `make dlq`.
 *
 * `ChangeTooLarge` (`repository.py::check_size`, teto de 4 MB) não é testável
 * por este caminho: o limite de mensagem do SQS (256 KB) rejeitaria o POST
 * bem antes do worker aplicar o próprio teto -- por isso não está na lista.
 *
 * Uso: `make resiliencia-evento-invalido` (ver Makefile).
 */

import http from 'k6/http';
import { check } from 'k6';
import { Counter } from 'k6/metrics';
import { changeEventAleatorio } from './payloads.js';

const URL = __ENV.ARGUS_CHANGES_URL;
const TOKEN = __ENV.ARGUS_INGEST_TOKEN;
if (!URL) throw new Error('ARGUS_CHANGES_URL nao definida');
if (!TOKEN) throw new Error('ARGUS_INGEST_TOKEN nao definida');

const HEADERS = { headers: { 'content-type': 'application/json', authorization: `Bearer ${TOKEN}` } };

// Quantas vezes cada caso de item inválido é repetido -- baixo de propósito
// (isto é um teste de corretude, não de carga; volume alto só atrapalharia a
// leitura da DLQ depois).
const REPETICOES = Number(__ENV.REPETICOES || 3);
const VALIDOS_POR_LOTE = 10;

// Cada builder recebe um change event válido e devolve a versão quebrada,
// no formato exato que `changes.py::ChangeEvent`/`parse_change` rejeitam.
const CASOS_ITEM = [
  {
    nome: 'sem_source_table',
    quebrar: (e) => {
      const c = { ...e };
      delete c.source_table;
      return c;
    },
  },
  {
    nome: 'tabela_desconhecida',
    quebrar: (e) => ({ ...e, source_table: 'tabela_fantasma_k6' }),
  },
  {
    nome: 'op_invalido',
    quebrar: (e) => ({ ...e, op: 'x' }),
  },
  {
    nome: 'pk_vazia',
    quebrar: (e) => ({ ...e, pk: {} }),
  },
  {
    nome: 'update_sem_after',
    quebrar: (e) => {
      const c = { ...e, op: 'u' };
      delete c.after;
      return c;
    },
  },
];

const itensPorCaso = new Counter('itens_invalidos_por_caso');
const corposMalformados = new Counter('corpos_malformados_enviados');

export const options = {
  scenarios: {
    itens_invalidos: {
      executor: 'shared-iterations',
      exec: 'itemInvalido',
      vus: 3,
      iterations: CASOS_ITEM.length * REPETICOES,
      maxDuration: '2m',
    },
    corpo_malformado: {
      executor: 'shared-iterations',
      exec: 'corpoMalformado',
      vus: 1,
      iterations: REPETICOES,
      maxDuration: '1m',
      startTime: '1s',
    },
  },
};

/** Caso 1: um item quebrado, escondido num lote de itens válidos. */
export function itemInvalido() {
  const caso = CASOS_ITEM[__ITER % CASOS_ITEM.length];

  const lote = [];
  for (let i = 0; i < VALIDOS_POR_LOTE; i++) lote.push(changeEventAleatorio());
  // Insere o item quebrado no meio do lote, não na ponta -- garante que a
  // quarentena por item não depende de posição (primeiro/último).
  lote.splice(Math.floor(VALIDOS_POR_LOTE / 2), 0, caso.quebrar(changeEventAleatorio()));

  const resposta = http.post(URL, JSON.stringify({ changes: lote }), HEADERS);
  check(resposta, { [`aceito na borda (${caso.nome})`]: (r) => r.status < 300 });
  itensPorCaso.add(1, { caso: caso.nome });
}

/** Caso 2: o corpo inteiro do POST não é JSON válido. Nunca misturado a válidos. */
export function corpoMalformado() {
  const corpo = '{"changes": [ isto nao fecha como json k6-rnf04';
  const resposta = http.post(URL, corpo, HEADERS);
  check(resposta, { 'aceito na borda (corpo malformado)': (r) => r.status < 300 });
  corposMalformados.add(1);
}

export function handleSummary(data) {
  const m = data.metrics;
  const totalItens = m.itens_invalidos_por_caso ? m.itens_invalidos_por_caso.values.count : 0;
  const totalCorpos = m.corpos_malformados_enviados ? m.corpos_malformados_enviados.values.count : 0;

  const resumo =
    `\n== RNF04: trafego de eventos invalidos enviado ==\n` +
    `casos de item invalido, ${REPETICOES}x cada: ${CASOS_ITEM.map((c) => c.nome).join(', ')}\n` +
    `total de POSTs com item invalido: ${totalItens}\n` +
    `total de POSTs com corpo malformado: ${totalCorpos}\n` +
    `\nPróximo passo (fora do k6):\n` +
    `  make dlq    -> confere o FailureReason de cada caso acima\n` +
    `  make count  -> confere que os ${VALIDOS_POR_LOTE} validos de cada lote com item\n` +
    `                 invalido foram gravados mesmo assim (o corpo malformado, esse\n` +
    `                 sim, perde os validos que estavam no MESMO corpo -- ver docstring)\n`;

  return { stdout: resumo, 'resultado_rnf04.json': JSON.stringify(data, null, 2) };
}
