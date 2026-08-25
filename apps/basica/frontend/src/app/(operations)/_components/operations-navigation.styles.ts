/** Utilities Tailwind geradas a partir do CSS legado para preservar paridade visual. */
export const navigationStyles = {
  "active": "active [box-shadow:inset_2px_0_var(--red)] [background:#fff]",
  "badge": "badge [min-width:15px] [height:15px] [padding:0_3px] [display:grid] [place-items:center] [background:var(--red)] [color:white] [font-size:8px] [font-weight:700] [font-variant-numeric:tabular-nums]",
  "index": "index [color:var(--soft)] [font-size:8px] [font-variant-numeric:tabular-nums]",
  "label": "label [font-size:11px] [font-weight:600]",
  "link": "link [min-height:48px] [padding:0_12px_0_9px] [display:grid] [grid-template-columns:22px_1fr_18px] [align-items:center] [border-bottom:1px_solid_var(--line-soft)] [box-shadow:inset_2px_0_transparent] [color:var(--ink)] [text-decoration:none] [transition:background-color_160ms_ease,box-shadow_160ms_ease] hover:[background:rgba(255,255,255,0.55)] focus-visible:[position:relative] focus-visible:[z-index:1] focus-visible:[outline:2px_solid_var(--ink)] focus-visible:[outline-offset:-2px] max-[760px]:[width:118px] max-[760px]:[min-height:48px] max-[760px]:[border-right:1px_solid_var(--line-soft)] max-[760px]:[border-bottom:0] motion-reduce:[transition:none]",
  "list": "list [position:sticky] [top:0] [margin:0] [padding:0] [list-style:none] max-[760px]:[position:static] max-[760px]:[display:flex] max-[760px]:[width:max-content]",
  "navigation": "navigation [min-width:150px] [border-right:1px_solid_var(--line)] [background:rgba(255,255,255,0.12)] max-[760px]:[min-width:0] max-[760px]:[overflow-x:auto] max-[760px]:[border-right:0] max-[760px]:[border-bottom:1px_solid_var(--line)] max-[760px]:[scrollbar-width:thin]",
} as const;
