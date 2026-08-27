import { screenTitle } from "../../_components/screen-frame.styles";

/** Utilities Tailwind geradas a partir do CSS legado para preservar paridade visual. */
export const hipotesesStyles = {
  "action": "action [min-height:36px] [padding:0_17px] [display:inline-flex] [align-items:center] [border:1px_solid_var(--border-strong)] text-foreground text-micro font-semibold [text-decoration:none] hover:bg-surface focus-visible:[outline:2px_solid_var(--primary)] focus-visible:[outline-offset:2px]",
  "actions": "actions [display:flex] [gap:10px] [flex-wrap:wrap]",
  "body": "body [min-width:0] [display:flex] [flex-direction:column] [gap:5px]",
  "discarded": "discarded [margin-top:22px] [padding-top:16px] [border-top:1px_solid_var(--border)] [&_>_p]:[margin:0_0_10px] [&_>_p]:text-subtle-foreground [&_>_p]:text-micro [&_>_p]:font-semibold [&_>_p]:[letter-spacing:0.08em] [&_>_p]:[text-transform:uppercase] [&_ul]:[margin:0] [&_ul]:[padding:0] [&_ul]:[list-style:none] [&_li]:[padding:8px_0] [&_li]:[display:grid] [&_li]:[grid-template-columns:38px_minmax(0,1fr)] [&_li]:[gap:12px] [&_li]:[align-items:baseline] [&_li]:[border-bottom:1px_solid_var(--border-soft)] [&_b]:text-subtle-foreground [&_b]:text-micro [&_b]:[font-variant-numeric:tabular-nums] [&_span]:text-muted-foreground [&_span]:text-micro [&_span]:[line-height:1.45] [&_strong]:text-foreground [&_strong]:text-micro",
  "error": "error text-primary-hover",
  "evidence": "evidence [margin:0_0_24px] [padding:0] [list-style:none] [&_li]:[padding:9px_0] [&_li]:[display:flex] [&_li]:[align-items:baseline] [&_li]:[justify-content:space-between] [&_li]:[gap:16px] [&_li]:[border-bottom:1px_solid_var(--border-soft)] [&_li]:text-micro [&_b]:[font-weight:400] [&_span]:text-muted-foreground [&_span]:[text-align:right] max-[700px]:[&_li]:[flex-direction:column] max-[700px]:[&_li]:[gap:3px] max-[700px]:[&_span]:[text-align:left]",
  "factorHead": "factorHead [display:flex] [align-items:baseline] [justify-content:space-between] [gap:14px] [&_strong]:text-micro [&_span]:[flex:none] [&_span]:text-subtle-foreground [&_span]:text-micro [&_span]:[font-variant-numeric:tabular-nums]",
  "factors": "factors [margin:0_0_26px] [padding:0] [list-style:none] [&_li]:[padding:12px_0_14px] [&_li]:[border-top:1px_solid_var(--border-soft)] [&_li:first-child]:[border-top:0] [&_p]:[margin:0] [&_p]:text-muted-foreground [&_p]:text-micro [&_p]:[line-height:1.5]",
  "header": `header [padding:22px_4px_14px] [display:flex] [align-items:baseline] [gap:12px] [flex-wrap:wrap] [&_p]:[margin:0] [&_p]:text-muted-foreground [&_p]:text-micro ${screenTitle}`,
  "item": "item [width:100%] [min-height:64px] [padding:16px_14px_15px_12px] [display:grid] [grid-template-columns:64px_minmax(0,1fr)] [align-items:start] [gap:12px] [border-bottom:1px_solid_var(--border-soft)] bg-transparent text-foreground [text-align:left] [cursor:pointer] [transition:background-color_160ms_ease] hover:bg-surface-raised focus-visible:[outline:2px_solid_var(--primary)] focus-visible:[outline-offset:-2px] max-[700px]:[grid-template-columns:48px_minmax(0,1fr)] max-[700px]:[padding:14px_4px] motion-reduce:[transition:none]",
  "kicker": "kicker text-subtle-foreground text-micro font-semibold [letter-spacing:0.09em] [text-transform:uppercase]",
  "layout": "layout [display:grid] [grid-template-columns:minmax(0,1.02fr)_minmax(0,1fr)] [align-items:start] [gap:26px] [padding-bottom:40px] max-[1100px]:[grid-template-columns:1fr] max-[1100px]:[gap:30px]",
  "list": "list [&_ol]:[margin:0] [&_ol]:[padding:0] [&_ol]:[list-style:none] [&_ol]:[border-top:1px_solid_var(--border)]",
  "meter": "meter [margin:7px_0_8px] [height:5px] bg-surface-raised [&_i]:[display:block] [&_i]:[height:100%] [&_i]:[background-image:var(--gradient-emphasis)]",
  "panel": "panel [position:sticky] [top:14px] [padding-top:16px] [border-top:1px_solid_var(--border)] [&_h2]:[margin:0_0_18px] [&_h2]:text-section [&_h2]:[line-height:1.25] [&_h2]:font-semibold [&_h2]:[letter-spacing:-0.2px] max-[1100px]:[position:static]",
  "panelKicker": "panelKicker [margin:0_0_8px] text-subtle-foreground text-micro font-semibold [letter-spacing:0.09em] [text-transform:uppercase]",
  "panelScore": "panelScore [margin:0_0_22px] [display:flex] [align-items:baseline] [gap:14px] [&_strong]:text-display [&_strong]:[line-height:1] [&_strong]:[font-variant-numeric:tabular-nums] [&_span]:text-muted-foreground [&_span]:text-micro",
  "primary": "primary [border-color:var(--primary)] bg-primary text-primary-foreground hover:bg-primary-hover hover:[border-color:var(--primary-hover)]",
  "score": "score text-display [line-height:0.9] [text-align:right] [font-variant-numeric:tabular-nums] max-[700px]:text-display",
  "selected": "selected [box-shadow:inset_3px_0_var(--primary)] bg-surface [border-bottom-color:var(--border)]",
  "state": "state [margin:0] [padding:30px_0] [border-top:1px_solid_var(--border-soft)] text-muted-foreground text-micro",
  "strip": "strip [margin-top:6px] [display:flex] [gap:3px] [height:6px] [&_i]:[height:100%] [&_i]:[min-width:2px]",
  "title": "title text-section [line-height:1.2] font-semibold [letter-spacing:-0.2px] max-[700px]:text-body",
} as const;
