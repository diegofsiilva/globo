/** Leitura local de amostras; nenhum dado é enviado à plataforma. */
import Papa from "papaparse";
import { parquetMetadataAsync, parquetReadObjects, parquetSchema } from "hyparquet";
import { compressors } from "hyparquet-compressors";
import { formatoArquivo, LIMITES } from "./selecao";
import { LIMITES_PREVIA, type Previa } from "./previa-contrato";

/** Distingue limites e problemas conhecidos de falhas internas dos parsers. */
class ErroPrevia extends Error {}

/** Evita cabeçalhos ambíguos e tabelas cuja largura inviabiliza a revisão. */
function validarColunas(nomes: string[]) {
  if (!nomes.length || nomes.length > LIMITES_PREVIA.colunas) {
    throw new ErroPrevia("A prévia aceita de 1 a 64 colunas. Divida o arquivo ou reduza as colunas.");
  }
  if (nomes.some((nome) => !nome.trim()) || new Set(nomes).size !== nomes.length) {
    throw new ErroPrevia("Os nomes das colunas precisam ser preenchidos e únicos.");
  }
}

/** Indica apenas o tipo observado, preservando identificadores com zeros à esquerda. */
function inferirTipo(valores: string[]): string {
  const preenchidos = valores.filter((valor) => valor !== "");
  if (!preenchidos.length) return "não determinado";
  if (preenchidos.every((valor) => /^(true|false)$/i.test(valor))) return "booleano (amostra)";
  if (preenchidos.every((valor) => /^-?(0|[1-9]\d*)(\.\d+)?([eE][+-]?\d+)?$/.test(valor))) return "número (amostra)";
  return "texto (amostra)";
}

/** Formata valores sem perder inteiros de 64 bits. */
function formatarValor(valor: unknown): string {
  if (valor === null || valor === undefined) return "";
  let texto: string;
  if (valor instanceof Date) texto = valor.toISOString();
  else if (valor instanceof Uint8Array) texto = `[binário: ${valor.byteLength} bytes]`;
  else if (typeof valor === "object") texto = JSON.stringify(valor, (_, item) => typeof item === "bigint" ? item.toString() : item);
  else texto = String(valor);
  return texto;
}

/** Limita a exibição; o marcador de truncamento impede validar valores cortados. */
function exibirValor(valor: unknown): string {
  const texto = formatarValor(valor);
  return texto.length > LIMITES_PREVIA.caracteresCelula ? `${texto.slice(0, LIMITES_PREVIA.caracteresCelula)}…` : texto;
}

/** Lê um prefixo UTF-8 e preserva campos entre aspas, inclusive quebras de linha. */
async function lerCsv(arquivo: File): Promise<Previa> {
  const parcial = arquivo.size > LIMITES_PREVIA.csvBytes;
  const bytes = await arquivo.slice(0, LIMITES_PREVIA.csvBytes).arrayBuffer();
  let texto: string;
  try {
    texto = new TextDecoder("utf-8", { fatal: true }).decode(bytes, { stream: parcial });
  } catch {
    throw new ErroPrevia("O CSV precisa estar em UTF-8. Converta a codificação e tente novamente.");
  }
  if (texto.includes("\0")) throw new ErroPrevia("O CSV contém bytes nulos. Converta o arquivo para texto UTF-8.");
  const resultado = Papa.parse<string[]>(texto, {
    header: false, dynamicTyping: false, skipEmptyLines: "greedy",
    preview: LIMITES_PREVIA.linhas + 2, delimitersToGuess: [",", ";", "\t", "|"],
  });
  if (resultado.errors.some((erro) => erro.code !== "UndetectableDelimiter")) {
    throw new ErroPrevia("Não foi possível ler a amostra CSV. Verifique as aspas e os registros; linhas muito longas podem exceder o limite de 1 MiB.");
  }
  const registros = [...resultado.data];
  // O último registro de um prefixo pode estar cortado; nunca o exiba como completo.
  if (parcial && !resultado.meta.truncated && !/[\r\n]$/.test(texto)) registros.pop();
  const nomes = (registros.shift() ?? []).map((nome) => nome.trim());
  validarColunas(nomes);
  const linhas = registros.slice(0, LIMITES_PREVIA.linhas);
  if (linhas.some((linha) => linha.length !== nomes.length)) {
    throw new ErroPrevia("A amostra CSV contém linhas com quantidade de campos diferente do cabeçalho.");
  }
  if (parcial && !linhas.length) throw new ErroPrevia("Nenhum registro completo encontrado no primeiro 1 MiB. Reduza o tamanho das linhas.");
  return {
    formato: "CSV", colunas: nomes.map((nome, index) => ({ nome, tipo: inferirTipo(linhas.map((linha) => linha[index])) })),
    linhas: linhas.map((linha) => linha.map(exibirValor)),
    truncadas: linhas.map((linha) => linha.map((valor) => valor.length > LIMITES_PREVIA.caracteresCelula)), totalLinhas: null,
    delimitador: resultado.meta.delimiter,
    avisos: ["Tipos inferidos apenas pela amostra; os valores originais não são convertidos.",
      ...(parcial ? ["Leitura limitada ao primeiro 1 MiB do CSV."] : []),
      ...(!linhas.length ? ["O arquivo contém cabeçalho, mas nenhum registro na amostra."] : [])],
  };
}

/** Lê metadados e a primeira faixa de linhas com orçamento de bytes local. */
async function lerParquet(arquivo: File): Promise<Previa> {
  if (arquivo.size < 12) throw new ErroPrevia("O arquivo não possui uma estrutura Parquet válida.");
  const inicio = new Uint8Array(await arquivo.slice(0, 4).arrayBuffer());
  const fim = new Uint8Array(await arquivo.slice(-8).arrayBuffer());
  const assinatura = [80, 65, 82, 49];
  if (!assinatura.every((byte, index) => inicio[index] === byte && fim[index + 4] === byte)) {
    throw new ErroPrevia("Assinatura Parquet inválida ou arquivo criptografado não suportado.");
  }
  const tamanhoMetadados = new DataView(fim.buffer).getUint32(0, true);
  if (tamanhoMetadados > 2 * 1024 ** 2 || tamanhoMetadados > arquivo.size - 12) {
    throw new ErroPrevia("Metadados Parquet inválidos ou maiores que o limite de 2 MiB.");
  }
  let bytesLidos = 0;
  const buffer = {
    byteLength: arquivo.size,
    async slice(start: number, end = arquivo.size): Promise<ArrayBuffer> {
      if (start < 0 || end > arquivo.size || end < start) throw new ErroPrevia("O Parquet referencia uma faixa de bytes inválida.");
      bytesLidos += end - start;
      if (bytesLidos > LIMITES_PREVIA.parquetBytes) throw new ErroPrevia("A prévia Parquet excedeu 16 MiB de leitura. Gere grupos de linhas menores.");
      return arquivo.slice(start, end).arrayBuffer();
    },
  };
  const metadata = await parquetMetadataAsync(buffer);
  const esquema = parquetSchema(metadata).children;
  const nomes = esquema.map((coluna) => coluna.element.name);
  validarColunas(nomes);
  // Mesmo dez linhas podem exigir descomprimir todo um grupo colunar.
  let acumuladas = BigInt(0);
  for (const grupo of metadata.row_groups) {
    if (acumuladas >= BigInt(LIMITES_PREVIA.linhas)) break;
    if (grupo.total_byte_size > BigInt(LIMITES_PREVIA.grupoDescomprimido)) {
      throw new ErroPrevia("O grupo Parquet excede 64 MiB descomprimidos. Gere grupos de linhas menores para a prévia.");
    }
    acumuladas += grupo.num_rows;
  }
  const linhas = metadata.num_rows > BigInt(0) ? await parquetReadObjects({
    file: buffer, metadata, compressors, rowStart: 0, rowEnd: LIMITES_PREVIA.linhas,
  }) : [];
  const valores = linhas.slice(0, LIMITES_PREVIA.linhas).map((linha) => nomes.map((nome) => formatarValor(linha[nome])));
  const naoEscalares = linhas.slice(0, LIMITES_PREVIA.linhas).map((linha) => nomes.map((nome) => {
    const valor = linha[nome];
    return valor !== null && typeof valor === "object" && !(valor instanceof Date);
  }));
  return {
    formato: "PARQUET",
    colunas: esquema.map((coluna) => ({ nome: coluna.element.name, tipo: coluna.element.converted_type ?? coluna.element.type ?? "estrutura" })),
    linhas: valores.map((linha) => linha.map(exibirValor)),
    truncadas: valores.map((linha) => linha.map((valor) => valor.length > LIMITES_PREVIA.caracteresCelula)),
    naoEscalares,
    totalLinhas: metadata.num_rows.toString(), avisos: [],
  };
}

/** Escolhe o parser pelo formato e traduz falhas sem expor detalhes internos.
 * @param arquivo Arquivo local selecionado pelo operador.
 * @returns Até dez registros e o esquema observado; não valida o arquivo inteiro.
 */
export async function lerPrevia(arquivo: File): Promise<Previa> {
  const formato = formatoArquivo(arquivo.name);
  if (!formato || !arquivo.size || arquivo.size > LIMITES.porArquivo) throw new ErroPrevia("Selecione um CSV ou Parquet não vazio de até 50 MiB.");
  try {
    return formato === "CSV" ? await lerCsv(arquivo) : await lerParquet(arquivo);
  } catch (erro) {
    if (erro instanceof ErroPrevia) throw erro;
    throw new ErroPrevia(`Não foi possível ler o ${formato}. Verifique se o arquivo está completo e usa um formato suportado.`);
  }
}
