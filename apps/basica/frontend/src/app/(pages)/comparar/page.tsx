"use client";

/** Tela 03 — Comparar: a janela atual contra referências históricas. */

import { useState } from "react";
import { ScreenFrame, type ScreenPeriod } from "@/components/screen-frame";
import styles from "./comparar.module.css";

/** Itens que a tela precisa apresentar quando for implementada. */
const planned = [
  {
    title: "Quatro referências de comparação",
    description:
      "Ontem no mesmo horário, semana passada, última janela estável e pico ao vivo anterior — escalas distintas de sazonalidade, incluindo o caso do evento programado.",
  },
  {
    title: "Tabela de métricas com significância",
    description:
      "Além do delta, a distância em desvios-padrão: é ela que hierarquiza 14,2σ na falha de play contra 1,2σ no p95 de borda.",
  },
  {
    title: "Eventos de infraestrutura entre as janelas",
    description:
      "Painel lateral em ordem cronológica, ligando o que mudou ao que se moveu.",
  },
];

/** Janela atual contra referências históricas, com significância estatística */
export default function CompararPage() {
  const [period, setPeriod] = useState<ScreenPeriod>("30 min");

  return (
    <ScreenFrame period={period} onPeriodChange={setPeriod}>
      <header className={styles.header}>
        <h1>Comparar</h1>
        <p>o desvio é anomalia ou sazonalidade esperada</p>
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
          Especificação em artefatos/entendimento_ux.md §5.3.3.
        </p>
      </section>
    </ScreenFrame>
  );
}
