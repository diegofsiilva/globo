/** Utilities Tailwind geradas a partir do CSS legado para preservar paridade visual. */
export const operationsLayoutStyles = {
  "appShell": "appShell [min-height:100vh] [position:relative]",
  "brand": "brand [display:flex] [align-items:center] [gap:9px] [text-transform:uppercase] [&_strong]:[font-size:12px] [&_strong]:[letter-spacing:1.08px] [&_strong]:[white-space:nowrap] [&_span]:[color:var(--soft)] [&_span]:[font-size:12px] [&_span]:[letter-spacing:0.72px] [&_span]:[white-space:nowrap] max-[900px]:[&_span]:[display:none]",
  "brandMark": "brandMark [width:13px] [height:13px] [flex:none] [background:var(--red)]",
  "navigationSlot": "navigationSlot [min-width:0] [grid-column:1] [grid-row:3] max-[760px]:[grid-column:1] max-[760px]:[grid-row:3]",
  "routeGrid": "routeGrid [display:grid] [grid-template-columns:150px_minmax(0,1fr)] [grid-template-rows:auto_auto_minmax(0,1fr)] [min-height:calc(100vh_-_52px)] [&_[data-operations-slot=\"controls\"]]:[grid-column:1_/_-1] [&_[data-operations-slot=\"scope\"]]:[grid-column:1_/_-1] [&_[data-operations-slot=\"controls\"]]:[grid-row:1] [&_[data-operations-slot=\"scope\"]]:[grid-row:2] [&_[data-operations-slot=\"content\"]]:[min-width:0] [&_[data-operations-slot=\"content\"]]:[grid-column:2] [&_[data-operations-slot=\"content\"]]:[grid-row:3] max-[760px]:[grid-template-columns:minmax(0,1fr)] max-[760px]:[grid-template-rows:auto_auto_auto_minmax(0,1fr)] max-[760px]:[&_[data-operations-slot=\"content\"]]:[grid-column:1] max-[760px]:[&_[data-operations-slot=\"content\"]]:[grid-row:4]",
  "siteHeader": "siteHeader [height:52px] [padding:0_20px] [display:flex] [align-items:center] [border-bottom:1px_solid_var(--line)] max-[760px]:[padding:0_12px]",
  "skipLink": "skipLink [position:fixed] [top:8px] [left:8px] [z-index:1000] [padding:10px_14px] [transform:translateY(-150%)] [background:var(--ink)] [color:#fff] [font-size:12px] [font-weight:600] [text-decoration:none] focus:[transform:translateY(0)]",
} as const;
