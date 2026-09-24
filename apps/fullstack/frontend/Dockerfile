# syntax=docker/dockerfile:1.7
#
# Imagem do dashboard. O contexto de build e frontend/ -- e nao apps/fullstack/ --
# porque o dashboard nao depende de common/ nem de nenhum outro app.
#
#   docker build -f frontend/Dockerfile -t argus-frontend:dev frontend
#
# Diferente das cinco imagens Python, esta e construida para amd64 E arm64
# (`make image-frontend`): as node pools padrao do EKS Auto Mode sao amd64,
# enquanto as maquinas do time e o Fargate do caminho assincrono sao arm64.
# Uma imagem so para as duas arquiteturas evita o `exec format error` que ja
# mordeu o time no ASG (infraestrutura-integracao.md, secao 4).
#
# O resultado NAO e um servidor Next: o next.config.ts usa `output: "export"`,
# entao o build gera HTML estatico e quem serve e o nginx. E a mesma saida que
# o `make frontend-deploy` sobe para o S3 -- a imagem apenas embrulha aquele
# mesmo `out/` para rodar no cluster.

FROM node:20-bookworm-slim@sha256:2cf067cfed83d5ea958367df9f966191a942351a2df77d6f0193e162b5febfc0 AS builder

WORKDIR /app

# Dependencias primeiro, em camada propria: mexer no src/ nao invalida o cache
# do npm, que e a parte cara do build. `npm ci` e nao `npm install` porque ele
# obedece ao package-lock.json em vez de reresolver os intervalos.
COPY package.json package-lock.json ./
RUN --mount=type=cache,target=/root/.npm \
    npm ci

COPY . .

# A URL da API entra no bundle em tempo de build -- o export estatico nao le
# variavel de ambiente em runtime. O valor "/" faz o cliente montar caminhos
# relativos (ver frontend/src/lib/api/client.ts), de modo que o dashboard e a
# API sejam servidos pela MESMA origem atraves do Ingress. Isso elimina o CORS
# e torna a imagem independente do endereco do ambiente: a mesma tag roda no
# kind e no EKS sem rebuild.
ARG NEXT_PUBLIC_API_URL=/
ARG NEXT_PUBLIC_HYPOTHESES_SOURCE=mock
ARG NEXT_PUBLIC_HYPOTHESES_API_URL=

# O mesmo build-info.json que `make frontend-build-info` grava. Escrito aqui, e
# nao copiado do contexto, para que o commit registrado seja o da imagem e nao
# o que por acaso estava na maquina de quem construiu.
ARG GIT_SHA=desconhecido
RUN printf '{\n  "commit": "%s",\n  "built_at": "%s",\n  "version": "%s"\n}\n' \
      "$GIT_SHA" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
      "$(node -p "require('./package.json').version")" \
      > public/build-info.json

ENV NEXT_TELEMETRY_DISABLED=1
RUN NEXT_PUBLIC_API_URL="$NEXT_PUBLIC_API_URL" \
    NEXT_PUBLIC_HYPOTHESES_SOURCE="$NEXT_PUBLIC_HYPOTHESES_SOURCE" \
    NEXT_PUBLIC_HYPOTHESES_API_URL="$NEXT_PUBLIC_HYPOTHESES_API_URL" \
    npm run build


FROM nginx:1.27-alpine@sha256:65645c7bb6a0661892a8b03b89d0743208a18dd2f3f17a54ef4b76fb8e2f2a10 AS runtime

# O usuario `nginx` (uid 101) ja vem na imagem oficial. Reusa-lo em vez de
# criar outro mantem a propriedade dos diretorios que a imagem ja preparou.
COPY nginx.conf /etc/nginx/nginx.conf
COPY --from=builder --chown=nginx:nginx /app/out /usr/share/nginx/html

# Os diretorios temporarios do nginx.conf precisam existir e ser graváveis
# antes de o processo largar o root -- com readOnlyRootFilesystem no pod, /tmp
# e o unico lugar onde ele consegue escrever.
RUN mkdir -p /tmp/client_temp /tmp/proxy_temp /tmp/fastcgi_temp \
             /tmp/uwsgi_temp /tmp/scgi_temp \
 && chown -R nginx:nginx /tmp/client_temp /tmp/proxy_temp /tmp/fastcgi_temp \
             /tmp/uwsgi_temp /tmp/scgi_temp

USER nginx

# 8080 e nao 80: ver o comentario no topo do nginx.conf.
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD wget --quiet --tries=1 --spider http://127.0.0.1:8080/healthz || exit 1

CMD ["nginx", "-g", "daemon off;"]
