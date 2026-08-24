"use client";

/** Tela 06 — Recorte: a população afetada, declarada e ajustável. */

import { useState } from "react";
import { ScreenFrame, type ScreenPeriod } from "@/components/screen-frame";
import styles from "./recorte.module.css";

/** Itens que a tela precisa apresentar quando for implementada. */
const planned = [
  {
    title: "Recorte declarado em quatro dimensões",
    description:
      "Plataforma, fabricante, região e versão, com a população nomeada em vez de implícita no filtro.",
  },
  {
    title: "Tráfego contra erros",
    description:
      "A relação que mostra concentração em vez de degradação geral: 3,1% do tráfego concentra 94% dos erros.",
  },
  {
    title: "Ajuste do recorte",
    description:
      "Alargar ou estreitar cada dimensão e ver o contraste se mover.",
  },
  {
    title: "Entrada vinda de Hipóteses",
    description:
      "A tela recebe ?hipotese e ?segmento na URL e deve abrir com esse recorte aplicado.",
  },
];

/** Definição explícita e ajuste da população afetada */
export default function RecortePage() {
  const [period, setPeriod] = useState<ScreenPeriod>("30 min");

  return (
    <ScreenFrame period={period} onPeriodChange={setPeriod}>
      <header className={styles.header}>
        <h1>Recorte</h1>
        <p>quem exatamente está sendo afetado</p>
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
          Especificação em artefatos/entendimento_ux.md §5.3.6.
        </p>
      </section>
    </ScreenFrame>
  );
}
