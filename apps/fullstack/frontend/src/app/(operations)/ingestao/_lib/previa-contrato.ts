/** Contrato leve entre interface e worker; não carrega os parsers na página. */

/** Limites locais da amostra, independentes dos limites do futuro upload. */
export const LIMITES_PREVIA = {
  linhas: 10, colunas: 64, csvBytes: 1024 ** 2,
  parquetBytes: 16 * 1024 ** 2, grupoDescomprimido: 64 * 1024 ** 2,
  caracteresCelula: 500, tempoMs: 30_000,
} as const;

/** Colunas, valores para exibição e informações sobre o alcance da amostra. */
export type Previa = {
  formato: "CSV" | "PARQUET";
  colunas: { nome: string; tipo: string }[];
  linhas: string[][];
  totalLinhas: string | null;
  delimitador?: string;
  avisos: string[];
};

/** Resposta serializável do worker; erros de biblioteca não são expostos na tela. */
export type RespostaPrevia = { previa: Previa } | { erro: string };
