/** Moldura comum das seis etapas operacionais. */
export const screenFrameStyles = {
  content:
    "min-w-0 max-w-full px-3 pb-12 sm:px-4 md:px-6 md:pb-16 xl:px-8",
  filter:
    "grid min-h-10 grid-cols-[minmax(5.5rem,auto)_minmax(0,1fr)] items-center gap-2 border border-border bg-background pl-3 [&>span]:font-mono [&>span]:text-[12px] [&>span]:uppercase [&>span]:tracking-[0.06em] [&>span]:text-muted-foreground md:flex md:min-h-9 md:pl-2 md:[&>span]:text-[11px]",
  filterList: "grid w-full gap-3 md:flex md:w-max md:items-center md:gap-1.5",
  mobileScope: "sticky top-24 z-[15] border-b border-border bg-surface/95 p-3 backdrop-blur-md md:hidden",
  page: "contents font-[variant-numeric:tabular-nums]",
  scopeBar:
    "sticky top-12 z-[15] hidden min-h-12 w-full min-w-0 max-w-full items-center gap-2 overflow-hidden border-b border-border bg-surface/95 px-5 py-1.5 backdrop-blur-md md:flex",
  scopeControls:
    "flex min-w-0 flex-1 items-center gap-1.5 overflow-x-auto [scrollbar-width:thin] [&>*]:shrink-0",
  scopeLabel:
    "shrink-0 font-mono text-[11px] font-semibold uppercase tracking-[0.1em] text-muted-foreground",
  scopeMeta:
    "ml-auto flex min-w-0 shrink-0 items-center gap-2 whitespace-nowrap font-mono text-[11px] text-muted-foreground [&>span]:hidden xl:[&>span]:block",
} as const;
