import { screenTitle } from "../../_components/screen-frame.styles";

/** Utilities Tailwind geradas a partir do CSS legado para preservar paridade visual. */
export const timelineStyles = {
  "neutral": "neutral",
  "accent": "accent text-primary!",
  "axis": "axis [height:43px] [margin-left:150px] [padding-bottom:7px] [display:flex] [align-items:end] [justify-content:space-between] text-muted-foreground text-micro",
  "band": "band [position:absolute] [z-index:0] [top:43px] [bottom:0] [left:63.4%] [width:14%] [background:color-mix(in_srgb,var(--primary)_12%,transparent)] [border-inline:1px_solid_color-mix(in_srgb,var(--primary)_35%,transparent)] [border-radius:var(--radius-hairline)]",
  "card": "card [align-self:start] [padding:22px_19px] rounded-panel [border:1px_solid_var(--border)] bg-surface [&_small]:text-subtle-foreground [&_small]:text-micro [&_small]:font-semibold [&_small]:[letter-spacing:0.07em] [&_small]:[text-transform:uppercase] [&_h2]:[margin:8px_0_6px] [&_h2]:text-display [&_h2]:font-semibold [&_>_p]:[margin:0] [&_>_p]:text-muted-foreground [&_>_p]:text-micro [&_>_p]:[line-height:1.55] [&_hr]:[margin:10px_0_17px] [&_hr]:[border:0] [&_hr]:[border-top:1px_solid_var(--border)] max-[1100px]:[max-width:420px]",
  "chart": "chart [position:relative] max-[760px]:[display:none]",
  "chronology": "chronology [&_h2]:[margin:0_0_12px] [&_h2]:text-subtle-foreground [&_h2]:text-micro [&_h2]:font-semibold [&_h2]:[letter-spacing:0.08em] [&_h2]:[text-transform:uppercase]",
  "chronologyRow": "chronologyRow [min-height:44px] [display:grid] [grid-template-columns:68px_113px_minmax(0,1fr)] [align-items:center] [border-bottom:1px_solid_var(--border-soft)] text-micro [&_time]:text-muted-foreground [&_time]:font-semibold [&_b]:text-muted-foreground [&_b]:text-micro [&_b]:[letter-spacing:0.06em] [&_p]:[margin:0] max-[760px]:[grid-template-columns:78px_minmax(0,1fr)] max-[760px]:[gap:4px_8px] max-[760px]:[padding:12px_0] max-[760px]:[&_p]:[grid-column:1/-1]",
  "critical": "critical text-primary-hover [&_i]:bg-primary",
  "deploy": "deploy text-primary-hover [&_i]:bg-primary",
  "empty": "empty text-muted-foreground",
  "event": "event [position:absolute] [top:10px] [display:flex] [flex-direction:column] text-micro [white-space:nowrap] [&_strong]:text-micro [&_span]:text-subtle-foreground [&_span]:text-micro [&_i]:[height:9px] [&_i]:[margin-top:2px] [&_i]:[border-radius:var(--radius-hairline)] [&_i]:bg-border-strong",
  "heading": `heading [padding:22px_0_16px] [border-bottom:1px_solid_var(--border)] [&_p]:[margin:5px_0_0] [&_p]:text-muted-foreground [&_p]:text-micro ${screenTitle}`,
  "lower": "lower [display:grid] [grid-template-columns:minmax(0,1fr)_320px] [gap:28px] [padding:24px_0_48px] max-[1100px]:[grid-template-columns:1fr]",
  "metric": "metric [margin-top:15px] [display:flex] [justify-content:space-between] text-muted-foreground text-micro [&_strong]:text-foreground",
  "row": "row [height:66px] [position:relative] [z-index:1] [display:grid] [grid-template-columns:150px_1fr]",
  "sectionLabel": "sectionLabel [margin:0_0_12px] text-subtle-foreground text-micro font-semibold [letter-spacing:0.08em] [text-transform:uppercase]",
  "source": "source [display:flex] [flex-direction:column] [justify-content:center] [border-bottom:1px_solid_var(--border-soft)] [&_strong]:text-micro [&_span]:[margin-top:5px] [&_span]:text-subtle-foreground [&_span]:text-micro",
  "track": "track [position:relative] [border-bottom:1px_solid_var(--border-soft)] [border-left:1px_solid_var(--border-soft)]",
} as const;
