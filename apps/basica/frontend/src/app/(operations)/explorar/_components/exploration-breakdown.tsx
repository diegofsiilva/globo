"use client";

import { useMemo, useState } from "react";
import clsx from "clsx";
import { Input } from "@/components/ui/input";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import {
  frequentErrors,
  type ExplorationRow,
  type GroupBy,
} from "../_mocks/scenario";
import { formatEvents, groupOptions } from "../_lib/exploration-config";
import { explorarStyles as styles } from "./explorar.styles";

type ExplorationBreakdownProps = {
  groupBy: GroupBy;
  maxEvents: number;
  onGroupByChange: (groupBy: GroupBy) => void;
  rows: ExplorationRow[];
  selectedEventName: string;
};

/** Agrupamento e busca de erros da etapa final da exploração. */
export function ExplorationBreakdown({
  groupBy,
  maxEvents,
  onGroupByChange,
  rows,
  selectedEventName,
}: ExplorationBreakdownProps) {
  const [search, setSearch] = useState("");
  const filteredErrors = useMemo(() => {
    const normalizedSearch = search.trim().toLocaleLowerCase("pt-BR");

    if (!normalizedSearch) return frequentErrors;

    return frequentErrors.filter((error) =>
      error.name.toLocaleLowerCase("pt-BR").includes(normalizedSearch),
    );
  }, [search]);

  return (
    <section className={styles.breakdownSection} aria-labelledby="breakdown-title">
      <header className={styles.breakdownHeader}>
        <div className={styles.sectionHeading}>
          <span className={styles.stepIndex}>03</span>
          <div>
            <h2 id="breakdown-title">Descubra onde o sinal se concentra</h2>
            <p>A tabela muda conforme a dimensão escolhida.</p>
          </div>
        </div>
        <div className={styles.groupBar} aria-label="Quebrar resultado por">
          <span>Quebrar por</span>
          <ToggleGroup
            type="single"
            value={groupBy}
            onValueChange={(value) => value && onGroupByChange(value as GroupBy)}
          >
            {groupOptions.map((option) => <ToggleGroupItem key={option} value={option}>{option}</ToggleGroupItem>)}
          </ToggleGroup>
        </div>
      </header>

      <div className={styles.results}>
        <div
          className={styles.distribution}
          tabIndex={0}
          role="region"
          aria-label={`Concentração de ${selectedEventName} por ${groupBy}`}
        >
          <table className={styles.distributionTable}>
            <caption>
              Eventos de {selectedEventName} agrupados por {groupBy}
            </caption>
            <thead>
              <tr>
                <th scope="col">{groupBy}</th>
                <th scope="col">Eventos</th>
                <th scope="col">
                  Taxa de erro<span className="sr-only">, percentual de eventos que apresentaram erro</span>
                </th>
                <th scope="col">
                  Volume relativo<span className="sr-only"> dentro deste agrupamento</span>
                </th>
                <th scope="col">vs. ontem</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => {
                const critical = row.errorRate >= 10;
                const width = Math.max(12, (row.events / maxEvents) * 96);

                return (
                  <tr key={row.label}>
                    <th scope="row">{row.label}</th>
                    <td>{formatEvents(row.events)}</td>
                    <td className={clsx(critical && styles.errorValue)}>
                      {row.errorRate.toLocaleString("pt-BR", {
                        maximumFractionDigits: 1,
                        minimumFractionDigits: 1,
                      })}
                      %
                      {critical && <small>alto</small>}
                    </td>
                    <td>
                      <span
                        className={styles.distributionBar}
                        role="img"
                        aria-label={`${Math.round(width)}% do maior volume deste grupo`}
                      >
                        <i
                          className={clsx(critical && styles.criticalFill)}
                          style={{ width: `${width}%` }}
                        />
                      </span>
                    </td>
                    <td className={clsx(critical && styles.errorValue)}>
                      {row.delta}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        <aside className={styles.errorsPanel} aria-labelledby="errors-title">
          <header className={styles.errorsHeader}>
            <span className={styles.stepIndex}>04</span>
            <div>
              <h2 id="errors-title">Entenda o que falhou</h2>
              <p>Veja quais mensagens explicam o recorte selecionado.</p>
            </div>
          </header>
          <label htmlFor="error-search">Filtrar erros pelo nome</label>
          <Input
            id="error-search"
            name="error-search"
            type="search"
            autoComplete="off"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Ex.: playback, timeout…"
          />
          <small className={styles.searchHint}>
            Procure por parte do nome técnico do erro.
          </small>
          <h3>Erros mais frequentes</h3>
          <div className={styles.errorList}>
            {filteredErrors.map((error) => (
              <article key={error.id}>
                <strong>{error.name}</strong>
                <span>
                  {error.count} · {error.share}
                </span>
              </article>
            ))}
            {filteredErrors.length === 0 && (
              <p className={styles.emptySearch}>Nenhum erro encontrado.</p>
            )}
          </div>
        </aside>
      </div>
    </section>
  );
}
