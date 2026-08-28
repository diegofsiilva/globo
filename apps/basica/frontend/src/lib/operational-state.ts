/** Como uma consulta falhou. Cada categoria leva a um desfecho diferente na tela. */
export type QueryFailureKind =
  | "offline"
  | "timeout"
  | "server"
  // 401/403 da API. Categoria própria porque o desfecho é diferente de todas as
  // outras: não adianta tentar de novo, o operador precisa colar o token
  // novamente. O `ScreenFrame` não chega a renderizar este estado — o portão de
  // acesso intercepta antes —, mas o tipo existe para que uma falha de
  // autenticação nunca seja contada como "servidor fora".
  | "unauthorized"
  | "invalid-response"
  | "unknown";

/**
 * Uma falha de consulta pronta para exibição.
 *
 * `reference` é o código que o operador cita ao relatar o problema; ele carrega
 * o `X-Request-Id` da resposta, que é o mesmo que está na linha de log da API.
 *
 * `lastSuccessAt` separa "nunca carregou" de "está exibindo dado de dois
 * minutos atrás" -- a segunda situação ainda é utilizável, e a tela precisa
 * dizer isso em vez de esvaziar.
 */
export type QueryFailure = {
  kind: QueryFailureKind;
  cause: string;
  reference: string;
  occurredAt: string;
  lastSuccessAt?: string;
  retryable: boolean;
};

/** Erro tipado usado pelos adapters de consulta sem alterar o contrato de sucesso. */
export class QuerySourceError extends Error {
  constructor(
    message: string,
    readonly kind: QueryFailureKind,
    readonly reference: string,
    readonly retryable = true,
  ) {
    super(message);
    this.name = "QuerySourceError";
  }
}

/**
 * Converte qualquer erro no formato que a moldura sabe exibir.
 *
 * @param error Erro capturado. `QuerySourceError` preserva a classificação;
 *   qualquer outro vira `unknown` e retryable.
 * @param lastSuccessAt Horário do último sucesso, quando houve.
 * @returns A falha normalizada.
 */
export function normalizeQueryFailure(
  error: unknown,
  lastSuccessAt?: string,
): QueryFailure {
  const occurredAt = new Intl.DateTimeFormat("pt-BR", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(new Date());

  if (error instanceof QuerySourceError) {
    return {
      kind: error.kind,
      cause: error.message,
      reference: error.reference,
      occurredAt,
      lastSuccessAt,
      retryable: error.retryable,
    };
  }

  return {
    kind: "unknown",
    cause: error instanceof Error ? error.message : "A consulta não retornou uma resposta utilizável.",
    reference: "ARG-QUERY-UNKNOWN",
    occurredAt,
    lastSuccessAt,
    retryable: true,
  };
}
