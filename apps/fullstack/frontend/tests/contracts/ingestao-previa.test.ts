// @vitest-environment node
/** Arquivos sintéticos exercitam os parsers reais sem dados do parceiro. */
import { describe, expect, it } from "vitest";
import { parquetWriteBuffer } from "hyparquet-writer";
import { lerPrevia } from "@/app/(operations)/ingestao/_lib/previa";
import { LIMITES_PREVIA } from "@/app/(operations)/ingestao/_lib/previa-contrato";

describe("prévia CSV", () => {
  it("detecta ponto e vírgula, BOM, aspas escapadas e campos com quebra de linha", async () => {
    const file = new File(['\uFEFFid;descricao;ativo\r\n001;"fala ""oi""\ne continua";true\r\n002;normal;false'], "dados.csv");
    const previa = await lerPrevia(file);
    expect(previa.delimitador).toBe(";");
    expect(previa.linhas).toEqual([["001", 'fala "oi"\ne continua', "true"], ["002", "normal", "false"]]);
    expect(previa.colunas.map((coluna) => coluna.tipo)).toEqual(["texto (amostra)", "texto (amostra)", "booleano (amostra)"]);
    expect(previa.totalLinhas).toBeNull();
  });

  it("limita a prévia a dez registros e reconhece separador de tabulação", async () => {
    const csv = "id\tvalor\n" + Array.from({ length: 20 }, (_, index) => `${index}\t${index + 0.5}`).join("\n");
    const previa = await lerPrevia(new File([csv], "dados.csv"));
    expect(previa.delimitador).toBe("\t");
    expect(previa.linhas).toHaveLength(10);
    expect(previa.colunas[1].tipo).toBe("número (amostra)");
  });

  it("aceita CSV de uma coluna e cabeçalho sem registros", async () => {
    const previa = await lerPrevia(new File(["nome\n"], "dados.csv"));
    expect(previa.colunas).toEqual([{ nome: "nome", tipo: "não determinado" }]);
    expect(previa.linhas).toEqual([]);
    expect(previa.avisos.join(" ")).toContain("nenhum registro");
  });

  it.each([
    ["nome,nome\na,b", "únicos"],
    ["nome,\na,b", "preenchidos"],
    ["nome,valor\na,b,c", "quantidade de campos"],
    ['nome,valor\na,"aberto', "aspas"],
    [Array.from({ length: 65 }, (_, index) => `col${index}`).join(","), "64 colunas"],
  ])("rejeita amostra inválida: %s", async (csv, mensagem) => {
    await expect(lerPrevia(new File([csv], "dados.csv"))).rejects.toThrow(mensagem);
  });

  it("rejeita codificação inválida e não converte fórmulas em conteúdo executável", async () => {
    await expect(lerPrevia(new File([new Uint8Array([0xff, 0xfe, 0x41])], "dados.csv"))).rejects.toThrow("UTF-8");
    const previa = await lerPrevia(new File(["valor\n=1+1\n<script>alert(1)</script>"], "dados.csv"));
    expect(previa.linhas).toEqual([["=1+1"], ["<script>alert(1)</script>"]]);
  });

  it("lê somente o prefixo e limita valores longos para exibição", async () => {
    const csv = "id,valor\n1," + "x".repeat(600) + "\n" + "2,normal\n".repeat(160_000);
    const file = new File([csv], "grande.csv");
    const previa = await lerPrevia(file);
    expect(previa.avisos.join(" ")).toContain("primeiro 1 MiB");
    expect(previa.linhas[0][1]).toHaveLength(LIMITES_PREVIA.caracteresCelula + 1);
    expect(previa.linhas).toHaveLength(10);
  });

  it("não exibe registro cortado pelo limite de leitura", async () => {
    const file = new File(["valor\n" + "x".repeat(LIMITES_PREVIA.csvBytes + 100)], "grande.csv");
    await expect(lerPrevia(file)).rejects.toThrow("Nenhum registro completo");
  });
});

describe("prévia Parquet", () => {
  it("lê Parquet Snappy real, esquema, total e inteiros de 64 bits", async () => {
    const buffer = parquetWriteBuffer({
      columnData: [
        { name: "id", data: Array.from({ length: 15 }, (_, index) => BigInt("9007199254740993") + BigInt(index)), type: "INT64" },
        { name: "nome", data: Array.from({ length: 15 }, (_, index) => `evento ${index}`), type: "STRING" },
      ], rowGroupSize: 5,
    });
    const previa = await lerPrevia(new File([buffer], "dados.parquet"));
    expect(previa.formato).toBe("PARQUET");
    expect(previa.totalLinhas).toBe("15");
    expect(previa.linhas).toHaveLength(10);
    expect(previa.linhas[0]).toEqual(["9007199254740993", "evento 0"]);
    expect(previa.colunas).toEqual([{ nome: "id", tipo: "INT64" }, { nome: "nome", tipo: "UTF8" }]);
  });

  it("não aceita CSV apenas renomeado como Parquet", async () => {
    await expect(lerPrevia(new File(["id,nome\n1,evento"], "falso.parquet"))).rejects.toThrow("Assinatura Parquet inválida");
  });

  it("rejeita rodapé corrompido e metadados com comprimento inválido", async () => {
    const buffer = parquetWriteBuffer({ columnData: [{ name: "id", data: [1], type: "INT32" }] });
    const corrompido = buffer.slice(0);
    new Uint8Array(corrompido)[corrompido.byteLength - 1] = 0;
    await expect(lerPrevia(new File([corrompido], "corrompido.parquet"))).rejects.toThrow("Assinatura");
    new DataView(buffer).setUint32(buffer.byteLength - 8, 3 * 1024 ** 2, true);
    await expect(lerPrevia(new File([buffer], "corrompido.parquet"))).rejects.toThrow("Metadados Parquet inválidos");
  });
});
