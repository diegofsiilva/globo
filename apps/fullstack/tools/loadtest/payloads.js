/**
 * Gerador de change events válidos, compartilhado entre `changes_load.js`
 * (carga/performance) e `eventos_invalidos.js` (RNF04) — os dois precisam do
 * mesmo "tráfego de fundo" plausível, só o segundo intercala payloads quebrados
 * nele.
 *
 * Schema de referência: `worker/src/argus_worker/changes.py::ChangeEvent`.
 *
 * IMPORTANTE: `pk`/`after` têm que casar com as colunas REAIS de
 * `bronze.<tabela>` (ver `db/migrations/004_bronze_corrente_argus.sql` e
 * `010_merge_e_etl.sql::merge_do_log`) — o merge monta a linha via
 * `jsonb_populate_record`, que ignora chave desconhecida mas não inventa
 * coluna faltando. Um único formato genérico pras 6 tabelas (usado até
 * 2026-09-01) só coincidia com `signal_bucket`; as outras cinco caíam na
 * changes-dlq por `NOT NULL` — não por falha do worker, mas por payload de
 * teste com o schema errado. Cada tabela tem seu próprio pk/after aqui por
 * causa disso.
 */

// Fontes reais do dataset Argus (ver dataset-argus / mapa de tratamentos):
// cadências bem diferentes (prometheus ~1 min, rpaas ~15 min, npaw ~28 h de
// atraso) — misturar as três aqui é o que torna o tráfego sintético parecido
// com o real, em vez de eventos uniformes de uma fonte só.
export const FONTES = ['prometheus', 'rpaas', 'npaw'];

const ESTADOS = ['SP', 'RJ', 'MG', 'RS', 'BA', 'PR'];
const ISPS = ['vivo', 'claro', 'tim', 'oi'];

// Peso maior para signal_point/signal_bucket: é o par já unificado pela Globo
// e o de maior volume real no dataset (ver mapa-tratamentos-bronze-silver-gold.md).
// As demais aparecem em proporção bem menor, só para o tráfego não ficar
// artificialmente restrito a duas tabelas.
const TABELAS_PESADAS = ['signal_point', 'signal_bucket'];
const TABELAS_LEVES = ['device_hourly', 'geo_hourly', 'player_hourly', 'incidents'];

export function tabelaAleatoria() {
  // 80% nas pesadas, 20% espalhado nas leves — não é uma medição real de
  // proporção, é só o suficiente para o teste não bater só numa tabela e
  // mascarar contenção que apareceria com tráfego misto.
  if (Math.random() < 0.8) {
    return TABELAS_PESADAS[Math.floor(Math.random() * TABELAS_PESADAS.length)];
  }
  return TABELAS_LEVES[Math.floor(Math.random() * TABELAS_LEVES.length)];
}

let contadorEntidade = 0;
let contadorHorario = 0;
let contadorIncidente = 0;

function aleatorioDe(lista) {
  return lista[Math.floor(Math.random() * lista.length)];
}

function bucketDeMinuto(agora) {
  return agora - (agora % 60000);
}

function bucketDeHora(agora) {
  return agora - (agora % 3600000);
}

// Um construtor por tabela: devolve { pk, after } com o nome de coluna exato
// da bronze. `after` só carrega colunas que aceitam NULL na tabela real (ou,
// no caso de `incidents`, inclui a NOT NULL que fica fora da pk) — assim o
// upsert nunca esbarra em NOT NULL independente da ordem em que os eventos
// chegam (o merge é `INSERT ... ON CONFLICT DO UPDATE`, então mesmo um evento
// "de update" pode ser a primeira vez que a linha aparece).
const CONSTRUTORES_POR_TABELA = {
  signal_point(agora) {
    return {
      pk: {
        ts: bucketDeMinuto(agora),
        source: aleatorioDe(FONTES),
        entity: `k6-entity-${contadorEntidade++ % 5000}`,
        metric: 'latency_ms',
      },
      after: { value: Math.random() * 500 },
    };
  },
  signal_bucket(agora) {
    return {
      pk: {
        bts: bucketDeMinuto(agora),
        source: aleatorioDe(FONTES),
        entity: `k6-entity-${contadorEntidade++ % 5000}`,
        metric: 'latency_ms',
      },
      after: { value: Math.random() * 500 },
    };
  },
  device_hourly(agora) {
    return {
      pk: {
        hour_ts: bucketDeHora(agora),
        device: `k6-device-${contadorHorario++ % 200}`,
      },
      after: {
        sessions: Math.floor(Math.random() * 1000),
        errors: Math.floor(Math.random() * 50),
      },
    };
  },
  geo_hourly(agora) {
    return {
      pk: {
        hour_ts: bucketDeHora(agora),
        state_province: aleatorioDe(ESTADOS),
        isp: aleatorioDe(ISPS),
      },
      after: {
        sessions: Math.floor(Math.random() * 1000),
        errors: Math.floor(Math.random() * 50),
      },
    };
  },
  player_hourly(agora) {
    return {
      pk: {
        hour_ts: bucketDeHora(agora),
        player: `k6-player-${contadorHorario++ % 20}`,
      },
      after: {
        sessions: Math.floor(Math.random() * 1000),
        errors: Math.floor(Math.random() * 50),
      },
    };
  },
  incidents(agora) {
    // `opened_at` é NOT NULL e fica FORA da pk (a pk é só `sys_id`) — sem ele
    // no `after`, a primeira vez que um `sys_id` aparece falha por NOT NULL,
    // mesmo com a pk certa. As demais colunas do ServiceNow são todas
    // opcionais, então ficam de fora (viram `_extra` vazio, não erro).
    return {
      pk: { sys_id: `k6-inc-${contadorIncidente++ % 1000}` },
      after: {
        opened_at: agora,
        state: aleatorioDe(['new', 'in_progress', 'resolved']),
        priority: aleatorioDe(['1', '2', '3']),
      },
    };
  },
};

/** Monta um change event válido, no formato de `changes.py::ChangeEvent`. */
export function changeEventAleatorio() {
  const agora = Date.now();
  const tabela = tabelaAleatoria();
  const { pk, after } = CONSTRUTORES_POR_TABELA[tabela](agora);

  return {
    source_table: tabela,
    op: 'u',
    pk,
    after,
    captured_at: new Date(agora).toISOString(),
  };
}

export function loteAleatorio(n) {
  const changes = [];
  for (let i = 0; i < n; i++) {
    changes.push(changeEventAleatorio());
  }
  return changes;
}
