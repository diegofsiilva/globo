import styles from "../dashboard.module.css";

type MetricProps = {
  label: string;
  value: string;
};

/** Valor destacado acompanhado de um rótulo. */
export function Metric({ label, value }: MetricProps) {
  return (
    <div className={styles.metric}>
      <strong>{value}</strong>
      <span>{label}</span>
    </div>
  );
}
