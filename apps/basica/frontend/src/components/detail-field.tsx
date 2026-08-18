type DetailFieldProps = {
  label: string;
  value: string;
};

/** Campo rotulado reutilizável em painéis de detalhes. */
export function DetailField({ label, value }: DetailFieldProps) {
  return (
    <span>
      <small>{label}</small>
      <b>{value}</b>
    </span>
  );
}
