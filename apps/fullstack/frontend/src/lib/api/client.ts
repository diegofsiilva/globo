/**
 * Cliente HTTP compartilhado por todos os adapters do dashboard.
 *
 * Antes existiam seis cópias do mesmo `fetch` + tratamento de erro, uma por
 * tela. Com autenticação isso deixou de ser só repetição: cada cópia seria um
 * lugar a mais onde esquecer o header, e a tela esquecida falharia com 401 num
 * momento em que o resto do dashboard funciona — o tipo de defeito que passa
 * despercebido até a demonstração.
 *
 * Três responsabilidades, e nenhuma delas cabe nas telas:
 *
 * 1. Acrescentar `Authorization: Bearer` a toda requisição.
 * 2. Derrubar a sessão em 401/403, para que o portão de acesso volte a pedir o
 *    token em vez de deixar seis telas mostrando "erro do servidor".
 * 3. Traduzir falha de rede, timeout e resposta não-JSON em `QuerySourceError`
 *    tipado, que é o que `ScreenFrame` usa para escolher o estado operacional.
 */

import { QuerySourceError } from "@/lib/operational-state";
import { lerToken, limparToken } from "./session";

/**
 * URL base da API, injetada em tempo de build. Nunca escrita no código —
 * ver `frontend/AGENTS.md`, regra 1.
 */
export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "";

/**
 * Cabeçalho de correlação. A API devolve o mesmo valor que registra no log
 * estruturado; expor na interface permite que o operador cite um identificador
 * ao relatar uma falha, em vez de "deu erro por volta das duas".
 */
export const CABECALHO_REQUEST_ID = "X-Request-Id";

/** Opções aceitas por {@link apiFetch}. */
export type ApiFetchOptions = {
  /** Aborta a requisição quando a tela é desmontada ou o filtro muda. */
  signal?: AbortSignal;
  /** Sufixo dos códigos de referência (`ARG-<tag>-HTTP-500`). */
  tag: string;
  /** Verbo HTTP. `POST` atende feedback e refinamento de hipótese. */
  method?: "GET" | "POST";
  /** Corpo já serializável em JSON. */
  body?: unknown;
};

/**
 * Faz uma requisição autenticada à API de leitura e devolve o JSON.
 *
 * @param path Caminho absoluto na API, começando com `/` (ex.:
 *   `/api/v1/signals?limit=25`).
 * @param options Ver {@link ApiFetchOptions}.
 * @returns O corpo da resposta, já convertido.
 * @throws {QuerySourceError} Em qualquer desfecho que não seja 2xx com JSON
 *   válido. O `kind` diz o que aconteceu; `unauthorized` significa que a sessão
 *   caiu e já foi limpa.
 */
export async function apiFetch<T>(path: string, options: ApiFetchOptions): Promise<T> {
  const { signal, tag, method = "GET", body } = options;

  if (!API_URL) {
    throw new QuerySourceError(
      "NEXT_PUBLIC_API_URL não está configurada no bundle.",
      "server",
      `ARG-${tag}-NO-URL`,
      false,
    );
  }

  const token = lerToken();
  if (!token) {
    throw new QuerySourceError(
      "Sessão sem token de acesso.",
      "unauthorized",
      `ARG-${tag}-SEM-TOKEN`,
      false,
    );
  }

  const headers: Record<string, string> = { Authorization: `Bearer ${token}` };
  if (body !== undefined) headers["Content-Type"] = "application/json";

  let response: Response;
  try {
    response = await fetch(`${API_URL.replace(/\/$/, "")}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal,
    });
  } catch (error) {
    // Aborto é fluxo normal (a tela trocou de filtro), não falha — precisa
    // subir intacto para o TanStack Query reconhecê-lo.
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new QuerySourceError(
      "A conexão com a API está indisponível. Verifique a rede e tente novamente.",
      "offline",
      `ARG-${tag}-OFFLINE`,
    );
  }

  const requestId = response.headers.get(CABECALHO_REQUEST_ID);
  const referencia = requestId ? `ARG-${tag}-${requestId}` : `ARG-${tag}`;

  if (response.status === 401 || response.status === 403) {
    // Limpar aqui, e não na tela, é o que faz o portão de acesso reagir a um
    // 401 vindo de QUALQUER consulta. Sem isso, a tela mostraria "erro do
    // servidor" e o operador continuaria clicando em "tentar de novo" com um
    // token que já não vale.
    limparToken();
    throw new QuerySourceError(
      response.status === 401
        ? "A sessão não enviou um token de acesso. Informe o token novamente."
        : "O token de acesso não é mais válido. Informe o token novamente.",
      "unauthorized",
      `${referencia}-HTTP-${response.status}`,
      false,
    );
  }

  if (!response.ok) {
    const timeout = response.status === 408 || response.status === 504;
    throw new QuerySourceError(
      timeout
        ? "A API excedeu o tempo limite da consulta."
        : `A API respondeu com status ${response.status}.`,
      timeout ? "timeout" : "server",
      `${referencia}-HTTP-${response.status}`,
      response.status >= 500 || timeout,
    );
  }

  try {
    return (await response.json()) as T;
  } catch {
    throw new QuerySourceError(
      "A API respondeu em um formato que a interface não reconhece.",
      "invalid-response",
      `${referencia}-INVALID-JSON`,
      false,
    );
  }
}

/**
 * Valida um token contra a API antes de abrir a sessão.
 *
 * Usada apenas pela tela de acesso. Bate numa rota barata e autenticada
 * (`/api/v1/clock`) para que um token errado vire uma mensagem na própria tela
 * de acesso, e não seis telas quebradas em seguida.
 *
 * Não usa {@link apiFetch} porque o token ainda não está na sessão — e não deve
 * estar antes de ser aceito.
 *
 * @param token Token colado pelo operador.
 * @returns `"ok"` quando a API aceita, `"recusado"` em 401/403 e `"indisponivel"`
 *   quando não foi possível concluir a verificação.
 */
export async function verificarToken(
  token: string,
): Promise<"ok" | "recusado" | "indisponivel"> {
  if (!API_URL) return "indisponivel";
  try {
    const response = await fetch(`${API_URL.replace(/\/$/, "")}/api/v1/clock`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (response.ok) return "ok";
    if (response.status === 401 || response.status === 403) return "recusado";
    return "indisponivel";
  } catch {
    return "indisponivel";
  }
}
