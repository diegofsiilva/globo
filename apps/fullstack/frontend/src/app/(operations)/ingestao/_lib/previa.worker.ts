/** Isola parsing e descompressão da interface; encerramento cancela a leitura. */
import { lerPrevia } from "./previa";
import type { RespostaPrevia } from "./previa-contrato";

self.onmessage = async (evento: MessageEvent<File>) => {
  let resposta: RespostaPrevia;
  try {
    resposta = { previa: await lerPrevia(evento.data) };
  } catch (erro) {
    resposta = { erro: erro instanceof Error ? erro.message : "Falha ao ler a amostra do arquivo." };
  }
  self.postMessage(resposta);
};
