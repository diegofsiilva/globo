/** Registro do veredito do operador sobre uma hipótese gerada. */

import { apiFetch } from "@/lib/api/client";

/** Vereditos que `POST /api/v1/hypotheses/{id}/feedback` aceita. */
export type Verdict = "confirmed" | "partially_confirmed" | "rejected";

/**
 * Recibo da gravação.
 *
 * `reviewer_verified` vem sempre `false`: o token autentica o serviço, e não a
 * pessoa, então a API não tem como afirmar quem revisou.
 */
export type FeedbackReceipt = {
  feedback_id: number;
  created: boolean;
  reviewer_verified: boolean;
};

/** O mock não grava nada; o veredito só existe contra a API real. */
export const hypothesisFeedbackEnabled =
  process.env.NEXT_PUBLIC_HYPOTHESES_SOURCE === "api";

/**
 * Registra o veredito do operador.
 *
 * A rota é idempotente por `idempotency_key`: reenviar o mesmo par chave e
 * conteúdo devolve o registro já gravado em vez de duplicar a avaliação. Quem
 * chama mantém a chave enquanto o conteúdo for o mesmo.
 *
 * @param hypothesisId Hipótese avaliada.
 * @param verdict Veredito escolhido.
 * @param idempotencyKey UUID da tentativa.
 * @param note Observação livre, opcional (até 2000 caracteres).
 * @returns Recibo da gravação.
 */
export async function submitHypothesisFeedback(
  hypothesisId: string,
  verdict: Verdict,
  idempotencyKey: string,
  note?: string,
): Promise<FeedbackReceipt> {
  return apiFetch<FeedbackReceipt>(
    `/api/v1/hypotheses/${encodeURIComponent(hypothesisId)}/feedback`,
    {
      tag: "HYP-FEEDBACK",
      method: "POST",
      body: { verdict, idempotency_key: idempotencyKey, ...(note ? { note } : {}) },
    },
  );
}
