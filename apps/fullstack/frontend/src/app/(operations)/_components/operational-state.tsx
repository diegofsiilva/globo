"use client";

import { useState, type ReactNode } from "react";
import {
  AlertCircle,
  Clock3,
  CloudOff,
  DatabaseZap,
  RefreshCw,
  SearchX,
} from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import type { QueryFailure } from "@/lib/operational-state";
import { useOperationsUi, type OperationalState } from "./operations-ui-context";

/**
 * O que a moldura precisa saber para escolher entre os sete estados.
 *
 * As três ações são opcionais e independentes porque nem todo estado as admite:
 * `onRetry` não faz sentido numa falha não-retentável, `onResetFilters` só existe
 * quando o vazio pode ter vindo do recorte, e `onUseCached` só quando há dado
 * anterior a exibir.
 *
 * `missingSources` alimenta o estado `partial`: a tela mostra o que tem e diz
 * quais fontes faltaram, em vez de esconder tudo ou fingir que o conjunto está
 * completo.
 */
export type OperationalPresentation = {
  state?: OperationalState;
  title: string;
  scope?: string;
  failure?: QueryFailure;
  lastSuccessAt?: string;
  missingSources?: readonly string[];
  onRetry?: () => unknown | Promise<unknown>;
  onResetFilters?: () => void;
  onUseCached?: () => void;
  /**
   * Próximo passo oferecido no estado vazio quando o vazio não veio de filtro
   * (ampliar o período, por exemplo). Sem isso a tela dizia "nenhum resultado"
   * e deixava o operador adivinhar o que mudar.
   */
  emptyAction?: { label: string; onAction: () => void };
};

/**
 * Escolhe o que renderizar: o conteúdo ou um dos estados operacionais.
 *
 * O estado forçado por query string (`?estado=empty`) tem precedência sobre o
 * real. É o que permite demonstrar e revisar cada estado sem reproduzir a
 * condição — derrubar a API só para ver a tela de erro custaria mais que a
 * revisão.
 *
 * @param children Conteúdo exibido quando o estado é `ready` ou `refreshing`.
 * @param presentation Estado, título, escopo, falha e ações disponíveis.
 */
export function OperationalStateBoundary({
  children,
  presentation,
}: {
  children: ReactNode;
  presentation: OperationalPresentation;
}) {
  const { demoState, clearDemoState } = useOperationsUi();
  const actualState = presentation.state ?? "ready";
  const state = demoState ?? actualState;
  const [retrying, setRetrying] = useState(false);
  const [announcement, setAnnouncement] = useState("");

  async function retry() {
    setRetrying(true);
    setAnnouncement("Nova tentativa iniciada.");
    try {
      if (demoState !== null) clearDemoState();
      await presentation.onRetry?.();
      setAnnouncement("Consulta solicitada novamente.");
    } catch {
      setAnnouncement("A nova tentativa falhou. Revise a conexão ou os filtros antes de tentar novamente.");
    } finally {
      setRetrying(false);
    }
  }

  return (
    <>
      {demoState !== null && (
        <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-panel border border-info/60 bg-info/8 px-4 py-3 text-sm">
          <span className="flex items-center gap-2">
            <Badge variant="outline" className="border-info text-info">Modo de demonstração</Badge>
            Estado <strong className="font-mono">{demoState}</strong> aplicado somente à interface.
          </span>
          <Button type="button" variant="ghost" size="sm" onClick={clearDemoState}>
            Voltar ao estado normal
          </Button>
        </div>
      )}

      <div className="sr-only" aria-live="polite">{announcement}</div>

      {state === "loading" && <LoadingState title={presentation.title} />}
      {state === "empty" && (
        <EmptyState
          title={presentation.title}
          onReset={demoState !== null ? clearDemoState : presentation.onResetFilters}
          action={demoState !== null ? undefined : presentation.emptyAction}
        />
      )}
      {state === "error" && (
        <ErrorState
          title={presentation.title}
          scope={presentation.scope}
          failure={presentation.failure}
          retrying={retrying}
          onRetry={() => void retry()}
          onUseCached={presentation.onUseCached}
          onResetFilters={presentation.onResetFilters}
        />
      )}
      {state === "partial" && (
        <>
          <PartialBanner missingSources={presentation.missingSources} />
          {children}
        </>
      )}
      {state === "stale" && (
        <>
          <StaleBanner
            lastSuccessAt={presentation.failure?.lastSuccessAt ?? presentation.lastSuccessAt}
            retrying={retrying}
            onRetry={() => void retry()}
          />
          {children}
        </>
      )}
      {state === "refreshing" && (
        <>
          {/* Altura zero de propósito. As telas reconsultam a cada 30 s, e uma
              faixa no fluxo empurrava a tela inteira para baixo e de volta a
              cada ciclo -- a linha que o operador estava lendo saía do lugar.
              O aviso flutua no canto do conteúdo e não desloca nada. */}
          <div className="relative h-0" role="status">
            <span className="absolute right-0 top-3 z-[1] inline-flex items-center gap-1.5 rounded-badge border border-info/40 bg-surface px-2.5 py-1 font-mono text-micro text-info">
              <RefreshCw className="size-3 animate-spin motion-reduce:animate-none" aria-hidden="true" />
              Atualizando
              <span className="sr-only">a consulta. Os dados anteriores permanecem visíveis.</span>
            </span>
          </div>
          {children}
        </>
      )}
      {state === "ready" && children}
    </>
  );
}

function LoadingState({ title }: { title: string }) {
  return (
    <div className="grid gap-5 py-8" role="status" aria-label={`Carregando ${title}`}>
      <div className="flex items-center gap-3 text-sm text-muted-foreground">
        <RefreshCw className="size-4 animate-spin motion-reduce:animate-none" aria-hidden="true" />
        Consultando fontes para {title.toLocaleLowerCase("pt-BR")}…
      </div>
      <div className="grid gap-px overflow-hidden rounded-panel border border-border bg-border md:grid-cols-2">
        {[0, 1, 2, 3].map((item) => (
          <div className="space-y-4 bg-background p-5" key={item}>
            <Skeleton className="h-3 w-32" />
            <Skeleton className="h-7 w-3/4" />
            <Skeleton className="h-3 w-full" />
          </div>
        ))}
      </div>
    </div>
  );
}

function EmptyState({
  title,
  onReset,
  action,
}: {
  title: string;
  onReset?: () => void;
  action?: OperationalPresentation["emptyAction"];
}) {
  return (
    <Alert className="my-6 max-w-3xl">
      <SearchX aria-hidden="true" />
      <AlertTitle>Nenhum resultado para {title.toLocaleLowerCase("pt-BR")}</AlertTitle>
      <AlertDescription className="space-y-4">
        <p>
          A consulta foi concluída, mas não encontrou dados neste recorte. Isso é diferente de uma
          falha de coleta ou de uma consulta interrompida.
        </p>
        {(onReset || action) && (
          <div className="flex flex-wrap gap-2">
            {action && (
              <Button type="button" size="sm" onClick={action.onAction}>
                {action.label}
              </Button>
            )}
            {onReset && (
              <Button type="button" variant="outline" size="sm" onClick={onReset}>
                Rever filtros
              </Button>
            )}
          </div>
        )}
      </AlertDescription>
    </Alert>
  );
}

function ErrorState({
  title,
  scope,
  failure,
  retrying,
  onRetry,
  onUseCached,
  onResetFilters,
}: {
  title: string;
  scope?: string;
  failure?: QueryFailure;
  retrying: boolean;
  onRetry: () => void;
  onUseCached?: () => void;
  onResetFilters?: () => void;
}) {
  const resolved = failure ?? demoFailure();
  return (
    <Alert variant="destructive" className="my-6 max-w-3xl" aria-live="assertive">
      {resolved.kind === "offline" ? <CloudOff aria-hidden="true" /> : <AlertCircle aria-hidden="true" />}
      <AlertTitle>Não foi possível atualizar {title.toLocaleLowerCase("pt-BR")}</AlertTitle>
      <AlertDescription className="space-y-4 text-foreground">
        <p>{resolved.cause}</p>
        <dl className="grid gap-2 border-y border-destructive/30 py-3 font-mono text-xs sm:grid-cols-2">
          <div><dt className="text-muted-foreground">Escopo afetado</dt><dd className="mt-1 break-words">{scope ?? "recorte atual"}</dd></div>
          <div><dt className="text-muted-foreground">Ocorrência</dt><dd className="mt-1">{resolved.occurredAt}</dd></div>
          <div><dt className="text-muted-foreground">Referência</dt><dd className="mt-1 break-all">{resolved.reference}</dd></div>
          <div><dt className="text-muted-foreground">Último resultado válido</dt><dd className="mt-1">{resolved.lastSuccessAt ?? "não disponível"}</dd></div>
        </dl>
        <div className="flex flex-wrap gap-2">
          <Button type="button" size="sm" onClick={onRetry} disabled={retrying} aria-busy={retrying}>
            <RefreshCw className={retrying ? "animate-spin motion-reduce:animate-none" : ""} aria-hidden="true" />
            {retrying ? "Tentando novamente…" : "Tentar novamente"}
          </Button>
          {resolved.lastSuccessAt && onUseCached && (
            <Button type="button" variant="outline" size="sm" onClick={onUseCached}>
              Continuar com último resultado
            </Button>
          )}
          {onResetFilters && (
            <Button type="button" variant="outline" size="sm" onClick={onResetFilters}>
              Rever filtros
            </Button>
          )}
        </div>
      </AlertDescription>
    </Alert>
  );
}

function PartialBanner({ missingSources = ["ServiceNow", "Apollo"] }: { missingSources?: readonly string[] }) {
  return (
    <Alert variant="warning" className="my-4">
      <DatabaseZap aria-hidden="true" />
      <AlertTitle>Dados parciais · 4 de 6 fontes disponíveis</AlertTitle>
      <AlertDescription>
        Fontes indisponíveis: {missingSources.join(", ")}. Métricas e correlações podem estar
        subestimadas até a próxima atualização.
      </AlertDescription>
    </Alert>
  );
}

function StaleBanner({
  lastSuccessAt,
  retrying,
  onRetry,
}: {
  lastSuccessAt?: string;
  retrying: boolean;
  onRetry: () => void;
}) {
  return (
    <Alert variant="warning" className="my-4">
      <Clock3 aria-hidden="true" />
      <AlertTitle>Dados desatualizados</AlertTitle>
      <AlertDescription className="flex flex-wrap items-center justify-between gap-3">
        <span>Último resultado válido: {lastSuccessAt ?? "20:04:12"}. A atualização automática falhou.</span>
        <Button type="button" variant="outline" size="sm" onClick={onRetry} disabled={retrying} aria-busy={retrying}>
          <RefreshCw className={retrying ? "animate-spin motion-reduce:animate-none" : ""} aria-hidden="true" />
          Atualizar agora
        </Button>
      </AlertDescription>
    </Alert>
  );
}

function demoFailure(): QueryFailure {
  return {
    kind: "timeout",
    cause: "A consulta excedeu 8 segundos ao cruzar as fontes do recorte. Os filtros foram preservados.",
    reference: "ARG-DEMO-TIMEOUT-504",
    occurredAt: "20:11:06",
    lastSuccessAt: "20:04:12",
    retryable: true,
  };
}
