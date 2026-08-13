// A URL da API vem do ambiente de build e NUNCA fica escrita aqui. Enquanto as
// APIs não tiverem autenticação (arquitetura.md §8.1), a URL é na prática a
// única barreira entre os eventos e qualquer pessoa na internet -- commitá-la é
// entregar o acesso junto com o código.
//
// Defina NEXT_PUBLIC_API_URL antes do build:
//   cd apps/basica/infra && terraform output -raw read_api_url
const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "";

if (!API_URL) {
  // Falha barulhenta e cedo. Sem isso, o fetch iria para o próprio domínio do
  // site estático, devolveria o HTML da página e quebraria no JSON.parse, com
  // uma mensagem que não explica nada.
  throw new Error(
    "NEXT_PUBLIC_API_URL não definida. Rode `make frontend-build` ou exporte a " +
      "variável antes de `next build`.",
  );
}

export type ApiEvent = {
  action: string | null;
  app_bucket: string | null;
  app_env: string | null;
  app_target: string | null;
  app_version: string | null;
  attributes: Record<string, unknown>;
  clock_skew: boolean;
  device_id: string;
  device_manufacturer: string | null;
  device_model: string | null;
  device_model_year: number | string | null;
  device_os: string | null;
  device_os_version: string | null;
  duration_ms: number | null;
  event_id: string;
  event_name: string;
  ingested_at: string | null;
  occurred_at: string;
  route_path: string | null;
  session_id: string;
};

export type EventsResponse = {
  items: ApiEvent[];
  next_cursor: string | null;
  query: { strategy: string; scanned: number; returned: number; queries: number };
};

export type EventFilters = {
  eventName?: string;
  platform?: string;
  manufacturer?: string;
  from?: string;
  to?: string;
};

export async function fetchEvents(filters: EventFilters, signal?: AbortSignal): Promise<EventsResponse> {
  const params = new URLSearchParams({ limit: "100" });
  if (filters.eventName) params.set("event_name", filters.eventName);
  if (filters.platform) params.set("device_os", filters.platform);
  if (filters.manufacturer) params.set("device_manufacturer", filters.manufacturer);
  if (filters.from) params.set("from", filters.from);
  if (filters.to) params.set("to", filters.to);

  const response = await fetch(`${API_URL}/api/v1/events?${params}`, { signal });
  if (!response.ok) throw new Error(`A API respondeu com status ${response.status}`);
  return response.json();
}
