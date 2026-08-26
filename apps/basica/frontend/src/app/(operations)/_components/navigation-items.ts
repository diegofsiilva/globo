export type NavigationItem = {
  href: string;
  index: string;
  label: string;
};

/** Destinos públicos da monitoração, compartilhados pela sidebar e pelo drawer. */
export const navigationItems: readonly NavigationItem[] = [
  { href: "/agora", index: "01", label: "Agora" },
  { href: "/explorar", index: "02", label: "Explorar" },
  { href: "/comparar", index: "03", label: "Comparar" },
  { href: "/hipoteses", index: "04", label: "Hipóteses" },
  { href: "/timeline", index: "05", label: "Timeline" },
  { href: "/recorte", index: "06", label: "Recorte" },
];
