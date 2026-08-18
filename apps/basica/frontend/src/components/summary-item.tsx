type SummaryItemProps = {
  critical?: boolean;
  index: string;
  label: string;
  value: number;
};

/** Item numérico reutilizável do resumo lateral. */
export function SummaryItem({
  critical = false,
  index,
  label,
  value,
}: SummaryItemProps) {
  return (
    <div>
      <span>{index}</span>
      <b className={critical ? "critical" : undefined}>{value}</b>
      <small>{label}</small>
    </div>
  );
}
