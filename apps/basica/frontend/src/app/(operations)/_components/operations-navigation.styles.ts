/** Utilities da navegação operacional em sidebar e drawer. */
export const navigationStyles = {
  active:
    "bg-[color-mix(in_srgb,var(--primary)_10%,transparent)] text-foreground shadow-[inset_2px_0_var(--primary)] before:absolute before:right-0 before:h-5 before:w-px before:bg-primary",
  badge:
    "min-w-5 border-0 px-1.5 py-0.5 text-[11px] tracking-normal [border-radius:999px]",
  drawer: "p-0",
  drawerNavigation: "flex-1 py-3",
  index: "font-mono text-[11px] text-muted-foreground tabular-nums",
  label: "text-[11px] font-semibold",
  link:
    "relative grid min-h-12 grid-cols-[24px_1fr_auto] items-center gap-2 border-b border-border px-3 text-muted-foreground no-underline transition-[background-color,color,box-shadow] duration-[160ms] hover:bg-surface-raised hover:text-foreground focus-visible:z-10 focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-ring motion-reduce:transition-none",
  list: "m-0 list-none p-0",
  menuButton: "md:hidden",
  navigation:
    "hidden h-full min-w-44 overflow-y-auto overscroll-contain border-r border-border bg-surface/65 backdrop-blur-[6px] md:block",
} as const;
