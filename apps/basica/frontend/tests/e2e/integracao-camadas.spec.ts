/**
 * TI-01 — integração entre o frontend e o backend, sobre o banco de dados.
 *
 * Componentes atravessados:
 *
 *     dashboard Next.js estático (servido em 127.0.0.1:3100)
 *         -> HTTP (fetch do navegador, com o token na sessão)
 *             -> API Flask de leitura (127.0.0.1:5100)
 *                 -> PostgreSQL local (`argus_test`, semeado por `fixture.sql`)
 *
 * Nenhuma dessas pontas é dublada: o navegador é real, o Flask é o processo
 * real subido pelo `playwright.config.ts`, e o dado vem de tabelas de verdade.
 *
 * O que se verifica é a COMUNICAÇÃO nos dois sentidos do contrato:
 *
 *   - de ida: a escolha do operador na tela vira parâmetro na query string que
 *     o navegador envia ao Flask;
 *   - de volta: o que a tela desenha é exatamente o que o Flask devolveu — nem
 *     uma linha a mais (inventada no cliente) nem uma a menos (perdida na
 *     renderização).
 *
 * Os testes de contrato em `tests/contracts/` já cobrem a forma do JSON contra
 * um dublê. O que só este teste pode mostrar é que essa forma é a mesma que o
 * backend real produz a partir do banco real.
 *
 * Requisitos exercitados: RF08 (pesquisa por atributos), RF09 (filtros
 * cumulativos), RF11 (agrupamento por critérios), RNF02 (resultado da consulta
 * simples em até 5 s) e RNF09 (acesso só a quem está autorizado).
 *
 * Pré-condição: `make -C apps/basica test-frontend-e2e`, que sobe o PostgreSQL,
 * aplica as migrations, carrega `fixture.sql` e constrói o site estático.
 */

import type { Response } from "@playwright/test";
import { expect, test } from "@playwright/test";

/** Origem do Flask de teste, declarada no `playwright.config.ts`. */
const API = "http://127.0.0.1:5100";

/** Forma crua devolvida por `/api/v1/series/breakdown`. */
type BreakdownResposta = {
  dimension: string;
  metric: string | null;
  total: number;
  groups: { key: string; value: number | null; points: number; share: number }[];
};

/**
 * Reconhece a requisição que alimenta a TABELA de agrupamento.
 *
 * A tela dispara vários `breakdown` em paralelo — um por cartão de métrica, um
 * para a taxa de erro da própria tabela. Sem distinguir, o teste leria a
 * resposta de outro componente e falharia por engano, não por defeito.
 *
 * A tabela de volume é a única sem `metric` na query string: ela soma todas as
 * métricas do recorte. As demais fixam uma.
 *
 * @param resposta Resposta observada pelo navegador.
 * @param dimensao Dimensão esperada do agrupamento.
 * @param metrica Métrica esperada, ou `null` para a consulta de volume total.
 */
function ehTabelaDeAgrupamento(
  resposta: Response,
  dimensao: string,
  metrica: string | null = null,
): boolean {
  const url = new URL(resposta.url());
  return (
    url.origin === API &&
    url.pathname.endsWith("/api/v1/series/breakdown") &&
    url.searchParams.get("dimension") === dimensao &&
    url.searchParams.get("metric") === metrica &&
    resposta.status() === 200
  );
}

/** Lê os rótulos de linha que a tabela de agrupamento está mostrando. */
async function chavesNaTela(page: import("@playwright/test").Page): Promise<string[]> {
  const rotulos = await page.getByRole("rowheader").allTextContents();
  return rotulos.map((texto) => texto.trim()).sort();
}

test.describe("TI-01 — dashboard, API de leitura e banco", () => {
  test.beforeEach(async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    // Abre a sessão antes da página carregar: sem token o painel nem monta, o
    // que é o comportamento correto e está sob teste em [TI-01.3].
    await page.addInitScript(() => {
      window.sessionStorage.setItem("argus-access-token", "a".repeat(64));
    });
  });

  test("[TI-01.1] a tela desenha exatamente as linhas que o Flask leu do PostgreSQL", async ({
    page,
  }) => {
    // Agrupamento padrão da tela: dispositivo, preso à fonte `youbora_device`.
    const aguardaTabela = page.waitForResponse((r) => ehTabelaDeAgrupamento(r, "entity"));

    const inicio = Date.now();
    await page.goto("/explorar/");
    const resposta = await aguardaTabela;
    const decorrido = Date.now() - inicio;

    // 1. A requisição saiu do navegador para o Flask de verdade — não para um
    //    dublê nem para um JSON embutido no bundle estático.
    const url = new URL(resposta.url());
    expect(url.origin).toBe(API);
    // O recorte que o agrupamento exige viajou junto (RF09).
    expect(url.searchParams.get("source")).toBe("youbora_device");

    // 2. O corpo veio do banco: traz as entidades semeadas por `fixture.sql`.
    const corpo = (await resposta.json()) as BreakdownResposta;
    expect(corpo.dimension).toBe("entity");
    expect(corpo.groups.length).toBeGreaterThan(0);
    const chavesDoBackend = corpo.groups.map((g) => g.key).sort();
    expect(chavesDoBackend).toContain("LG webOS 3.x");

    // 3. A tabela mostra esse conjunto, sem sobra nem falta. É a asserção
    //    central: liga o que atravessou a rede ao que o operador enxerga.
    await expect(page.getByRole("rowheader")).toHaveCount(corpo.groups.length);
    expect(await chavesNaTela(page)).toEqual(chavesDoBackend);

    // 4. E o número: o valor agregado pelo SQL aparece formatado na linha.
    //    Sem isto, a tela poderia acertar os rótulos e errar a conta.
    const maior = corpo.groups.reduce((a, b) => ((b.value ?? 0) > (a.value ?? 0) ? b : a));
    const formatado = (maior.value ?? 0).toLocaleString("pt-BR", {
      maximumFractionDigits: 1,
    });
    await expect(page.getByRole("row", { name: new RegExp(maior.key) })).toContainText(
      formatado,
    );

    // 5. RNF02: a consulta atravessou as três camadas dentro do limite.
    expect(decorrido).toBeLessThan(5_000);
  });

  test("[TI-01.2] trocar agrupamento e filtro na tela muda a query string e o que volta do banco", async ({
    page,
  }) => {
    await page.goto("/explorar/");
    await page.waitForResponse((r) => ehTabelaDeAgrupamento(r, "entity"));

    // --- de ida, primeiro salto: o agrupamento vira `dimension=source`. ------
    const aguardaPorFonte = page.waitForResponse((r) => ehTabelaDeAgrupamento(r, "source"));
    await page.getByRole("radio", { name: "Fonte" }).click();
    const porFonte = (await (await aguardaPorFonte).json()) as BreakdownResposta;

    // De volta: o banco devolveu as fontes do recorte, e a tela as reproduziu.
    const fontes = porFonte.groups.map((g) => g.key).sort();
    expect(fontes).toContain("npaw");
    await expect(page.getByRole("rowheader")).toHaveCount(porFonte.groups.length);
    expect(await chavesNaTela(page)).toEqual(fontes);

    // --- de ida, segundo salto: o filtro de métrica entra CUMULATIVO ---------
    // `dimension=source` continua valendo e `metric=request_count` se soma a
    // ele (RF09). Se o filtro fosse só um efeito visual no cliente, esta
    // requisição nunca sairia com os dois parâmetros.
    const aguardaFiltrada = page.waitForResponse((r) =>
      ehTabelaDeAgrupamento(r, "source", "request_count"),
    );
    await page.getByRole("combobox", { name: "métrica" }).click();
    await page.getByRole("option", { name: "request_count", exact: true }).click();
    const filtrada = (await (await aguardaFiltrada).json()) as BreakdownResposta;

    // De volta: o recorte foi aplicado no BANCO, e não na tela. `npaw` só tem
    // `bufferratio` no fixture, então some do resultado — e some da tabela.
    const comMetrica = filtrada.groups.map((g) => g.key).sort();
    expect(comMetrica).not.toContain("npaw");
    expect(comMetrica).toContain("prometheus");
    await expect(page.getByRole("rowheader", { name: "prometheus" })).toBeVisible();
    await expect(page.getByRole("rowheader", { name: "npaw" })).toHaveCount(0);
    expect(await chavesNaTela(page)).toEqual(comMetrica);
  });

  test("[TI-01.3] sem token válido o navegador não chega a consultar o backend", async ({
    browser,
  }) => {
    // Este caso NÃO abre a sessão: é o que ele investiga. RNF09 na fronteira —
    // a barreira tem que valer para a comunicação, e não só para a pintura da
    // tela: nenhuma consulta pode sair enquanto não houver token.
    const contexto = await browser.newContext();
    const page = await contexto.newPage();

    const chamadas: string[] = [];
    page.on("request", (r) => {
      if (r.url().startsWith(`${API}/api/v1/`)) chamadas.push(r.url());
    });

    await page.goto("/explorar/");
    await expect(page.getByRole("heading", { name: "Acesso ao painel" })).toBeVisible();
    await expect(page.getByRole("rowheader")).toHaveCount(0);

    expect(chamadas, "o dashboard consultou a API sem sessão aberta").toEqual([]);

    await contexto.close();
  });
});
