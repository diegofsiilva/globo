/** Shell compartilhado da monitoração, inspirado em consoles operacionais. */
export const operationsLayoutStyles = {
  appShell: "relative min-h-dvh overflow-x-clip bg-background text-foreground",
  brand:
    "flex min-w-0 items-center gap-2.5 uppercase [&_strong]:truncate [&_strong]:text-[11px] [&_strong]:font-bold [&_strong]:tracking-[0.09em] [&_span]:hidden [&_span]:font-mono [&_span]:text-[10px] [&_span]:tracking-[0.12em] [&_span]:text-muted-foreground sm:[&_span]:inline",
  brandMark:
    "size-3 shrink-0 rounded-mark bg-primary",
  controlRow:
    "flex min-w-0 items-center justify-between gap-2 border-t border-border px-3 sm:justify-end md:border-0 md:px-0",
  identityRow: "flex min-w-0 items-center gap-2 px-3 md:px-0",
  liveStatus:
    "m-0 flex items-center gap-2 whitespace-nowrap font-mono text-[12px] font-medium uppercase tracking-[0.08em] text-primary md:text-[11px] [&>[data-live-dot]]:size-1.5 [&>[data-live-dot]]:shrink-0 [&>[data-live-dot]]:rounded-full [&>[data-live-dot]]:bg-primary [&>[data-live-dot]]:animate-agora-live-pulse motion-reduce:[&>[data-live-dot]]:animate-none",
  navigationSlot:
    "fixed bottom-0 left-0 top-24 z-10 hidden w-44 min-w-0 md:block",
  periods:
    "min-w-0 shrink bg-background [&_[data-slot=toggle-group-item]]:h-11 [&_[data-slot=toggle-group-item]]:min-h-11 [&_[data-slot=toggle-group-item]]:min-w-11 [&_[data-slot=toggle-group-item]]:px-2 sm:shrink-0 md:[&_[data-slot=toggle-group-item]]:h-8 md:[&_[data-slot=toggle-group-item]]:min-h-8",
  routeGrid:
    "grid min-h-dvh scroll-mt-24 grid-cols-[minmax(0,1fr)] grid-rows-[auto_minmax(0,1fr)] pt-24 [&_[data-operations-slot=scope]]:col-start-1 [&_[data-operations-slot=scope]]:row-start-1 [&_[data-operations-slot=content]]:col-start-1 [&_[data-operations-slot=content]]:row-start-2 [&_[data-operations-slot=content]]:min-w-0 md:scroll-mt-12 md:grid-cols-[176px_minmax(0,1fr)] md:pt-12 md:[&_[data-operations-slot=scope]]:col-span-2 md:[&_[data-operations-slot=content]]:col-start-2",
  siteHeader:
    "fixed inset-x-0 top-0 z-20 grid h-24 grid-rows-2 border-b border-border bg-background/94 backdrop-blur-md md:h-12 md:grid-cols-[minmax(0,1fr)_auto] md:grid-rows-1 md:items-center md:gap-4 md:px-5",
  skipLink:
    "fixed left-2 top-2 z-[100] -translate-y-[150%] rounded-control border border-ring bg-foreground px-3.5 py-2.5 text-xs font-semibold text-background no-underline focus:translate-y-0",
} as const;
