import "@testing-library/jest-dom/vitest";

import { beforeEach } from "vitest";

import { gravarToken } from "@/lib/api/session";

/**
 * Todo teste começa com uma sessão autenticada.
 *
 * O cliente HTTP compartilhado recusa a requisição antes de chamar `fetch`
 * quando não há token na sessão (ver `lib/api/client.ts`). Sem esta semente,
 * cada teste de contrato falharia em `unauthorized` sem nunca exercitar o
 * cenário que pretende testar — o 504, o JSON malformado, o mapeamento.
 *
 * O valor é sintético e tem a forma de um token real (64 hexadecimais) só para
 * atravessar a validação de forma da tela de acesso. Ele não autentica contra
 * nada: nos testes de contrato o `fetch` é substituído por um dublê, e no E2E o
 * Flask local roda sem authorizer.
 *
 * O comportamento SEM sessão é testado à parte, em `tests/contracts/acesso.test.ts`.
 */
beforeEach(() => {
  gravarToken("a".repeat(64));
});
