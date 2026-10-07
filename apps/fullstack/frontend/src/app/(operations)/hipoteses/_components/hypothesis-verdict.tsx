"use client";

/** Veredito do operador sobre a hipótese selecionada. */

import { useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { normalizeQueryFailure } from "@/lib/operational-state";
import { submitHypothesisFeedback, type Verdict } from "../_lib/feedback";
import type { Hypothesis } from "../_lib/types";
import { hipotesesStyles as styles } from "./hipoteses.styles";

/** Os três vereditos da rota, com o rótulo do botão e o do estado gravado. */
const VERDICTS: ReadonlyArray<{ value: Verdict; label: string; done: string }> = [
  { value: "confirmed", label: "Confirmo", done: "confirmada" },
  { value: "partially_confirmed", label: "Confirmo em parte", done: "parcialmente confirmada" },
  { value: "rejected", label: "Rejeito", done: "rejeitada" },
];

/**
 * Registra se a hipótese se confirmou.
 *
 * A hipótese é uma explicação candidata para revisão humana, e não uma
 * causa-raiz. Sem este controle a revisão não tinha onde acontecer: a rota de
 * feedback existia e nenhuma tela a chamava.
 *
 * @param hypothesis Hipótese selecionada no painel.
 */
export function HypothesisVerdict({ hypothesis }: { hypothesis: Hypothesis }) {
  const queryClient = useQueryClient();
  const [note, setNote] = useState("");
  // Uma chave por conteúdo enviado. Repetir o clique depois de um timeout
  // reaproveita a chave e a API devolve o registro já gravado; mudar o veredito
  // ou a observação é outro conteúdo, e ganha outra chave.
  const keys = useRef(new Map<string, string>());

  const feedback = useMutation({
    mutationFn: (verdict: Verdict) => {
      const text = note.trim();
      const content = `${verdict}|${text}`;
      const key = keys.current.get(content) ?? crypto.randomUUID();
      keys.current.set(content, key);
      return submitHypothesisFeedback(hypothesis.id, verdict, key, text || undefined);
    },
    // A lista carrega `review_status`: reconsultar é o que faz o item e o
    // filtro de revisão refletirem o veredito recém-gravado.
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["hypotheses"] }),
  });

  const submitted = feedback.isSuccess
    ? VERDICTS.find((verdict) => verdict.value === feedback.variables)?.done
    : undefined;
  const registered =
    submitted ?? (hypothesis.reviewStatus !== "não revisada" ? hypothesis.reviewStatus : undefined);
  const failure = feedback.isError ? normalizeQueryFailure(feedback.error) : null;

  return (
    <section className={styles.verdict} aria-label="Veredito do operador">
      <p className={styles.panelKicker}>Esta hipótese se confirmou?</p>
      <p role="status">
        {registered ? (
          <>Registrada como <strong>{registered}</strong>.</>
        ) : (
          "Ainda sem revisão."
        )}
      </p>
      <Input
        value={note}
        onChange={(event) => setNote(event.target.value)}
        placeholder="Observação (opcional)"
        aria-label="Observação sobre o veredito"
        maxLength={2000}
        disabled={feedback.isPending}
      />
      <div className={styles.actions}>
        {VERDICTS.map((verdict) => (
          <Button
            key={verdict.value}
            type="button"
            variant="outline"
            size="sm"
            disabled={feedback.isPending}
            aria-pressed={registered === verdict.done}
            onClick={() => feedback.mutate(verdict.value)}
          >
            {feedback.isPending && feedback.variables === verdict.value ? "Registrando…" : verdict.label}
          </Button>
        ))}
      </div>
      {failure && (
        <p role="alert">
          {failure.cause} <small>Referência: {failure.reference}</small>
        </p>
      )}
      <small>
        O token identifica o serviço, e não a pessoa: o veredito fica gravado sem autoria.
      </small>
    </section>
  );
}
