// Carga leve e continua para os ensaios de resiliencia no kind.
//
// Nao mede desempenho: existe para contar quantas requisicoes o usuario veria
// falhar ENQUANTO o cluster repoe um pod, faz rollout ou perde o banco.
// Cada falha e impressa com timestamp ISO para cruzar com os eventos do
// kubectl. Sem thresholds de proposito: o codigo de saida do k6 nao deve
// mascarar o resultado -- a contagem e que importa.
//
//   BASE_URL=http://localhost:8080 VUS=5 DURACAO=60s k6 run carga_leve.js
import http from "k6/http";
import { check, sleep } from "k6";
import { Counter } from "k6/metrics";

const respostas200 = new Counter("respostas_200");
const respostasNao200 = new Counter("respostas_nao_200");

export const options = {
  vus: Number(__ENV.VUS || 5),
  duration: __ENV.DURACAO || "60s",
  summaryTrendStats: ["avg", "med", "p(95)", "max"],
  // Uma falha de conexao (status 0) tambem conta como falha do usuario.
  throw: false,
};

const BASE = (__ENV.BASE_URL || "http://localhost:8080").replace(/\/$/, "");
const ROTAS = (__ENV.ROTAS || "/api/v1/clock,/api/v1/hypotheses").split(",");

export default function () {
  for (const rota of ROTAS) {
    const res = http.get(`${BASE}${rota}`, {
      tags: { rota },
      timeout: "5s",
    });
    if (res.status === 200) {
      respostas200.add(1);
    } else {
      respostasNao200.add(1);
      console.log(
        `${new Date().toISOString()} FALHA vu=${__VU} ${rota} status=${res.status} ${res.error || ""}`.trim()
      );
    }
    check(res, { "status 200": (r) => r.status === 200 });
  }
  sleep(Number(__ENV.PAUSA_S || 0.2));
}
