import { expect, test } from "@playwright/test";

import { abrirSessao, TOKEN_DE_TESTE } from "./sessao";

test.beforeEach(async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await abrirSessao(page);
});

test.describe("acesso", () => {
  // Este bloco NÃO abre a sessão: é justamente o que ele testa.
  test.use({ storageState: { cookies: [], origins: [] } });

  test("[E2E-00] sem token o painel não carrega, e o token colado dá acesso", async ({
    browser,
  }) => {
    const contexto = await browser.newContext();
    const page = await contexto.newPage();

    await page.goto("/agora/");

    // Nenhuma tela é montada: nem a moldura, nem a navegação, nem uma consulta.
    await expect(page.getByRole("heading", { name: "Acesso ao painel" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Sinais em desvio agora" })).toHaveCount(0);
    await expect(page.getByRole("link", { name: /Explorar/ })).toHaveCount(0);

    // Um valor com a forma errada é recusado na própria tela, sem ir à rede.
    await page.getByLabel("Token de leitura").fill("token-curto");
    await page.getByRole("button", { name: "Entrar" }).click();
    await expect(page.getByText("O token não tem o formato esperado")).toBeVisible();

    // Com o token válido, o painel monta.
    await page.getByLabel("Token de leitura").fill(TOKEN_DE_TESTE);
    await page.getByRole("button", { name: "Entrar" }).click();
    await expect(page.getByRole("heading", { name: "Sinais em desvio agora" })).toBeVisible();

    // Sair devolve o operador à tela de acesso.
    await page.getByRole("button", { name: "Sair" }).click();
    await expect(page.getByRole("heading", { name: "Acesso ao painel" })).toBeVisible();

    await contexto.close();
  });
});

test("[E2E-01] a entrada redireciona e a navegação alcança as seis áreas", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveURL(/\/agora\/$/);
  await expect(page.getByRole("heading", { name: "Sinais em desvio agora" })).toBeVisible();

  const routes = [
    ["Explorar", "Explorar eventos"],
    ["Comparar", "Agora contra o passado"],
    ["Hipóteses", "Hipóteses de causa provável"],
    ["Timeline", "Timeline única do incidente"],
    ["Recorte", "Taxa de erro por dispositivo × hora BRT"],
  ] as const;

  for (const [link, heading] of routes) {
    await page.getByRole("link", { name: new RegExp(link) }).click();
    await expect(page.getByRole("heading", { name: heading })).toBeVisible();
  }
});

test("[E2E-02] Agora exibe o sinal calculado pelo Flask sobre o PostgreSQL", async ({ page }) => {
  const signalResponse = page.waitForResponse(
    (response) => response.url().includes("/api/v1/signals") && response.status() === 200,
  );
  await page.goto("/agora/");
  await signalResponse;

  await expect(page.getByText("playback-api", { exact: true }).first()).toBeVisible();
  await expect(page.getByText(/Crítico · prometheus · error_rate_pct/).first()).toBeVisible();
  await expect(page.getByText("GET /api/v1/signals")).toBeVisible();
});

test("[E2E-03] Explorar usa métricas, facetas e agrupamentos reais", async ({ page }) => {
  const breakdownResponse = page.waitForResponse(
    (response) => response.url().includes("/api/v1/series/breakdown") && response.status() === 200,
  );
  await page.goto("/explorar/");
  await breakdownResponse;

  await expect(page.getByText("request_count", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("LG webOS 3.x", { exact: true }).first()).toBeVisible();

  const metricBreakdown = page.getByRole("radio", { name: "Métrica" });
  await metricBreakdown.click();
  await expect(metricBreakdown).toBeChecked();
  await expect(page.getByRole("rowheader", { name: "error_rate_pct" })).toBeVisible();

  const sourceFilter = page.getByRole("combobox", { name: "fonte" });
  await sourceFilter.click();
  await page.getByRole("option", { name: "prometheus", exact: true }).click();

  const cumulativeResponse = page.waitForResponse((response) => {
    const url = new URL(response.url());
    return (
      url.pathname.endsWith("/api/v1/series/breakdown") &&
      url.searchParams.get("source") === "prometheus" &&
      url.searchParams.get("metric") === "request_count" &&
      response.status() === 200
    );
  });
  const metricFilter = page.getByRole("combobox", { name: "métrica" });
  await metricFilter.click();
  await page.getByRole("option", { name: "request_count", exact: true }).click();
  await cumulativeResponse;
  await expect(sourceFilter).toContainText("prometheus");
  await expect(metricFilter).toContainText("request_count");
});

test("[E2E-04] Comparar troca a referência e mostra mudanças do backend", async ({ page }) => {
  await page.goto("/comparar/");

  await expect(page.getByText("globoplay-tv", { exact: false })).toBeVisible();
  const yesterday = page.getByRole("radio", { name: /Ontem, mesmo horário/ });
  await yesterday.click();
  await expect(yesterday).toBeChecked();
  await expect(page.getByText(/ontem$/).first()).toBeVisible();
});

test("[E2E-05] Hipóteses opera em modo API e expõe score e evidência", async ({ page }) => {
  const hypothesesResponse = page.waitForResponse(
    (response) => response.url().includes("/api/v1/hypotheses") && response.status() === 200,
  );
  await page.goto("/hipoteses/");
  await hypothesesResponse;

  const hypothesis = page.getByRole("button", { name: /Falha interna de playback/ });
  await expect(hypothesis).toBeVisible();
  await hypothesis.click();
  await expect(page.getByRole("complementary", { name: "Composição do score" })).toContainText(
    "82",
  );
  await expect(page.getByText(/taxa de erro acima do baseline/)).toBeVisible();
});

test("[E2E-06] Timeline correlaciona as seis fontes reais", async ({ page }) => {
  await page.goto("/timeline/");

  await expect(page.getByText("6 fontes", { exact: false }).first()).toBeVisible();
  await expect(page.getByText("INC-E2E-001", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("globoplay-tv", { exact: true }).first()).toBeVisible();
  await expect(page.getByLabel("Janela de correlação")).toContainText("6 de 6");
});

test("[E2E-07] Recorte abre a timeline pública de uma sessão", async ({ page }) => {
  await page.goto("/recorte/");

  await expect(page.getByText("LG webOS 3.x", { exact: true }).first()).toBeVisible();
  await page.getByRole("button", { name: "PLAYER-500" }).first().click();
  await expect(page.getByRole("dialog")).toContainText("Sessão session-e2e");
  await expect(page.getByRole("dialog")).toContainText("PLAYER-500");
});

test("[E2E-08] tema e navegação móvel preservam uma interação acessível", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/agora/");

  const themeToggle = page.getByRole("button", { name: /Usar modo (claro|escuro)/ });
  const initialLabel = await themeToggle.getAttribute("aria-label");
  await themeToggle.focus();
  await page.keyboard.press("Enter");
  await expect(themeToggle).not.toHaveAttribute("aria-label", initialLabel ?? "");

  await page.getByRole("button", { name: "Abrir menu de navegação" }).click();
  await page.getByRole("navigation", { name: "Navegação móvel de monitoração" })
    .getByRole("link", { name: /Explorar/ })
    .click();
  await expect(page).toHaveURL(/\/explorar\/$/);
  await expect(page.getByRole("heading", { name: "Explorar eventos" })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );
});
