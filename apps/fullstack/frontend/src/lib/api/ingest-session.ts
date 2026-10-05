/** Credencial de escrita separada do token de leitura; nunca vai para o bundle. */
const CHAVE = "argus-ingest-token";
const EVENTO = "argus-ingest-session";

/** Lê o token de ingestão apenas da aba atual. */
export function lerTokenIngestao(): string | null {
  try { return window.sessionStorage.getItem(CHAVE); } catch { return null; }
}

/** Salva somente uma credencial já aceita pelo serviço e avisa a interface. */
export function gravarTokenIngestao(token: string): void {
  window.sessionStorage.setItem(CHAVE, token);
  window.dispatchEvent(new Event(EVENTO));
}

/** Expiração da escrita não encerra a sessão de leitura do dashboard. */
export function limparTokenIngestao(): void {
  try { window.sessionStorage.removeItem(CHAVE); } catch { /* Sem armazenamento. */ }
  window.dispatchEvent(new Event(EVENTO));
}

/** Observa autenticação de escrita sem persistir credenciais entre abas. */
export function observarTokenIngestao(listener: () => void): () => void {
  window.addEventListener(EVENTO, listener);
  return () => window.removeEventListener(EVENTO, listener);
}
