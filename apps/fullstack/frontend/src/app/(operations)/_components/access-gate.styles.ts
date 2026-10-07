/** Tela de acesso: pede o token de leitura antes de montar a moldura. */
export const accessGateStyles = {
  screen:
    "flex min-h-dvh items-center justify-center bg-background px-4 py-10 text-foreground",
  card: "w-full max-w-md",
  brand:
    "mb-6 flex items-center gap-2.5 uppercase [&_strong]:text-[11px] [&_strong]:font-bold [&_strong]:tracking-[0.09em] [&_span]:font-mono [&_span]:text-[11px] [&_span]:tracking-[0.12em] [&_span]:text-muted-foreground",
  brandMark: "size-3 shrink-0 rounded-mark bg-primary",
  title: "m-0 text-subhead font-semibold",
  intro: "mt-2 mb-6 text-body text-muted-foreground",
  field: "flex flex-col gap-2",
  label: "text-label font-medium",
  // `font-mono` porque o token é hexadecimal: em fonte proporcional o operador
  // não distingue o que colou, e um caractere a mais passa despercebido.
  input: "font-mono",
  hint: "m-0 text-micro text-muted-foreground",
  actions: "mt-5 flex items-center gap-3",
  error: "mt-4",
  footer: "mt-8 border-t border-border pt-4 text-micro text-muted-foreground",
} as const;
