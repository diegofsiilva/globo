export type NavigationItem = {
  href: string;
  index: string;
  label: string;
};

/** Destinos públicos da monitoração, compartilhados pela sidebar e pelo drawer. */
export const navigationItems: readonly NavigationItem[] = [
  { href: "/monitor", index: "01", label: "Monitor" },
  { href: "/agora", index: "02", label: "Agora" },
  { href: "/explorar", index: "03", label: "Explorar" },
  { href: "/comparar", index: "04", label: "Comparar" },
  { href: "/hipoteses", index: "05", label: "Hipóteses" },
  { href: "/timeline", index: "06", label: "Timeline" },
  { href: "/recorte", index: "07", label: "Recorte" },
];
