export type QueryFailureKind =
  | "offline"
  | "timeout"
  | "server"
  | "invalid-response"
  | "unknown";

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
