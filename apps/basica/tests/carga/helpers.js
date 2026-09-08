/** Utilitários compartilhados pelos testes de carga k6 do Argus. */

/** Endpoint completo de ingestão. O output Terraform já termina em /v1/events. */
export const INGEST_ENDPOINT = normalizarEndpoint(__ENV.ARGUS_INGEST_URL || "");

/** URL base da API de leitura, sem barra final. */
export const READ_URL = normalizarEndpoint(__ENV.ARGUS_API_URL || "");

export const INGEST_TOKEN = __ENV.ARGUS_INGEST_TOKEN || "";
export const READ_TOKEN = __ENV.ARGUS_READ_TOKEN || "";
export const TEST_ID = __ENV.K6_TEST_ID || "manual-sem-id";

const EVENT_TYPES = ["request", "vitals", "screen_view", "video_view", "session", "error"];
const PLATFORMS = ["android_tv", "apple_tv", "fire_tv", "ios", "android", "web"];
const OS_LIST = ["Android 12", "tvOS 16", "Fire OS 7", "iOS 17", "Android 14", "Chrome 120"];

function normalizarEndpoint(url) {
  return url.trim().replace(/\/+$/, "");
}

function inteiroAleatorio(min, max) {
  return Math.floor(Math.random() * (max - min + 1)) + min;
}

/** UUID suficiente para distinguir eventos sintéticos. */
export function uuid() {
  const hex = "0123456789abcdef";
  let id = "";
  for (let i = 0; i < 32; i += 1) {
    id += hex[Math.floor(Math.random() * 16)];
    if (i === 7 || i === 11 || i === 15 || i === 19) id += "-";
  }
  return id;
}

/**
 * Gera um evento compatível com BaseEvent do worker.
 * O campo correto na ingestão é `timestamp`; `occurred_at` pertence à leitura.
 */
export function gerarEvento(overrides = {}) {
  const tipo = overrides.event_name || EVENT_TYPES[inteiroAleatorio(0, EVENT_TYPES.length - 1)];
  const plataforma = PLATFORMS[inteiroAleatorio(0, PLATFORMS.length - 1)];

  const evento = {
    timestamp: new Date().toISOString(),
    event_name: tipo,
    session_id: uuid(),
    device_id: uuid(),
    device_os: OS_LIST[inteiroAleatorio(0, OS_LIST.length - 1)],
    device_manufacturer: plataforma.includes("apple") || plataforma === "ios" ? "Apple" : "Samsung",
    device_model: `K6-${inteiroAleatorio(1, 50)}`,
    app_target: plataforma,
    app_version: `${inteiroAleatorio(1, 5)}.${inteiroAleatorio(0, 9)}.${inteiroAleatorio(0, 20)}`,
    app_env: "load_test",
    route_path: `/player/content-${inteiroAleatorio(1000, 9999)}`,
    load_test_id: TEST_ID,
  };

  if (tipo === "request") {
    evento.request_method = "GET";
    evento.request_url = "/player/content";
    evento.request_status = [200, 200, 200, 404, 500][inteiroAleatorio(0, 4)];
    evento.duration = inteiroAleatorio(10, 5000) / 1000;
  } else if (tipo === "video_view") {
    evento.media_id = `video-${inteiroAleatorio(1, 500)}`;
    evento.media_kind = "vod";
    evento.duration = inteiroAleatorio(1, 300);
  } else if (tipo === "error") {
    evento.error_name = `ERR-${inteiroAleatorio(100, 599)}`;
    evento.error_message = "Synthetic event from the k6 load test";
  } else if (tipo === "vitals") {
    evento.action = "heartbeat";
    evento.duration = inteiroAleatorio(1, 50) / 10;
  }

  return Object.assign(evento, overrides);
}

export function headersIngestao() {
  const headers = { "Content-Type": "application/json" };
  if (INGEST_TOKEN) headers.Authorization = `Bearer ${INGEST_TOKEN}`;
  return headers;
}

export function headersLeitura() {
  const headers = {};
  if (READ_TOKEN) headers.Authorization = `Bearer ${READ_TOKEN}`;
  return headers;
}

function endpointLocal(url) {
  return /^https?:\/\/(localhost|127\.0\.0\.1)(:|\/|$)/.test(url);
}

/** Falha antes da carga se a configuração produziria uma execução sem alvo. */
export function validarConfiguracao({ ingestao = false, leitura = false } = {}) {
  if (ingestao) {
    if (!/^https?:\/\//.test(INGEST_ENDPOINT)) {
      throw new Error("ARGUS_INGEST_URL é obrigatória e deve ser o endpoint completo .../v1/events");
    }
    if (!endpointLocal(INGEST_ENDPOINT) && !INGEST_TOKEN) {
      throw new Error("ARGUS_INGEST_TOKEN é obrigatório para a API de ingestão publicada");
    }
  }

  if (leitura) {
    if (!/^https?:\/\//.test(READ_URL)) {
      throw new Error("ARGUS_API_URL é obrigatória e deve ser a URL base da API de leitura");
    }
    if (!endpointLocal(READ_URL) && !READ_TOKEN) {
      throw new Error("ARGUS_READ_TOKEN é obrigatório para a API de leitura publicada");
    }
  }
}

export function numero(metrica, campo, fallback = 0) {
  const valor = metrica && metrica.values ? metrica.values[campo] : undefined;
  return typeof valor === "number" && Number.isFinite(valor) ? valor : fallback;
}

export function taxaSucesso(metricaFalhas) {
  return (1 - numero(metricaFalhas, "rate", 1)) * 100;
}
