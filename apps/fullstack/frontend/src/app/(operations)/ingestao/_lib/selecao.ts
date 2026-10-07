/** Regras locais de preparação; não validam conteúdo nem autorizam ingestão. */

/** Limites provisórios do navegador, a alinhar com o serviço de upload. */
export const LIMITES = { arquivos: 10, porArquivo: 50 * 1024 ** 2, lote: 100 * 1024 ** 2 } as const;

/** Estado efêmero do lote e avisos da última seleção. */
export type Selecao = { arquivos: File[]; avisos: string[] };

/** Distingue cópias repetidas pelo conjunto de metadados disponível localmente. */
export function chaveArquivo(arquivo: Pick<File, "name" | "size" | "lastModified">): string {
  return JSON.stringify([arquivo.name, arquivo.size, arquivo.lastModified]);
}

/** Aceita os formatos pela extensão, pois o MIME pode estar vazio ou variar. */
export function formatoArquivo(nome: string): "CSV" | "PARQUET" | null {
  const extensao = nome.split(".").pop()?.toLowerCase();
  return extensao === "csv" ? "CSV" : extensao === "parquet" ? "PARQUET" : null;
}

/** Acrescenta apenas candidatos válidos, preservando o lote e a ordem escolhida.
 * @param atuais Arquivos já aceitos na página.
 * @param candidatos Nova seleção; falhas individuais não descartam os demais.
 * @returns Lote atualizado e razões de rejeição da seleção atual.
 */
export function selecionarArquivos(atuais: File[], candidatos: File[]): Selecao {
  const arquivos = [...atuais];
  const chaves = new Set(atuais.map(chaveArquivo));
  const avisos: string[] = [];
  let bytes = atuais.reduce((total, arquivo) => total + arquivo.size, 0);

  for (const arquivo of candidatos) {
    const chave = chaveArquivo(arquivo);
    let motivo: string | null = null;
    if (!formatoArquivo(arquivo.name)) motivo = "formato não aceito. Use CSV ou Parquet.";
    else if (arquivo.size === 0) motivo = "arquivo vazio.";
    else if (arquivo.size > LIMITES.porArquivo) motivo = "excede 50 MiB por arquivo.";
    else if (chaves.has(chave)) motivo = "já está no lote.";
    else if (arquivos.length >= LIMITES.arquivos) motivo = "o lote permite até 10 arquivos.";
    else if (bytes + arquivo.size > LIMITES.lote) motivo = "o lote excederia 100 MiB.";

    if (motivo) {
      avisos.push(`${arquivo.name}: ${motivo}`);
      continue;
    }
    arquivos.push(arquivo);
    chaves.add(chave);
    bytes += arquivo.size;
  }
  return { arquivos, avisos };
}
