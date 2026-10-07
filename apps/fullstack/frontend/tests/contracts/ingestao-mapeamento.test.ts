/** Revisão do envelope de eventos e casos que não podem ser aprovados pela amostra. */
import { describe, expect, it } from "vitest";
import { sugerirMapeamento, validarMapeamento, type Mapeamento } from "@/app/(operations)/ingestao/_lib/mapeamento";
import type { Previa } from "@/app/(operations)/ingestao/_lib/previa-contrato";

const previa: Previa = {
  formato: "CSV", colunas: ["timestamp", "event_name", "session_id", "device_id", "duration", "request_status", "media_ads"].map((nome) => ({ nome, tipo: "texto (amostra)" })),
  linhas: [["2026-10-05T12:30:00-03:00", "request", "001", "tv-1", "12.5", "200", "false"]],
  totalLinhas: null, avisos: [],
};

function comValor(coluna: number, valor: string): Previa {
  return { ...previa, linhas: [previa.linhas[0].map((atual, index) => index === coluna ? valor : atual)] };
}

describe("mapeamento de eventos do app de TV", () => {
  it("sugere nomes exatos e aprova campos obrigatórios/opcionais sem alterar a origem", () => {
    const mapeamento = sugerirMapeamento(previa);
    const resultado = validarMapeamento(previa, mapeamento);
    expect(resultado.erros).toEqual([]);
    expect(resultado.linhasValidas).toBe(1);
    expect(previa.linhas[0][2]).toBe("001");
    expect(mapeamento.event_id).toBeNull();
  });

  it("não escolhe cabeçalhos ambíguos nem inventa aliases", () => {
    const outra = { ...previa, colunas: [{ nome: "timestamp", tipo: "texto" }, { nome: "TIMESTAMP", tipo: "texto" }, { nome: "sessao", tipo: "texto" }] };
    expect(sugerirMapeamento(outra).timestamp).toBeNull();
    expect(sugerirMapeamento(outra).session_id).toBeNull();
  });

  it("permite escolher colunas renomeadas manualmente", () => {
    const outra = { ...previa, colunas: previa.colunas.map((coluna) => ({ ...coluna, nome: `origem_${coluna.nome}` })) };
    const manual: Mapeamento = { timestamp: 0, event_name: 1, session_id: 2, device_id: 3 };
    expect(validarMapeamento(outra, manual).erros).toEqual([]);
  });

  it("informa os quatro campos obrigatórios ausentes e não conta linhas como válidas", () => {
    const resultado = validarMapeamento(previa, {});
    expect(resultado.erros.map((erro) => erro.campo)).toEqual(["timestamp", "event_name", "session_id", "device_id"]);
    expect(resultado.linhasValidas).toBe(0);
  });

  it("não permite usar a mesma coluna em dois campos", () => {
    const resultado = validarMapeamento(previa, { ...sugerirMapeamento(previa), device_id: 2 });
    expect(resultado.erros[0].mensagem).toContain("já foi usada em session_id");
    expect(resultado.linhasValidas).toBe(0);
  });

  it("rejeita índices que não pertencem ao esquema", () => {
    expect(validarMapeamento(previa, { ...sugerirMapeamento(previa), device_id: 99 }).erros[0].mensagem).toContain("não existe");
  });

  it("numera a linha e o campo quando um identificador obrigatório está em branco", () => {
    const resultado = validarMapeamento(comValor(2, "   "), sugerirMapeamento(previa));
    expect(resultado.erros).toEqual([{ campo: "session_id", linha: 1, mensagem: "O campo obrigatório está vazio." }]);
  });

  it.each(["2026-02-30T12:00:00Z", "2025-02-29T12:00:00Z", "2026-13-01T12:00:00Z", "2026-10-05T24:00:00Z", "2026-10-05T12:00:00+03:60", "05/10/2026"])("rejeita data inválida %s", (valor) => {
    expect(validarMapeamento(comValor(0, valor), sugerirMapeamento(previa)).erros[0].campo).toBe("timestamp");
  });

  it("aceita ano bissexto e sinaliza UTC para data sem fuso", () => {
    const resultado = validarMapeamento(comValor(0, "2024-02-29T12:30:00.123456"), sugerirMapeamento(previa));
    expect(resultado.erros).toEqual([]);
    expect(resultado.avisos.join(" ")).toContain("UTC");
  });

  it.each([[4, "NaN"], [4, "1,5"], [4, "1e999"], [5, "200.5"], [5, "9007199254740993"], [6, "talvez"]])("rejeita tipo inválido na coluna %i: %s", (coluna, valor) => {
    const resultado = validarMapeamento(comValor(coluna, valor), sugerirMapeamento(previa));
    expect(resultado.erros).toHaveLength(1);
    expect(resultado.linhasValidas).toBe(0);
  });

  it("aceita campos opcionais vazios e evento genérico com aviso", () => {
    const outra = { ...previa, linhas: [["2026-10-05T12:00:00Z", "custom_event", "001", "tv-1", "", "", ""]] };
    const resultado = validarMapeamento(outra, sugerirMapeamento(outra));
    expect(resultado.erros).toEqual([]);
    expect(resultado.avisos.join(" ")).toContain("eventos genéricos");
  });

  it("não aprova valores cortados nem estruturas Parquet apresentadas como texto", () => {
    const cortada = { ...previa, truncadas: [[false, false, true]] };
    expect(validarMapeamento(cortada, sugerirMapeamento(cortada)).erros[0].mensagem).toContain("cortado");
    const estrutura = { ...previa, naoEscalares: [[false, false, false, true]] };
    expect(validarMapeamento(estrutura, sugerirMapeamento(estrutura)).erros[0].mensagem).toContain("campo escalar");
  });

  it("não aprova amostra sem registros", () => {
    const resultado = validarMapeamento({ ...previa, linhas: [] }, sugerirMapeamento(previa));
    expect(resultado.erros[0].mensagem).toContain("não contém registros");
  });

  it("conta somente linhas sem erro na amostra e avisa sobre colunas fora da revisão", () => {
    const outra = { ...previa, linhas: [previa.linhas[0], comValor(2, "").linhas[0]] };
    const resultado = validarMapeamento(outra, { timestamp: 0, event_name: 1, session_id: 2, device_id: 3 });
    expect(resultado.linhasValidas).toBe(1);
    expect(resultado.totalLinhas).toBe(2);
    expect(resultado.erros[0].linha).toBe(2);
    expect(resultado.avisos.join(" ")).toContain("3 coluna(s) não mapeada(s)");
  });
});
