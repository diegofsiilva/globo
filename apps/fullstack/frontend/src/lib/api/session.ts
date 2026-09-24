/**
 * Sessão de acesso do dashboard: onde o token de leitura vive no navegador.
 *
 * O token **nunca** entra no bundle. Ele não é `NEXT_PUBLIC_*`, não vem de
 * variável de build e não aparece em nenhum arquivo do repositório — quem o
 * fornece é o operador, colando na tela de acesso. Um token embutido no bundle
 * estaria disponível para qualquer visitante da distribuição, o que anularia a
 * autenticação inteira.
 *
 * Guardado em `sessionStorage`, e não em `localStorage` nem em cookie:
 *
 * - `localStorage` sobrevive ao fechamento do navegador. Numa máquina
 *   compartilhada — o cenário de uma sala de operação — a credencial ficaria
 *   disponível para o próximo turno.
 * - Cookie seria enviado automaticamente em toda requisição ao domínio,
 *   inclusive nas que o operador não iniciou (CSRF). O header explícito só
 *   viaja quando este código o coloca.
 * - `sessionStorage` é por aba e some ao fechá-la, que é a duração certa para
 *   uma sessão de trabalho.
 *
 * A URL também está fora de questão: ficaria no histórico, no `Referer` e em
 * qualquer print da tela.
 */

/**
 * Chave no `sessionStorage`. Prefixada para não colidir com o `argus-theme`
 * gravado pelo `next-themes`.
 */
const CHAVE = "argus-access-token";

type Ouvinte = (token: string | null) => void;

const ouvintes = new Set<Ouvinte>();

/**
 * Lê o token da sessão atual.
 *
 * @returns O token, ou `null` quando não há sessão. Também devolve `null`
 *   durante a renderização no servidor, onde `sessionStorage` não existe — o
 *   export estático pré-renderiza as páginas em build, e um acesso direto ao
 *   objeto global quebraria esse passo.
 */
export function lerToken(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.sessionStorage.getItem(CHAVE);
  } catch {
    // Navegador com armazenamento bloqueado (modo restrito, política de
    // privacidade). Tratar como "sem sessão" mantém a tela de acesso visível,
    // que é honesto: sem onde guardar, não há sessão.
    return null;
  }
}

/**
 * Grava o token e notifica quem estiver observando.
 *
 * @param token Token de leitura colado pelo operador.
 */
export function gravarToken(token: string): void {
  try {
    window.sessionStorage.setItem(CHAVE, token);
  } catch {
    // Segue em frente: o token continua em memória nos ouvintes, e a sessão
    // vale até o próximo recarregamento.
  }
  notificar(token);
}

/**
 * Apaga o token da sessão. Chamado pelo cliente HTTP em 401/403 e pelo botão
 * de sair.
 */
export function limparToken(): void {
  try {
    window.sessionStorage.removeItem(CHAVE);
  } catch {
    // Ignorado pelo mesmo motivo de `gravarToken`.
  }
  notificar(null);
}

/**
 * Observa mudanças na sessão.
 *
 * Existe para que o portão de acesso reaja a um 401 disparado por qualquer
 * consulta, em qualquer tela, sem que cada adapter precise conhecer a interface.
 *
 * @param ouvinte Chamado com o token novo, ou `null` quando a sessão cai.
 * @returns Função que cancela a inscrição.
 */
export function observarToken(ouvinte: Ouvinte): () => void {
  ouvintes.add(ouvinte);
  return () => {
    ouvintes.delete(ouvinte);
  };
}

/**
 * Avisa todos os ouvintes.
 *
 * @param token Valor novo da sessão.
 */
function notificar(token: string | null): void {
  for (const ouvinte of ouvintes) ouvinte(token);
}

/**
 * Verifica se um texto tem a forma de um token válido antes de gravá-lo.
 *
 * Não valida contra o servidor — quem faz isso é o authorizer. Serve para
 * transformar o erro mais comum (colar com espaço, colar a linha inteira do
 * terminal, colar o token errado) num aviso imediato na tela de acesso, em vez
 * de um 403 alguns segundos depois, que o operador leria como "a API caiu".
 *
 * @param valor Texto colado pelo operador.
 * @returns `true` quando são 64 caracteres hexadecimais, que é o formato de um
 *   token de 256 bits gerado por `make auth-rotate`.
 */
export function pareceToken(valor: string): boolean {
  return /^[0-9a-fA-F]{64}$/.test(valor.trim());
}
