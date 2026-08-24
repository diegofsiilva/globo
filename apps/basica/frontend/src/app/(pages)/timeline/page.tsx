"use client";

/** Tela 05 — Timeline: seis fontes sobre um eixo temporal único. */

import { useState } from "react";
import { ScreenFrame, type ScreenPeriod } from "@/components/screen-frame";
import styles from "./timeline.module.css";

/** Itens que a tela precisa apresentar quando for implementada. */
const planned = [
  {
    title: "Seis raias paralelas sobre um eixo",
    description:
      "As fontes que hoje vivem em ferramentas separadas, com a janela de correlação destacada.",
  },
  {
    title: "Cronologia reconstruída em texto",
    description:
      "Os mesmos fatos em lista, cada linha atribuída à fonte que a originou — é o que preserva a rastreabilidade.",
  },
  {
    title: "Números da janela de correlação",
    description:
      "Painel lateral com a antecedência em relação ao primeiro chamado, que é o valor da detecção proativa.",
  },
  {
    title: "Entrada vinda de Hipóteses",
    description:
      "A tela recebe ?hipotese e ?t na URL e deve abrir centrada nesse instante.",
  },
];

/** Seis fontes de telemetria e infraestrutura sobre um eixo temporal único */
export default function TimelinePage() {
  const [period, setPeriod] = useState<ScreenPeriod>("30 min");

  return (
    <ScreenFrame period={period} onPeriodChange={setPeriod}>
      <header className={styles.header}>
        <h1>Timeline</h1>
        <p>a sequência que sustenta a hipótese, fonte por fonte</p>
      </header>

      <section className={styles.pending} aria-label="Conteúdo previsto para esta tela">
        <p>Em construção</p>
        <ul>
          {planned.map((item) => (
            <li key={item.title}>
              <strong>{item.title}</strong>
              {item.description}
            </li>
          ))}
        </ul>
        <p className={styles.source}>
          Especificação em artefatos/entendimento_ux.md §5.3.5.
        </p>
      </section>
    </ScreenFrame>
  );
}
