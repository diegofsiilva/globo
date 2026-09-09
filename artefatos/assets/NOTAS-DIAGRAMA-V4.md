# Ajustes pendentes no diagrama v4

> Lista fechada do que precisa mudar em `arquitetura-implantacao-v4.svg` para que
> a figura descreva a infraestrutura **escrita no Terraform**, e não a topologia
> que se pretendia quando ela foi desenhada. Conferida linha a linha contra
> `apps/basica/infra/` em 08/09/2026.
>
> Os números de linha são do SVG e valem enquanto ele não for reeditado. Depois
> de aplicar tudo, **reexportar o PNG** com um dos comandos da seção 2.1 do
> artefato e commitar os dois arquivos juntos.

---

## 1. Prioridade alta — a figura afirma coisas que deixaram de ser verdade

### 1.1 A nota de estado (linhas 451–455)

É o primeiro texto que um avaliador procura, e hoje ele diz que nada existe.

**Está:**

```
Estado em 03/09/2026
topologia planejada; nenhum recurso
desta figura está provisionado.
O traço laranja marca o que ainda
não existe no Terraform.
```

**Deve ficar:**

```
Estado em 08/09/2026
rede, bastion, ALB, Auto Scaling Group
e RDS escritos e validados no Terraform.
O traço laranja marca o que ainda
não existe: CloudFront e RDS standby.
```

Evitar a palavra "provisionado" sem qualificação. O Terraform foi validado
(`terraform validate`, `terraform fmt`, `make check`), não aplicado numa conta —
a distinção está registrada ao fim da seção 1.2 do artefato, e a figura não deve
contradizê-la.

### 1.2 Porta da aplicação: 8000 → 5000 (linhas 187, 224, 261, 275, 415, 417)

A figura diz 8000 em seis lugares. A porta real é **5000**: é o que
`backend/Dockerfile` expõe (`EXPOSE 5000`), o que o gunicorn usa
(`--bind 0.0.0.0:5000`) e o valor padrão de `var.app_port`.

| Linha | Está | Deve ficar |
|---|---|---|
| 187 | `porta 8000 · usuário argus_api` | `porta 5000 · usuário argus_api` |
| 261 | `porta 8000 · usuário argus_api` | `porta 5000 · usuário argus_api` |
| 415 | `HTTP 8000` (rótulo da seta ALB → EC2, AZ-a) | `HTTP 5000` |
| 417 | `HTTP 8000` (rótulo da seta ALB → EC2, AZ-b) | `HTTP 5000` |
| 224 e 275 | ver 1.3 abaixo, que muda a linha inteira | — |

### 1.3 Listener 443 → 80 (linhas 224 e 275)

Sem CloudFront não há certificado ACM, e sem certificado não há listener HTTPS.
O ALB serve **HTTP na porta 80** (`aws_lb_listener.http` em `alb.tf`).

**Está** (nas duas linhas, uma por nó do ALB):

```
listener 443 · target group HTTP 8000
```

**Deve ficar:**

```
listener 80 · target group HTTP 5000
```

### 1.4 Caminho do health check (linhas 190, 225, 264, 276)

A figura diz `/health`. A rota real é **`/health/live`** — `/health` não existe.

| Linha | Está | Deve ficar |
|---|---|---|
| 190 | `/health para o target group` | `/health/live para o target group` |
| 264 | `/health para o target group` | `/health/live para o target group` |
| 225 | `health check /health · 2 de 2 · 30 s` | `health check /health/live · 2 de 2 · 30 s` |
| 276 | `health check /health · 2 de 2 · 30 s` | `health check /health/live · 2 de 2 · 30 s` |

### 1.5 CloudFront volta a ser "planejado" (bloco a partir da linha 294)

O nó do CloudFront está em **roxo** (`new-face` / `new-top` / `new-side`), que na
legenda significa "acrescentado nesta revisão". Ele não foi acrescentado: ficou
fora do escopo desta sprint.

- Trocar as classes das três faces do nó de `new-*` para `planned-*`.
- A seta do navegador ao CloudFront e a seta do CloudFront ao S3 «frontend»
  passam de `flow` para `flow-plan` (laranja tracejada).
- A seta do CloudFront ao ALB (`HTTPS · /api/*`) idem.

### 1.6 A seta do navegador ao ALB (linha 440 e vizinhança)

Enquanto o CloudFront não existir, o navegador fala **direto com o ALB, em HTTP**.

- O rótulo `HTTPS 443` da seta que chega ao ALB passa a `HTTP 80`.
- Acrescentar uma seta direta **Navegador do usuário → Application Load
  Balancer**, sólida (`flow`), rotulada `HTTP 80 · Bearer`, já que hoje é esse o
  caminho real da requisição do dashboard.
- A seta que hoje liga o navegador ao S3 «frontend» pelo CloudFront deve ter uma
  versão sólida direta ao endpoint de website do S3, rotulada `HTTP 80`.

---

## 2. Prioridade média — componentes que existem e não estão desenhados

### 2.1 Bucket de access logs do ALB

`aws_s3_bucket.alb_logs` (`vpc_logs.tf`) não aparece na figura. Acrescentar um nó
`«object storage» Amazon S3 — bucket «alb-logs»` na faixa transversal inferior,
com seta tracejada fina partindo do ALB, rotulada `access logs`.

### 2.2 Repositório ECR do backend

O nó do ECR fala de "imagens marcadas pelo SHA". Agora há **cinco** repositórios,
e um deles serve o caminho síncrono. Atualizar o texto do artefato interno para
`5 repositórios · backend, worker, simulator, processing, loader`.

### 2.3 Seta do boot da EC2 ao Secrets Manager

O `user_data` lê o SHA-256 do token no Secrets Manager durante o boot
(`asg.tf` → `templates/user_data.sh.tftpl`). É dependência real de inicialização
e não aparece. Acrescentar seta tracejada do nó EC2 ao Secrets Manager, rotulada
`boot · hash do token`.

### 2.4 Seta do boot da EC2 ao ECR

Mesma razão: a instância puxa a imagem no boot. Seta do nó EC2 ao ECR, rotulada
`boot · docker pull`.

### 2.5 O nó do Lambda «authorizer» mudou de papel

Hoje o artefato interno diz `protege ingestão e leitura`. A leitura deixou de
passar por ele: a validação do Bearer agora é do Flask, dentro da instância
(`telemetry/interfaces/auth.py`).

- Trocar o texto para `protege a ingestão · cache 5 min · falha fechada`.
- Nos dois nós EC2, acrescentar uma terceira caixa `«artifact»` com
  `valida Bearer · audiência dashboard`.

---

## 3. Prioridade baixa — coerência de legenda e detalhe

### 3.1 Tipo das instâncias

O diagrama não nomeia o tipo. Vale acrescentar, porque a escolha é justificada no
texto: `t4g.small (Graviton, arm64)` nos dois nós EC2 e `t4g.micro` no bastion —
a figura hoje diz `EC2 t3.micro` no bastion, o que ficou desatualizado.

### 3.2 A legenda (linha 456)

O item `planejado, não implementado` continua válido, mas agora se aplica a
**dois** nós: CloudFront e RDS standby. Nenhuma mudança de texto é necessária; é
só conferir, depois de aplicar 1.5, que os dois estão realmente em laranja e que
nenhum outro nó ficou.

### 3.3 CIDR do bastion

A figura diz `SSH 22 só do CIDR do time`, o que está correto e é bom que esteja
explícito — a validação do Terraform recusa `0.0.0.0/0`. Nenhuma mudança.

### 3.4 O que **não** muda

Conferido e correto como está: os CIDRs da VPC e das quatro sub-redes, os nomes
das AZs, `Auto Scaling Group · mín 2 · máx 6`, `Balanceador único, duas AZs`,
`db.t3.medium · privada`, o RDS standby em laranja, todo o bloco de ingestão
(API Gateway, SQS, DLQs, Fargate) e a faixa transversal de operação.

---

## 4. Depois de editar

```bash
rsvg-convert -w 3760 -b white \
  artefatos/assets/arquitetura-implantacao-v4.svg \
  -o artefatos/assets/arquitetura-implantacao-v4.png
```

Commitar SVG e PNG **no mesmo commit**. Em seguida, escrever o parágrafo de
leitura do diagrama que falta na seção 2 do artefato — ele deve descrever o
caminho da requisição do dashboard como ele é hoje: navegador → ALB (HTTP 80) →
instância do ASG (HTTP 5000) → RDS, e não o caminho com CloudFront.
