/** Shell compartilhado da monitoração, inspirado em consoles operacionais. */
export const operationsLayoutStyles = {
  appShell: "relative min-h-dvh overflow-x-clip bg-background text-foreground",
  brand:
    "flex min-w-0 items-center gap-2.5 uppercase [&_strong]:truncate [&_strong]:text-[11px] [&_strong]:font-bold [&_strong]:tracking-[0.09em] [&_span]:hidden [&_span]:font-mono [&_span]:text-[10px] [&_span]:tracking-[0.12em] [&_span]:text-muted-foreground sm:[&_span]:inline",
  brandMark:
    "size-3 shrink-0 bg-[linear-gradient(135deg,var(--primary),var(--warning))] shadow-[0_0_16px_color-mix(in_srgb,var(--primary)_34%,transparent)] [border-radius:3px]",
  headerActions: "ml-auto flex items-center gap-2",
  navigationSlot:
    "col-start-1 row-start-3 hidden min-w-0 md:block",
  routeGrid:
    "grid min-h-[calc(100dvh-48px)] grid-cols-[minmax(0,1fr)] grid-rows-[auto_auto_minmax(0,1fr)] [&_[data-operations-slot=controls]]:col-start-1 [&_[data-operations-slot=controls]]:row-start-1 [&_[data-operations-slot=scope]]:col-start-1 [&_[data-operations-slot=scope]]:row-start-2 [&_[data-operations-slot=content]]:col-start-1 [&_[data-operations-slot=content]]:row-start-3 [&_[data-operations-slot=content]]:min-w-0 md:grid-cols-[176px_minmax(0,1fr)] md:[&_[data-operations-slot=controls]]:col-span-2 md:[&_[data-operations-slot=scope]]:col-span-2 md:[&_[data-operations-slot=content]]:col-start-2",
  siteHeader:
    "relative z-20 flex h-12 items-center gap-2 border-b border-border bg-background/92 px-3 backdrop-blur-md md:px-5",
  skipLink:
    "fixed left-2 top-2 z-[100] -translate-y-[150%] border border-ring bg-foreground px-3.5 py-2.5 text-xs font-semibold text-background no-underline focus:translate-y-0",
} as const;
