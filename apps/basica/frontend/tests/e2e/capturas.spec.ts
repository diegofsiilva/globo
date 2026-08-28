import { expect, test, type Page } from "@playwright/test";
import path from "node:path";

const assetsDir = path.resolve(process.cwd(), "../../../artefatos/assets");

const routes = [
  ["agora", "Sinais em desvio agora"],
  ["explorar", "Explorar eventos"],
  ["comparar", "Agora contra o passado"],
  ["hipoteses", "Hipóteses de causa provável"],
  ["timeline", "Timeline única do incidente"],
  ["recorte", "Taxa de erro por dispositivo × hora BRT"],
] as const;

async function openIntegratedRoute(page: Page, route: string, heading: string, theme: string) {
  await page.addInitScript((selectedTheme) => {
    localStorage.setItem("argus-theme", selectedTheme);
  }, theme);
  await page.goto(`/${route}/`);
  await expect(page.getByRole("heading", { name: heading }).first()).toBeVisible();
  await expect(page.getByText(/Carregando/)).toHaveCount(0);
}

test("regenera as capturas integradas do relatório", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.setViewportSize({ width: 1264, height: 720 });

  for (const [route, heading] of routes) {
    for (const theme of ["escuro", "claro"] as const) {
      await openIntegratedRoute(page, route, heading, theme === "escuro" ? "dark" : "light");
      await page.screenshot({
        path: path.join(assetsDir, `captura_${route}_tema_${theme}.png`),
        animations: "disabled",
      });
    }
  }

  for (const [suffix, width, height] of [
    ["mobile", 390, 844],
    ["tablet", 768, 1024],
  ] as const) {
    await page.setViewportSize({ width, height });
    await openIntegratedRoute(page, "agora", "Sinais em desvio agora", "dark");
    await page.screenshot({
      path: path.join(assetsDir, `captura_agora_${suffix}.png`),
      animations: "disabled",
    });
  }
});
