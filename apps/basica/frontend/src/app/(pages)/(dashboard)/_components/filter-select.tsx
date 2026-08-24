type FilterSelectProps = {
  label: string;
  labels?: Record<string, string>;
  onChange: (value: string) => void;
  options: string[];
  value: string;
};

/** Seletor reutilizável da barra de filtros. */
export function FilterSelect({
  label,
  labels = {},
  onChange,
  options,
  value,
}: FilterSelectProps) {
  return (
    <label className="scope-select">
      <span>{label}</span>
      <select value={value} onChange={(event) => onChange(event.target.value)}>
        <option value="all">todos</option>
        {options.map((option) => (
          <option key={option} value={option}>
            {labels[option] ?? option}
          </option>
        ))}
      </select>
    </label>
  );
}
