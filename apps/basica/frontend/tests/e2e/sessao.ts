import type { Page } from "@playwright/test";

/**
 * Chave da sessão no `sessionStorage`. Precisa casar com `lib/api/session.ts`.
 *
 * Duplicada aqui de propósito, como literal: o helper roda dentro do navegador
 * via `addInitScript`, antes de qualquer módulo da aplicação existir, então não
 * há de onde importar a constante.
 */
const CHAVE = "argus-access-token";

/**
 * Token sintético com a forma de um real (64 hexadecimais).
 *
 * Não autentica contra nada: o Flask local roda sem o authorizer do API
 * Gateway, então qualquer valor passa. A forma importa apenas para atravessar
 * a validação da tela de acesso.
 */
export const TOKEN_DE_TESTE = "a".repeat(64);

/**
 * Abre uma sessão autenticada antes de a página carregar.
 *
 * Sem isto, todo teste pararia na tela de acesso — que é o comportamento
 * correto do produto, e por isso é exercitado no seu próprio teste
 * (`[E2E-00]`), e não em todos os outros.
 *
 * `addInitScript` e não `page.evaluate`: o script precisa rodar ANTES dos
 * scripts da página, ou o portão já teria decidido que não há sessão e
 * renderizado a tela de acesso.
 *
 * @param page Página do Playwright.
 */
export async function abrirSessao(page: Page): Promise<void> {
  await page.addInitScript(
    ([chave, token]) => {
      window.sessionStorage.setItem(chave, token);
    },
    [CHAVE, TOKEN_DE_TESTE] as const,
  );
}
