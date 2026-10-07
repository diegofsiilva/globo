/** Revisão local do envelope de eventos definido em argus_worker/models.py. */
import type { Previa } from "./previa-contrato";

/** Campos suportados nesta revisão; campos extras continuam no arquivo original. */
export const CAMPOS_EVENTO = [
  { id: "timestamp", tipo: "data", obrigatorio: true, ajuda: "Data e hora ISO 8601; sem fuso, UTC." },
  { id: "event_name", tipo: "texto", obrigatorio: true, ajuda: "Nome do evento, como request ou vitals." },
  { id: "session_id", tipo: "texto", obrigatorio: true, ajuda: "Identificador da sessão; zeros iniciais são preservados." },
  { id: "device_id", tipo: "texto", obrigatorio: true, ajuda: "Identificador do dispositivo." },
  { id: "event_id", tipo: "texto", obrigatorio: false, ajuda: "Identidade da origem, quando fornecida." },
  { id: "user_id", tipo: "texto", obrigatorio: false, ajuda: "Identificador do usuário." },
  { id: "app_version", tipo: "texto", obrigatorio: false, ajuda: "Versão do aplicativo." },
  { id: "device_model", tipo: "texto", obrigatorio: false, ajuda: "Modelo do dispositivo." },
  { id: "duration", tipo: "numero", obrigatorio: false, ajuda: "Número finito com ponto decimal; unidade da fonte." },
  { id: "request_status", tipo: "inteiro", obrigatorio: false, ajuda: "Status da requisição, como 200 ou 500." },
  { id: "media_ads", tipo: "booleano", obrigatorio: false, ajuda: "true, false, 1 ou 0." },
  { id: "media_drm", tipo: "booleano", obrigatorio: false, ajuda: "true, false, 1 ou 0." },
] as const;

/** Nome de campo do destino de eventos de TV. */
export type CampoEvento = (typeof CAMPOS_EVENTO)[number]["id"];

/** Índice da coluna escolhida por campo; ausência significa não mapeado. */
export type Mapeamento = Partial<Record<CampoEvento, number | null>>;

/** Problema local de mapeamento ou de uma linha, numerada a partir de um. */
export type ProblemaMapeamento = { campo: string; linha?: number; mensagem: string };

/** Resultado restrito à amostra, sem indicar sucesso de ingestão. */
export type ValidacaoMapeamento = {
  erros: ProblemaMapeamento[];
  avisos: string[];
  linhasValidas: number;
  totalLinhas: number;
};

const EVENTOS_CONHECIDOS = new Set(["request", "screen_view", "session", "video_view", "vitals", "error"]);

/** Sugere somente nomes iguais, sem inferir aliases ou resolver ambiguidades. */
export function sugerirMapeamento(previa: Previa): Mapeamento {
  const mapeamento: Mapeamento = {};
  for (const campo of CAMPOS_EVENTO) {
    const indices = previa.colunas.flatMap((coluna, index) => coluna.nome.trim().toLowerCase() === campo.id ? [index] : []);
    mapeamento[campo.id] = indices.length === 1 ? indices[0] : null;
  }
  return mapeamento;
}

/** Confere o calendário antes de aceitar uma data que JavaScript normalizaria. */
function dataIsoValida(valor: string): boolean {
  const partes = /^(\d{4})-(\d{2})-(\d{2})[Tt](\d{2}):(\d{2})(?::(\d{2})(?:\.\d{1,6})?)?(?:[Zz]|([+-])(\d{2}):(\d{2}))?$/.exec(valor);
  if (!partes) return false;
  const [, ano, mes, dia, hora, minuto, segundo = "0", , fusoHora = "0", fusoMinuto = "0"] = partes;
  if (+ano < 1 || +hora > 23 || +minuto > 59 || +segundo > 59 || +fusoHora > 23 || +fusoMinuto > 59) return false;
  const data = new Date(0);
  data.setUTCFullYear(+ano, +mes - 1, +dia);
  return data.getUTCFullYear() === +ano && data.getUTCMonth() === +mes - 1 && data.getUTCDate() === +dia;
}

/** Valida o texto observado; não converte nem sobrescreve os valores da origem. */
function problemaTipo(valor: string, tipo: (typeof CAMPOS_EVENTO)[number]["tipo"]): string | null {
  if (tipo === "data" && !dataIsoValida(valor)) return "Use uma data e hora ISO 8601 com calendário e fuso válidos.";
  if (tipo === "numero" && (!/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$/.test(valor) || !Number.isFinite(Number(valor)))) return "Use um número finito com ponto decimal.";
  if (tipo === "inteiro" && (!/^[+-]?\d+$/.test(valor) || !Number.isSafeInteger(Number(valor)))) return "Use um número inteiro sem perda de precisão.";
  if (tipo === "booleano" && !/^(true|false|1|0)$/i.test(valor)) return "Use true, false, 1 ou 0.";
  return null;
}

/** Verifica campos obrigatórios, reutilização de colunas e valores da amostra.
 * @param previa Amostra local; não representa a validação do arquivo inteiro.
 * @param mapeamento Coluna de origem escolhida para cada campo de destino.
 * @returns Problemas por campo/linha e avisos, sem produzir payload de upload.
 */
export function validarMapeamento(previa: Previa, mapeamento: Mapeamento): ValidacaoMapeamento {
  const erros: ProblemaMapeamento[] = [];
  const avisos = new Set<string>();
  const utilizadas = new Map<number, CampoEvento>();
  const camposValidos: { campo: (typeof CAMPOS_EVENTO)[number]; indice: number }[] = [];
  for (const campo of CAMPOS_EVENTO) {
    const indice = mapeamento[campo.id];
    if (indice === null || indice === undefined) {
      if (campo.obrigatorio) erros.push({ campo: campo.id, mensagem: "Selecione uma coluna para este campo obrigatório." });
      continue;
    }
    if (!Number.isInteger(indice) || indice < 0 || indice >= previa.colunas.length) {
      erros.push({ campo: campo.id, mensagem: "A coluna selecionada não existe nesta amostra." });
      continue;
    }
    const anterior = utilizadas.get(indice);
    if (anterior) erros.push({ campo: campo.id, mensagem: `Esta coluna já foi usada em ${anterior}. Escolha outra coluna.` });
    else utilizadas.set(indice, campo.id);
    camposValidos.push({ campo, indice });
  }
  const erroEstrutura = erros.length > 0;
  if (!previa.linhas.length) erros.push({ campo: "amostra", mensagem: "A amostra não contém registros para validar." });
  let linhasValidas = 0;
  previa.linhas.forEach((linha, numero) => {
    let valida = !erroEstrutura;
    for (const { campo, indice } of camposValidos) {
      const valor = (linha[indice] ?? "").trim();
      let problema: string | null = null;
      if (previa.naoEscalares?.[numero]?.[indice]) problema = "Conteúdo estruturado ou binário não pode ser mapeado para este campo escalar.";
      else if (previa.truncadas?.[numero]?.[indice]) problema = "O valor está cortado na prévia e não pode ser validado integralmente.";
      else if (!valor && campo.obrigatorio) problema = "O campo obrigatório está vazio.";
      else if (valor) problema = problemaTipo(valor, campo.tipo);
      if (problema) {
        erros.push({ campo: campo.id, linha: numero + 1, mensagem: problema });
        valida = false;
      }
      if (campo.id === "timestamp" && valor && !problema && !/(?:z|[+-]\d{2}:\d{2})$/i.test(valor)) avisos.add("Datas sem fuso serão interpretadas como UTC, conforme o worker.");
      if (campo.id === "event_name" && valor && !EVENTOS_CONHECIDOS.has(valor)) avisos.add("Há tipos de evento desconhecidos na amostra; o worker os aceita como eventos genéricos.");
    }
    if (valida) linhasValidas += 1;
  });
  const ignoradas = previa.colunas.filter((_, index) => !utilizadas.has(index)).length;
  if (ignoradas) avisos.add(`${ignoradas} coluna(s) não mapeada(s), fora desta revisão. O arquivo original permanece intacto.`);
  return { erros, avisos: [...avisos], linhasValidas, totalLinhas: previa.linhas.length };
}
