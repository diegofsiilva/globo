/** Utilities da navegação operacional em sidebar e drawer. */
export const navigationStyles = {
  active:
    "bg-[image:var(--gradient-emphasis-soft)] text-foreground shadow-[inset_2px_0_var(--primary)] before:absolute before:right-0 before:h-5 before:w-px before:bg-primary",
  drawer: "p-0",
  drawerNavigation: "flex-1 py-3",
  index: "font-mono text-[12px] text-muted-foreground tabular-nums",
  label: "text-[13px] font-semibold",
  link:
    "relative grid min-h-12 grid-cols-[26px_1fr] items-center gap-2 border-b border-border px-3 text-muted-foreground no-underline transition-[background-color,color,box-shadow] duration-[160ms] hover:bg-surface-raised hover:text-foreground focus-visible:z-10 focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-ring motion-reduce:transition-none",
  list: "m-0 list-none p-0",
  menuButton: "md:hidden",
  navigation:
    "hidden h-full min-w-44 overflow-y-auto overscroll-contain border-r border-border bg-surface/65 backdrop-blur-[6px] md:block",
} as const;
