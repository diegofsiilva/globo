/** Mapeamento estático UF -> região (divisão IBGE). Não depende de dado
 * telemetrado: a série gold/silver expõe `uf` real, mas não tem coluna de
 * região nomeada -- isto é geografia fixa, não um dado que possa ficar
 * desatualizado. */
export const UF_TO_REGION: Record<string, string> = {
  AC: "Norte",
  AP: "Norte",
  AM: "Norte",
  PA: "Norte",
  RO: "Norte",
  RR: "Norte",
  TO: "Norte",
  AL: "Nordeste",
  BA: "Nordeste",
  CE: "Nordeste",
  MA: "Nordeste",
  PB: "Nordeste",
  PE: "Nordeste",
  PI: "Nordeste",
  RN: "Nordeste",
  SE: "Nordeste",
  DF: "Centro-Oeste",
  GO: "Centro-Oeste",
  MT: "Centro-Oeste",
  MS: "Centro-Oeste",
  ES: "Sudeste",
  MG: "Sudeste",
  RJ: "Sudeste",
  SP: "Sudeste",
  PR: "Sul",
  RS: "Sul",
  SC: "Sul",
};

/** Região de uma UF, ou `undefined` se o código não for reconhecido (dado sujo). */
export function regionOf(uf: string): string | undefined {
  return UF_TO_REGION[uf.toUpperCase()];
}

/** Reduz uma lista de UFs reais (ex.: vinda de `/api/v1/facets?field=uf`) às
 * regiões que elas cobrem, sem repetição e na ordem Norte/Nordeste/Centro-
 * Oeste/Sudeste/Sul. UFs não reconhecidas são ignoradas. */
export function regionsFromUfs(ufs: string[]): string[] {
  const order = ["Norte", "Nordeste", "Centro-Oeste", "Sudeste", "Sul"];
  const present = new Set(ufs.map(regionOf).filter((region): region is string => Boolean(region)));
  return order.filter((region) => present.has(region));
}
