/** Moldura comum das seis etapas operacionais. */
export const screenFrameStyles = {
  content:
    "min-w-0 max-w-full px-3 pb-12 sm:px-4 md:px-6 md:pb-16 xl:px-8",
  filter:
    "flex min-h-9 items-center gap-2 border border-border bg-background pl-2 [&>span]:font-mono [&>span]:text-[8px] [&>span]:uppercase [&>span]:tracking-[0.08em] [&>span]:text-muted-foreground",
  filterList: "flex w-max items-center gap-1.5",
  liveStatus:
    "m-0 flex items-center gap-2 whitespace-nowrap font-mono text-[9px] font-medium uppercase tracking-[0.11em] text-primary [&>span]:size-1.5 [&>span]:shrink-0 [&>span]:bg-primary [&>span]:animate-agora-live-pulse motion-reduce:[&>span]:animate-none",
  page: "contents font-[variant-numeric:tabular-nums]",
  periods:
    "ml-auto shrink-0 bg-background [&_[data-slot=toggle-group-item]]:h-8 [&_[data-slot=toggle-group-item]]:min-h-8 [&_[data-slot=toggle-group-item]]:min-w-11 [&_[data-slot=toggle-group-item]]:px-2.5",
  scopeBar:
    "flex min-h-12 w-full min-w-0 max-w-full items-center gap-2 overflow-hidden border-b border-border bg-surface/85 px-3 py-1.5 backdrop-blur-md md:px-5",
  scopeControls:
    "flex min-w-0 flex-1 items-center gap-1.5 overflow-x-auto [scrollbar-width:thin] [&>*]:shrink-0",
  scopeLabel:
    "shrink-0 font-mono text-[8px] font-semibold uppercase tracking-[0.11em] text-muted-foreground",
  scopeMeta:
    "ml-auto flex min-w-0 shrink-0 items-center gap-2 whitespace-nowrap font-mono text-[8px] text-muted-foreground [&>span]:hidden xl:[&>span]:block",
  topControls:
    "flex min-h-11 w-full min-w-0 max-w-full items-center gap-3 border-b border-border bg-background/94 px-3 md:min-h-10 md:px-5",
} as const;
