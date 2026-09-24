/**
 * TI-01 contra o caminho orquestrado por Kubernetes.
 *
 * O `playwright.config.ts` sobe um Flask avulso e serve o `out/` por um
 * `http.server`: duas origens, com CORS, que é a topologia da implantação até a
 * Sprint 3. Este aqui não sobe nada. Ele aponta para um cluster já de pé, onde
 * o Ingress serve o dashboard em `/` e a API em `/api` no MESMO endereço.
 *
 * A diferença não é de configuração do teste, é de artefato sob teste: aqui o
 * navegador carrega a imagem que vai para o registro, construída com
 * `NEXT_PUBLIC_API_URL=/`, servida pelo mesmo nginx do cluster. O
 * `playwright.config.ts` testa um bundle construído na hora, com o endereço do
 * Flask compilado dentro.
 *
 * Local, com kind:
 *
 *     make -C apps/fullstack kind-up k8s-images kind-load
 *     make -C apps/fullstack k8s-apply k8s-migrate K8S_OVERLAY=kind
 *     kubectl -n argus exec -i deploy/argus-postgres -- \
 *       psql -v ON_ERROR_STOP=1 -U argus -d argus < tests/e2e/fixture.sql
 *     npm run test:e2e:k8s
 *
 * Contra o EKS, o mesmo comando com `ARGUS_E2E_BASE_URL=$(make -s k8s-url)` --
 * e, lá, o fixture entra pelo Job de migration ou por túnel, porque o RDS não é
 * alcançável de fora.
 */
import { defineConfig, devices } from "@playwright/test";

/** Endereço do Ingress. No kind, o `kind-cluster.yaml` publica a 8080. */
const baseURL = process.env.ARGUS_E2E_BASE_URL ?? "http://localhost:8080";

export default defineConfig({
  testDir: "./tests/e2e",
  // A captura de telas para a documentação não faz parte desta suíte.
  testIgnore: ["**/capturas.spec.ts"],
  fullyParallel: false,
  workers: 1,
  timeout: 30_000,
  expect: { timeout: 10_000 },
  reporter: [["list"]],
  use: {
    baseURL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
  // Sem `webServer`: o cluster é pré-condição, não algo que o teste levanta. Se
  // não estiver no ar, a falha tem que ser evidente -- e não mascarada por um
  // Flask local que o Playwright subiria por conta própria.
});
