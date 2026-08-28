"use client";

import {
  useCallback,
  useState,
  useSyncExternalStore,
  type FormEvent,
  type ReactNode,
} from "react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { verificarToken } from "@/lib/api/client";
import { gravarToken, lerToken, observarToken, pareceToken } from "@/lib/api/session";
import { accessGateStyles as styles } from "./access-gate.styles";

/**
 * Portão de acesso do dashboard.
 *
 * Enquanto não houver token na sessão, nenhuma tela é montada — nem a moldura,
 * nem a navegação, nem uma única consulta. Isso não é uma barreira de segurança
 * (a barreira está no authorizer do API Gateway, e um `sessionStorage.setItem`
 * no console contorna esta camada em três segundos). É o comportamento correto
 * do produto: sem token, toda consulta voltaria 401, e o operador veria seis
 * telas quebradas em vez de uma instrução do que fazer.
 *
 * Também é o ponto onde a sessão volta a ser pedida quando cai. O cliente HTTP
 * limpa a sessão em 401/403, e este componente observa essa mudança — de
 * qualquer tela, sem que os adapters conheçam a interface.
 *
 * @param children Árvore protegida, montada só com sessão ativa.
 */
export function AccessGate({ children }: { children: ReactNode }) {
  // `useSyncExternalStore` e não `useEffect` + `setState`: a sessão É uma store
  // externa (o `sessionStorage` mais os ouvintes), e este hook existe
  // exatamente para isso. Ler no efeito causaria uma renderização em cascata a
  // cada montagem, que o lint do React 19 recusa com razão.
  //
  // O snapshot de servidor devolve `undefined` de propósito. Ele é usado na
  // pré-renderização estática E na hidratação; distinguir "ainda não sabemos"
  // de "não há token" é o que evita o piscar da tela de acesso a cada
  // navegação para quem já está autenticado.
  const token = useSyncExternalStore(observarToken, lerToken, () => undefined);

  if (token === undefined) return null;
  if (token) return <>{children}</>;
  return <AccessScreen />;
}

/** Estado do formulário. Um enum explícito em vez de dois booleanos que podem
 * se contradizer (`carregando && erro`). */
type Estado =
  | { fase: "editando" }
  | { fase: "verificando" }
  | { fase: "recusado" }
  | { fase: "malformado" }
  | { fase: "indisponivel" };

/** Formulário de entrada do token de leitura. */
function AccessScreen() {
  const [valor, setValor] = useState("");
  const [estado, setEstado] = useState<Estado>({ fase: "editando" });

  const enviar = useCallback(
    async (evento: FormEvent) => {
      evento.preventDefault();
      const token = valor.trim();

      // Checagem de forma ANTES da rede: colar com quebra de linha ou colar a
      // linha inteira do terminal são os erros comuns, e um 403 alguns
      // segundos depois seria lido como "a API caiu".
      if (!pareceToken(token)) {
        setEstado({ fase: "malformado" });
        return;
      }

      setEstado({ fase: "verificando" });
      const resultado = await verificarToken(token);

      if (resultado === "ok") {
        // Só grava depois de a API aceitar. Gravar antes deixaria a sessão
        // "aberta" com um token inválido, e a primeira consulta a derrubaria.
        gravarToken(token);
        return;
      }
      setEstado({ fase: resultado === "recusado" ? "recusado" : "indisponivel" });
    },
    [valor],
  );

  const verificando = estado.fase === "verificando";

  return (
    <div className={styles.screen}>
      <main className={styles.card}>
        <div className={styles.brand}>
          <div className={styles.brandMark} aria-hidden="true" />
          <strong>Monitoração Agêntica</strong>
          <span>Globoplay</span>
        </div>

        <h1 className={styles.title}>Acesso ao painel</h1>
        <p className={styles.intro}>
          Este painel consulta dados de telemetria do parceiro. Informe o token de
          leitura para continuar.
        </p>

        <form onSubmit={enviar} noValidate>
          <div className={styles.field}>
            <label className={styles.label} htmlFor="token-de-acesso">
              Token de leitura
            </label>
            <Input
              id="token-de-acesso"
              name="token"
              type="password"
              className={styles.input}
              value={valor}
              onChange={(evento) => {
                setValor(evento.target.value);
                if (estado.fase !== "editando") setEstado({ fase: "editando" });
              }}
              // `autoComplete="off"` e `spellCheck` desligado: o token não é uma
              // senha de conta e não deve ser oferecido pelo gerenciador do
              // navegador nem sublinhado como erro de digitação.
              autoComplete="off"
              spellCheck={false}
              autoCapitalize="off"
              autoCorrect="off"
              aria-describedby="token-ajuda"
              aria-invalid={estado.fase === "malformado" || estado.fase === "recusado"}
              disabled={verificando}
              required
            />
            <p className={styles.hint} id="token-ajuda">
              64 caracteres hexadecimais. Fornecido pela equipe de operação; não é
              a sua senha corporativa.
            </p>
          </div>

          <div className={styles.actions}>
            <Button type="submit" disabled={verificando || valor.trim().length === 0}>
              {verificando ? "Verificando…" : "Entrar"}
            </Button>
          </div>
        </form>

        <MensagemDeErro estado={estado} />

        <p className={styles.footer}>
          O token fica guardado apenas nesta aba e é descartado ao fechá-la. Ele
          identifica o serviço, não a pessoa: não o compartilhe fora da equipe.
        </p>
      </main>
    </div>
  );
}

/**
 * Traduz o estado do formulário na mensagem correspondente.
 *
 * `aria-live` no contêiner e não no `Alert`: o leitor de tela precisa observar
 * uma região que já existe no DOM antes da mudança. Um `aria-live` que aparece
 * junto com o texto costuma não ser anunciado.
 *
 * @param estado Estado atual do formulário.
 */
function MensagemDeErro({ estado }: { estado: Estado }) {
  return (
    <div className={styles.error} aria-live="polite">
      {estado.fase === "malformado" && (
        <Alert variant="warning">
          <AlertTitle>O token não tem o formato esperado</AlertTitle>
          <AlertDescription>
            São 64 caracteres hexadecimais, sem espaços nem quebras de linha.
            Confira se você copiou o valor inteiro.
          </AlertDescription>
        </Alert>
      )}
      {estado.fase === "recusado" && (
        <Alert variant="destructive">
          <AlertTitle>Token recusado</AlertTitle>
          <AlertDescription>
            A API não reconheceu este token. Ele pode ter sido rotacionado, ou
            ser o token de ingestão — que não dá acesso a este painel.
          </AlertDescription>
        </Alert>
      )}
      {estado.fase === "indisponivel" && (
        <Alert variant="warning">
          <AlertTitle>Não foi possível verificar o token</AlertTitle>
          <AlertDescription>
            A API não respondeu. Isso não significa que o token esteja errado —
            verifique a rede e tente de novo.
          </AlertDescription>
        </Alert>
      )}
    </div>
  );
}
