import { createHttpHypothesesSource } from "./http-source";
import type { HypothesesSource } from "./types";
import { fetchHypothesesFromMock } from "../_mocks/source";

type HypothesesSourceName = "api" | "mock";

/** Resolve uma única vez o adapter escolhido no ambiente de build. */
export const fetchHypotheses: HypothesesSource = resolveHypothesesSource(
  process.env.NEXT_PUBLIC_HYPOTHESES_SOURCE,
  process.env.NEXT_PUBLIC_HYPOTHESES_API_URL,
);

function resolveHypothesesSource(
  source: string | undefined,
  apiUrl: string | undefined,
): HypothesesSource {
  if (!isHypothesesSourceName(source)) {
    throw new Error(
      "NEXT_PUBLIC_HYPOTHESES_SOURCE deve ser definida como `mock` ou `api`.",
    );
  }

  if (source === "mock") return fetchHypothesesFromMock;

  if (!apiUrl) {
    throw new Error(
      "NEXT_PUBLIC_HYPOTHESES_API_URL é obrigatória quando " +
        "NEXT_PUBLIC_HYPOTHESES_SOURCE=api.",
    );
  }

  return createHttpHypothesesSource(apiUrl);
}

function isHypothesesSourceName(
  source: string | undefined,
): source is HypothesesSourceName {
  return source === "mock" || source === "api";
}
