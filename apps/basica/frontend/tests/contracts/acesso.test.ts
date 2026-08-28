import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import { apiFetch, verificarToken } from "@/lib/api/client";
import { gravarToken, lerToken, limparToken, pareceToken } from "@/lib/api/session";

describe("contrato de acesso", () => {
  afterEach(() => vi.unstubAllGlobals());

  test("[TAC-01] a sessão vive em sessionStorage, e não em localStorage", () => {
    // Espião no `localStorage` em vez de leitura direta: o jsdom desta versão
    // expõe o objeto sem os métodos, e o que importa aqui é que o módulo NÃO o
    // procure -- `localStorage` sobrevive ao fechamento do navegador, e numa
    // máquina compartilhada a credencial ficaria para o próximo turno.
    const escrita = vi.fn();
    vi.stubGlobal("localStorage", { setItem: escrita, getItem: vi.fn(), removeItem: vi.fn() });

    gravarToken("b".repeat(64));

    expect(window.sessionStorage.getItem("argus-access-token")).toBe("b".repeat(64));
    expect(escrita).not.toHaveBeenCalled();
  });

  test("[TAC-02] o token nunca entra no bundle", () => {
    // Se algum dia alguém "resolver" a fricção da tela de acesso pondo o token
    // numa variável de build, ele passaria a ser servido a qualquer visitante
    // da distribuição. Este teste é o que barra essa mudança.
    const publicas = Object.keys(process.env).filter((chave) => chave.startsWith("NEXT_PUBLIC_"));
    for (const chave of publicas) {
      expect(chave.toLowerCase()).not.toContain("token");
    }
  });

  test("[TAC-03] valida a forma do token antes de ir à rede", () => {
    expect(pareceToken("a".repeat(64))).toBe(true);
    expect(pareceToken(`  ${"A".repeat(64)}  `)).toBe(true);
    expect(pareceToken("a".repeat(63))).toBe(false);
    expect(pareceToken("z".repeat(64))).toBe(false);
    expect(pareceToken("Bearer " + "a".repeat(64))).toBe(false);
  });

  describe("cliente HTTP", () => {
    beforeEach(() => gravarToken("c".repeat(64)));

    test("[TAC-04] acrescenta Authorization: Bearer a toda requisição", async () => {
      const espiao = vi.fn().mockResolvedValue(Response.json({ ok: true }));
      vi.stubGlobal("fetch", espiao);

      await apiFetch("/api/v1/clock", { tag: "CLOCK" });

      const [, init] = espiao.mock.calls[0];
      expect(init.headers.Authorization).toBe(`Bearer ${"c".repeat(64)}`);
    });

    test("[TAC-05] 401 derruba a sessão e não é retentável", async () => {
      vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, { status: 401 })));

      await expect(apiFetch("/api/v1/signals", { tag: "SIGNALS" })).rejects.toMatchObject({
        kind: "unauthorized",
        retryable: false,
      });
      // Limpar aqui é o que faz o portão de acesso reagir a um 401 vindo de
      // QUALQUER tela, sem que os adapters conheçam a interface.
      expect(lerToken()).toBeNull();
    });

    test("[TAC-06] 403 derruba a sessão com mensagem de token inválido", async () => {
      vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, { status: 403 })));

      await expect(apiFetch("/api/v1/signals", { tag: "SIGNALS" })).rejects.toMatchObject({
        kind: "unauthorized",
      });
      expect(lerToken()).toBeNull();
    });

    test("[TAC-07] 500 NÃO derruba a sessão", async () => {
      vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, { status: 500 })));

      await expect(apiFetch("/api/v1/signals", { tag: "SIGNALS" })).rejects.toMatchObject({
        kind: "server",
        retryable: true,
      });
      // Erro do servidor não é erro de credencial. Pedir o token de novo aqui
      // faria o operador achar que perdeu o acesso durante uma indisponibilidade.
      expect(lerToken()).toBe("c".repeat(64));
    });

    test("[TAC-08] o X-Request-Id da resposta entra no código de referência", async () => {
      vi.stubGlobal(
        "fetch",
        vi.fn().mockResolvedValue(
          new Response(null, { status: 500, headers: { "X-Request-Id": "req-abc-123" } }),
        ),
      );

      await expect(apiFetch("/api/v1/signals", { tag: "SIGNALS" })).rejects.toMatchObject({
        reference: "ARG-SIGNALS-req-abc-123-HTTP-500",
      });
    });

    test("[TAC-09] sem sessão, nem chega a chamar fetch", async () => {
      limparToken();
      const espiao = vi.fn();
      vi.stubGlobal("fetch", espiao);

      await expect(apiFetch("/api/v1/signals", { tag: "SIGNALS" })).rejects.toMatchObject({
        kind: "unauthorized",
      });
      expect(espiao).not.toHaveBeenCalled();
    });
  });

  describe("verificação do token na tela de acesso", () => {
    test("[TAC-10] 200 aceita", async () => {
      vi.stubGlobal("fetch", vi.fn().mockResolvedValue(Response.json({ sim_now: "x" })));

      await expect(verificarToken("d".repeat(64))).resolves.toBe("ok");
    });

    test("[TAC-11] 403 recusa", async () => {
      vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, { status: 403 })));

      await expect(verificarToken("d".repeat(64))).resolves.toBe("recusado");
    });

    test("[TAC-12] falha de rede não é recusa", async () => {
      // A distinção importa na tela: "token errado" e "não deu para verificar"
      // levam o operador a ações diferentes.
      vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("offline")));

      await expect(verificarToken("d".repeat(64))).resolves.toBe("indisponivel");
    });

    test("[TAC-13] 500 na verificação não é recusa", async () => {
      vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, { status: 500 })));

      await expect(verificarToken("d".repeat(64))).resolves.toBe("indisponivel");
    });
  });
});
