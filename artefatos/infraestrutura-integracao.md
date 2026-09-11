# Infraestrutura e integração

&emsp; Este artefato documenta o provisionamento da infraestrutura em nuvem e a
integração entre o front-end e o back-end do Argus. O texto foi finalizado na branch
`docs/Videosdaimplementação` e conferido em 10 de setembro de 2026 numa conta do AWS
Academy Learner Lab, na região `us-east-1`. Identificadores da conta, credenciais e
tokens não são registrados: as evidências usam nomes lógicos, estados e contagens
suficientes para reproduzir e avaliar o ambiente sem expor segredos temporários.

## Divergências de nomenclatura

| Especificação | Repositório | Tratamento |
|---|---|---|
| `infraestrutura_integracao.md` (seção de vídeos) e `infraestrutura-integracao.md` (cabeçalho) | `artefatos/infraestrutura-integracao.md` | Adotado o hífen, coerente com `arquitetura-inicial.md` e com os links já existentes no repositório |
| `/apps/fullstack` | `apps/basica` | Mantido o nome histórico `apps/basica` para não quebrar Makefile, caminhos de build e referências entre artefatos; a divergência fica registrada aqui |

## Rastreabilidade da rubrica

&emsp; A tabela consolida os nove itens avaliados. O item de análise de impacto nos
ODS da ONU foi dispensado pelo professor em 4 de setembro de 2026 por já estar
contemplado no artefato de negócios. O status abaixo considera a documentação,
as verificações de 10 de setembro e os dois vídeos publicados.

| # | Item da rubrica | Peso | Onde está | Status |
|---|---|---|---|---|
| R-a | Diagrama de implantação com ênfase em nuvem | 1,0 | Seção 2 | pronto |
| R-b | Descrição dos componentes e justificativa | 1,0 | Seção 3 | pronto |
| R-c | Plano de deploy na AWS, incluindo CloudFront | 1,0 | Seção 4 | pronto |
| V1-a | VPC, sub-redes pública e privada, NAT, logs distribuídos | 1,0 | Seções 3.1, 4.6 e 6 | pronto |
| V1-b | Bastion Host com regras seguras de acesso | 1,0 | Seções 3.2 e 6 | pronto |
| V1-c | ASG de EC2 com política de escalonamento + ALB | 1,0 | Seções 3.3, 5 e 6 | pronto |
| V1-d | Banco de dados em RDS | 1,0 | Seções 3.4 e 6 | pronto |
| V2-a | Testes de validação funcional | 1,0 | Seção 7 | pronto |
| V2-b | Comunicação entre serviços em ambiente integrado | 1,0 | Seção 7 | pronto |

&emsp; O item R-c avalia o plano de inclusão do CloudFront, não a existência da
distribuição no Learner Lab. A seção 4.4 registra a topologia recomendada e deixa
explícito que o recurso não foi criado nesta sprint.

---

## 1. Contexto e escopo

&emsp; O Argus é um sistema de telemetria e correlação de falhas para a cadeia de
entrega de streaming do Grupo Globo. Aplicações cliente enviam eventos a uma API de
ingestão; o pipeline normaliza, persiste e expõe os dados a um dashboard que apresenta
a linha do tempo do incidente e as hipóteses de causa provável. A arquitetura
consolidada até a sprint anterior está descrita em
[`arquitetura-inicial.md`](arquitetura-inicial.md); este artefato cobre o que muda na
camada de infraestrutura e na integração entre front-end e back-end.

&emsp; A topologia anterior executa inteiramente sobre a VPC padrão da conta do AWS
Academy Learner Lab. As tasks recebem endereço público (`assign_public_ip = true`)
porque essa era a forma de obter saída para a internet sem provisionar um NAT Gateway,
e o dashboard é servido pelo endpoint de website do Amazon S3, que atende somente em
HTTP. Nenhuma das duas escolhas foi apresentada como definitiva: `arquitetura-inicial.md`
registra a primeira como “concessão do laboratório e não a postura recomendada para
produção” (§4.7) e a segunda como “fallback temporário para demonstração em rede
confiável” (§4.8), esta com a consequência explícita de que o token colado pelo
operador trafega em claro e pode ser observado por um intermediário de rede.

&emsp; Esta revisão implementa a rede própria e acrescenta a camada de
escalabilidade horizontal que faltava ao caminho de leitura. A VPC possui sub-redes
públicas e privadas em duas zonas de disponibilidade; as cargas privadas alcançam a
internet pelo NAT Gateway; o acesso administrativo passa pelo bastion; e uma versão
da API de leitura executa em instâncias EC2 sob Auto Scaling Group, atrás de um
Application Load Balancer. A Lambda de leitura foi mantida durante a transição e é o
caminho usado pelo dashboard no Vídeo 2. O CloudFront, que fecharia a dívida de TLS do
site S3, permanece planejado e não é apresentado como recurso implantado.

&emsp; A migração é deliberadamente parcial. O caminho síncrono, que é a requisição
feita pelo dashboard e cuja latência o usuário percebe, é o que recebe grupo de
escalonamento e balanceador, porque é onde a variação de carga é observável e onde a
perda de uma instância tem efeito imediato sobre a experiência. O caminho assíncrono
de ingestão permanece em filas com consumidores no ECS Fargate: o desacoplamento por
SQS já absorve rajada, o backlog da fila é a métrica de saúde natural desse fluxo, e
reescrevê-lo sobre EC2 acrescentaria risco de regressão sem ganho arquitetural
correspondente. A seção 3.8 registra a decisão junto com a alternativa descartada.

### 1.1 Legenda de estado

- **Implementado:** existe no código e na infraestrutura Terraform aplicada.
- **Condicional:** existe no Terraform, mas depende de variáveis do ambiente.
- **Planejado:** decisão registrada, ainda sem recurso Terraform.

### 1.2 O que mudou nesta revisão

&emsp; A coluna `Estado` reflete o ambiente verificado em 10 de setembro de 2026.
Itens planejados são descritos como proposta e não como recurso existente.

| Item | Antes | Agora | Estado |
|---|---|---|---|
| Ambiente de rede | VPC padrão da conta, apenas sub-redes públicas | VPC dedicada, sub-redes públicas e privadas em duas AZs | Implementado |
| Saída para a internet das cargas | Endereço público na própria task | NAT Gateway em sub-rede pública | Implementado |
| Acesso administrativo | Task avulsa `migration` dentro da VPC | Bastion host, com a task `migration` mantida | Implementado no ambiente verificado; condicional a `bastion_key_name` em novos deploys |
| API de leitura | AWS Lambda (Flask por `lambda_handler`) | EC2 em Auto Scaling Group atrás de ALB, em paralelo ao caminho Lambda/API Gateway durante a transição | Implementado |
| Elasticidade do caminho síncrono | Concorrência da Lambda, implícita | Política de escalonamento declarada no ASG | Implementado |
| Autenticação da API de leitura | Lambda authorizer do API Gateway | Validação do Bearer dentro do Flask | Implementado |
| Entrega do dashboard | Endpoint de website S3, somente HTTP | CloudFront com TLS e bucket privado por OAC | Planejado; fora do escopo desta sprint |
| Observabilidade de rede | Log de aplicação e alarmes do CloudWatch | Acrescidos VPC Flow Logs, access logs do ALB e painel do CloudWatch | Implementado |
| Ingestão e processamento | API Gateway → SQS → ECS Fargate | Inalterado, realocado para sub-rede privada | Implementado |
| Banco de dados | RDS PostgreSQL 16 privado na VPC padrão | RDS PostgreSQL 16 em subnet group privado da VPC dedicada | Implementado |
| Alta disponibilidade do banco | Instância única | Multi-AZ | Planejado; desligado por custo, ver 5.1 |

&emsp; “Implementado” significa que o recurso existe no Terraform, foi aplicado e
foi observado na conta usada para a gravação. Em 10 de setembro de 2026, o ASG
mantinha duas instâncias `InService`, o target group mostrava dois targets
`healthy`, `/health/live` respondia HTTP 200, o RDS privado estava `available`, o
bastion existia e havia streams recentes no log group da aplicação. A camada de
rede já havia sido verificada em 8 de setembro, inclusive com uma instância privada
saindo pelo NAT sem endereço público. As restrições encontradas no laboratório
estão documentadas na seção 8. CloudFront e o standby Multi-AZ do RDS são as duas
exceções planejadas mostradas no diagrama.

### 1.3 Fora de escopo

&emsp; Este artefato não redescreve o que já está documentado em outro lugar do
repositório. Modelo de dados, migrations, ETL, checkpoints e coordenação do
processamento estão em [`arquitetura-inicial.md`](arquitetura-inicial.md) e em seus
apêndices; os endpoints da API de leitura e a autenticação por token Bearer, em
[`backend.md`](backend.md); as telas do dashboard e as decisões de interface, em
[`frontend.md`](frontend.md); a origem e a correlação dos dados cedidos pelo parceiro,
em [`correlacao_dados.md`](correlacao_dados.md). Referência cruzada substitui cópia:
um mesmo fato mantido em dois artefatos diverge no commit seguinte.

&emsp; Permanece igualmente fora de escopo a camada agêntica de correlação, que
pertence ao roadmap de produção e não ao recorte implantado. A distinção foi
estabelecida em [`entendimento_negocio.md`](entendimento_negocio.md) e é preservada
aqui.

---

## 2. Diagrama de implantação do sistema

<div align="center">

<sub>Figura 1 — Implantação do Argus na AWS, região `us-east-1`</sub>

![Diagrama de implantação do Argus v4](assets/arquitetura-implantacao-v4.png)

<sup>Fonte: material produzido pelos autores (2026).</sup>

</div>

&emsp; A figura separa a VPC, as duas zonas de disponibilidade e as sub-redes
públicas e privadas, deixando visíveis o NAT, o bastion, o ALB, as instâncias do ASG
e o RDS. As ligações sólidas representam recursos e caminhos implementados; o traço
laranja indica o CloudFront e o standby Multi-AZ do RDS, ainda planejados. O caminho
escalável validado parte do navegador para o ALB em HTTP 80, segue para um target na
porta 5000 e chega ao PostgreSQL privado na porta 5432. Durante a transição, o
dashboard demonstrado no Vídeo 2 continua no website S3 e consulta a API de leitura
por API Gateway e Lambda; os dois caminhos coexistem para permitir rollback sem
indisponibilidade.

### 2.1 Fonte editável e exportação

&emsp; A fonte do diagrama é [`assets/arquitetura-implantacao-v4.svg`](assets/arquitetura-implantacao-v4.svg),
SVG escrito à mão e versionado como fonte, na mesma convenção do
`arquitetura-implantacao-v3.svg`, do qual herda o vocabulário visual: nós
tridimensionais com estereótipo, caixas de artefato aninhadas, faixa transversal de
operação e o traço laranja tracejado para o que ainda não existe. Não há binário
intermediário de ferramenta. O PNG publicado no relatório é gerado a partir do SVG e
commitado junto; os dois arquivos andam sempre no mesmo commit, sob pena de a
figura divergir da fonte.

&emsp; O diagrama v3 permanece intacto, porque é a figura referenciada por
[`arquitetura-inicial.md`](arquitetura-inicial.md). Editá-lo no lugar faria o artefato
da sprint anterior exibir infraestrutura que não existia quando aquele texto foi
escrito.

**Exportar o PNG**

&emsp; O SVG tem 3760 × 2454 px de área útil, o que já é resolução suficiente para o
avaliador ampliar a figura. Qualquer um dos comandos abaixo produz o PNG:

```bash
# opção 1: rsvg-convert, mesma linha usada no v3
rsvg-convert -w 3760 -b white \
  artefatos/assets/arquitetura-implantacao-v4.svg \
  -o artefatos/assets/arquitetura-implantacao-v4.png

# opção 2: Chromium headless, quando o rsvg-convert não estiver disponível
chrome --headless --disable-gpu --hide-scrollbars \
  --window-size=3760,2454 --default-background-color=FFFFFFFF \
  --screenshot=artefatos/assets/arquitetura-implantacao-v4.png \
  artefatos/assets/arquitetura-implantacao-v4.svg
```

&emsp; Conferir depois de exportar: o Markdown do GitHub reduz a figura à largura
da coluna de leitura, cerca de 880 px, o que torna os rótulos ilegíveis em linha; o
leitor precisa clicar na imagem para vê-la em tamanho real, e é por isso que o PNG
exportado tem de ser grande. O fundo branco precisa ser explícito, nunca
transparente: no tema escuro do GitHub o texto sumiria.

### 2.2 Convenções de notação

| Elemento | Significado |
|---|---|
| Nó tridimensional | Nó de implantação: ambiente de execução, serviço gerenciado ou dispositivo |
| Preenchimento azul-cinza | Nó que já existia na arquitetura v3 e foi apenas realocado na rede |
| Preenchimento roxo | Nó acrescentado nesta revisão, sem correspondente no diagrama v3 |
| Preenchimento laranja tracejado | Nó planejado, ainda sem recurso no Terraform |
| Caixa branca interna `«artifact»` | Artefato de software implantado naquele nó |
| Retângulo com título no canto superior | Fronteira de rede: VPC, zona de disponibilidade, sub-rede. Toda essa camada é nova nesta revisão |
| Retângulo tracejado sem preenchimento | Agrupamento lógico, como o Auto Scaling Group e o balanceador, que atravessa as zonas de disponibilidade e não é recurso de rede |
| `«…»` | Estereótipo do nó |
| Rótulo da seta | Protocolo e porta efetivamente usados |
| Faixa inferior tracejada | Serviços transversais ao ASG, ao Fargate e ao RDS |

&emsp; Os nós em roxo são a resposta visual à pergunta “o que esta sprint acrescentou”:
Internet Gateway, NAT Gateway, bastion host, os dois nós do Application Load Balancer,
as duas instâncias EC2 do Auto Scaling Group e a estação do administrador. CloudFront
e o RDS standby aparecem em laranja porque ainda não foram provisionados; quando a
distribuição e o Multi-AZ forem habilitados, esses nós passam para roxo.

---

## 3. Componentes e justificativa da arquitetura

&emsp; Esta seção descreve cada componente da topologia implantada e justifica a
escolha. Descrição e justificativa são coisas distintas e as duas são exigidas:
dizer que “o balanceador distribui carga entre as instâncias” é descrever o que
o serviço faz. A justificativa está em qual alternativa foi descartada, contra
qual atributo de qualidade, e a que custo. É isso que a ficha padrão de cada
componente registra, junto com o modo de falha previsto e o arquivo Terraform onde o
recurso vive. A tabela consolidada das decisões está em 3.8.

&emsp; O estado segue a legenda de 1.1. “Implementado” significa que existe no
código Terraform deste repositório e foi validado por `terraform validate` e
`terraform fmt`; “Planejado” significa decisão registrada sem recurso
correspondente. A validação de configuração não é o mesmo que aplicação em
conta: o que o Terraform confirma é sintaxe, tipos e referências entre recursos,
não que o papel `voclabs` do Learner Lab autorize criar cada um deles.

### 3.1 Rede — VPC, sub-redes, NAT e rotas

&emsp; Até esta revisão o sistema inteiro executava sobre a VPC padrão da conta,
com todas as sub-redes públicas e endereço roteável em cada task
(`assign_public_ip = true`). Essa escolha nunca foi apresentada como definitiva:
[`arquitetura-inicial.md`](arquitetura-inicial.md) §4.7 a registra como
“concessão do laboratório e não a postura recomendada para produção”. A rede
dedicada descrita aqui paga essa dívida.

&emsp; As duas chaves andam juntas, e o Terraform recusa a combinação errada.
`create_network = true` com `assign_public_ip = true` põe a task numa sub-rede
privada, que não tem rota para o Internet Gateway: o endereço público não serve
para nada, o download da imagem no ECR falha e o serviço entra em ciclo de
reinicialização. Uma validação cruzada entre as duas variáveis transforma isso em
erro de `plan`, com a explicação junto. Sem ela o sintoma chega horas depois, como
serviço que não estabiliza, e nada aponta para a variável de rede que o causou. As
faixas das sub-redes são derivadas de `vpc_cidr` pelo mesmo motivo: listas fixas
deixariam sub-redes penduradas fora da VPC ao primeiro que trocasse o bloco. O
arquivo `rede.tftest.hcl` exercita as duas regras com um provider simulado, que
responde no lugar da AWS sem criar recurso nenhum.

&emsp; A VPC ocupa o bloco `10.0.0.0/16`. A notação `/16` é o CIDR, a forma de
escrever uma faixa de endereços IP pelo número de bits fixos: `10.0.0.0/16`
reserva os 65.536 endereços entre `10.0.0.0` e `10.0.255.255`, e cada `/24`
recortado dela reserva 256. A VPC tem `enable_dns_hostnames` ligado porque, sem
esse atributo, o endereço do RDS não recebe nome DNS resolvível de dentro da
própria VPC, e a `DATABASE_URL` montada em `locals.tf` apontaria para um host
inexistente. Dentro dela há quatro sub-redes, distribuídas em duas zonas de
disponibilidade. Duas zonas não é preferência de projeto: o Application Load
Balancer exige no mínimo duas sub-redes em zonas distintas e não chega a ser
criado com uma só, e o subnet group do RDS, que é a lista de sub-redes onde o
banco pode nascer, impõe a mesma condição.

| Sub-rede | Tipo | CIDR | AZ | Rota `0.0.0.0/0` | O que executa |
|---|---|---|---|---|---|
| `argus-events-dev-public-0` | pública | `10.0.0.0/24` | 1ª da conta | Internet Gateway | ALB, NAT Gateway, bastion |
| `argus-events-dev-public-1` | pública | `10.0.1.0/24` | 2ª da conta | Internet Gateway | ALB |
| `argus-events-dev-private-0` | privada | `10.0.10.0/24` | 1ª da conta | NAT Gateway | EC2 do ASG, tasks Fargate, RDS |
| `argus-events-dev-private-1` | privada | `10.0.11.0/24` | 2ª da conta | NAT Gateway | EC2 do ASG, tasks Fargate, RDS |

&emsp; As zonas saem de `data.aws_availability_zones.available` e não de
literais `us-east-1a`. O AWS Academy distribui as zonas por conta: o `us-east-1a`
de uma conta pode ser o hardware que outra enxerga como `us-east-1c`, e nem toda
conta recebe a lista completa. Fixar o nome faz o `apply` passar numa conta e
falhar em outra, com a causa aparecendo como “sub-rede inválida” muito depois do
erro real.

&emsp; A diferença entre os dois gateways é o que define a sub-rede privada. O
Internet Gateway é simétrico: deixa sair e deixa entrar. O NAT Gateway é
assimétrico, porque traduz o endereço de saída e não tem como encaminhar uma
conexão iniciada de fora: não existe tradução registrada para ela. A tabela de
rotas privada aponta `0.0.0.0/0` para o NAT e não tem nenhuma rota para o Internet
Gateway. É essa ausência, e não o nome da sub-rede, que impede alcance externo,
mesmo que um security group fosse afrouxado por engano.

&emsp; Os hosts privados precisam de saída por quatro motivos concretos, todos
exercitados no boot de cada instância: baixar pacotes do repositório do Amazon
Linux (`dnf install` de Docker e do agente CloudWatch), autenticar e puxar a
imagem do ECR, ler o segredo dos tokens no Secrets Manager, e entregar log e
métrica ao CloudWatch. Sem NAT, a instância sobe, não encontra o que executar e
reprova na verificação de saúde do balanceador; o grupo entra em ciclo de
substituição, com o sintoma aparecendo como falha da aplicação.

&emsp; Há um único NAT Gateway, na primeira sub-rede pública, e não um por zona. A
recomendação da AWS para produção é um por zona, justamente para que a queda de
uma não leve junto a saída da outra. Aqui a decisão é de custo: cada NAT custa
cerca de US$ 32/mês de hora parada mais o tráfego, e é o item mais caro da
topologia. A consequência está assumida e detalhada em 5.1. Se a zona do NAT cair,
as instâncias da outra zona continuam servindo tráfego, porque o caminho de
leitura não passa pelo NAT, mas perdem a saída, e o ASG não consegue subir
instância nova naquela zona até a zona voltar.

&emsp; Os VPC endpoints de interface não foram criados, e a decisão é consciente.
Um endpoint é uma porta de entrada privada para um serviço da AWS, criada dentro
da própria VPC; ele vem em duas formas. O *gateway endpoint* é uma entrada a mais
na tabela de rotas, serve só S3 e DynamoDB e é gratuito: esse foi criado, para
S3. O *endpoint de interface* é uma placa de rede dentro da sub-rede, atende os
demais serviços e cobra por hora em cada zona. Endpoints de interface para ECR,
Secrets Manager e CloudWatch Logs tirariam esse tráfego do NAT, reduzindo o custo
de transferência e mantendo as chamadas dentro da rede da AWS. O custo de não
usá-los é que todo `docker pull` e toda chamada de API paga tráfego de NAT, e o
caminho até o ECR sai e volta pela borda. Ficaram de fora porque seriam cinco
recursos adicionais, um para ECR API, ECR DKR, Secrets Manager, CloudWatch Logs e
STS, cada um com security group próprio e com custo horário que anula parte da
economia num volume tão pequeno. A decisão está registrada em 3.8 (decisão 4).

**Grupos de segurança**

&emsp; A regra que vale em todo o stack: sempre que a origem for um recurso
nosso, ela referencia outro security group, e não uma faixa de endereços. Uma
sub-rede pode ser renumerada e o IP de uma instância muda a cada substituição do
ASG, mas a identidade do grupo não muda. Há exatamente um `0.0.0.0/0` de entrada
em toda a topologia, e ele está na porta 80 do balanceador, que existe justamente
para aceitar conexão de qualquer origem.

| Security group | Regra de entrada | Origem | Regra de saída | Destino |
|---|---|---|---|---|
| `argus-events-dev-alb` | TCP 80 | `0.0.0.0/0` | TCP 5000 | `sg-app` |
| `argus-events-dev-app` | TCP 5000 · TCP 22 | `sg-alb` · `sg-bastion` | TCP 443, TCP 80, TCP 5432 | saída, `sg-rds` |
| `argus-events-dev-bastion` | TCP 22 | Endereço do time em `/32`; a validação recusa `0.0.0.0/0` | TCP 22, TCP 5432, TCP 443 | `sg-app`, `sg-rds`, saída |
| `argus-events-dev-rds` | TCP 5432 | `sg-worker`, `sg-app`, `sg-bastion` | — | — |
| `argus-events-dev-tasks` | — (nenhuma) | — | TCP 443, TCP 5432 | saída, `sg-rds` |

&emsp; O grupo das tasks Fargate não tem regra de entrada nenhuma, e isso é o
desenho: os workers buscam mensagem na fila por *long polling*, que é uma consulta
de saída que fica aberta esperando a mensagem chegar, e o simulador também só faz
chamada de saída. Ninguém conecta neles. A saída do bastion é restrita a três
destinos em vez de `0.0.0.0/0`: abrir a saída inteira daria a quem o comprometesse
um trampolim para qualquer lugar.

**Observabilidade da rede: logs distribuídos**

&emsp; O log da aplicação responde “o que a API fez com a requisição”. Ele não
responde “a conexão chegou?”, e essa é exatamente a pergunta que aparece quando
um security group está errado: a requisição some sem deixar rastro em lugar
nenhum, porque nunca alcançou o processo que sabe registrá-la. Por isso são três
fontes, em três níveis, e a utilidade está em cruzá-las.

| Fonte | Destino | Retenção | Pergunta que responde |
|---|---|---|---|
| VPC Flow Logs | Bucket `argus-events-dev-flow-logs-<conta>` | 30 dias | Tráfego aceito ou rejeitado, por par origem/destino; conexão inesperada |
| Aplicação nas EC2 do ASG | `/argus/argus-events-dev/app` | 30 dias | Erro por requisição, latência, `X-Request-Id` |
| Access logs do ALB | Bucket `argus-events-dev-alb-logs-<conta>` | 30 dias | Código de resposta e tempo do backend, por requisição |
| Tasks Fargate | `/ecs/argus-events-dev/<serviço>` | 30 dias | Ingestão, ETL, motor de hipóteses |
| API Gateway de ingestão | `/aws/apigateway/argus-events-dev` | 30 dias | Evento recusado na borda |

&emsp; Os Flow Logs usam formato customizado, e não o padrão, porque o padrão não
traz `pkt-srcaddr` e `pkt-dstaddr`, que são os endereços reais antes da tradução do
NAT. Sem eles, todo tráfego de saída das sub-redes privadas aparece originado no
NAT, e fica impossível dizer qual instância falou com quem. O intervalo de
agregação está em 60 segundos e não nos 600 do padrão: numa demonstração ao vivo,
esperar dez minutos pelo primeiro registro é a diferença entre evidenciar o
recurso e falar sobre ele. O destino é um bucket S3, e a razão está na seção 8.1:
o papel do laboratório não consegue assumir a identidade que o serviço usaria para
escrever no CloudWatch Logs.

&emsp; Os access logs do ALB vão para S3 porque o serviço não os entrega no
CloudWatch Logs. Não há escolha de destino aqui; o bucket existe porque o serviço
exige bucket. Ele tem bloqueio total de acesso público e uma regra de ciclo de
vida que expira os objetos em 30 dias: access log cresce por requisição e ninguém
volta nele depois de um mês.

&emsp; A correlação ponta a ponta usa o `X-Request-Id`. O cabeçalho já é
emitido em toda resposta por `telemetry/observability.py` e aparece na linha de
log estruturado da aplicação e no corpo dos erros RFC 7807. Uma requisição que
aparece no flow log e não no access log morreu no security group do balanceador;
uma que aparece no access log com 502 e não no log da aplicação morreu antes do
gunicorn; e uma que aparece nos três é rastreável do navegador até a consulta SQL
pelo mesmo identificador. Esse encadeamento é o procedimento de diagnóstico do
caminho ALB/ASG; o caminho Lambda usado no Vídeo 2 é correlacionado pelo log
estruturado da função de leitura.

**Ficha — VPC e sub-redes**

| Campo | Conteúdo |
|---|---|
| Papel no sistema | Isolamento de rede: define quem alcança quem, e por qual caminho |
| Configuração efetiva | `10.0.0.0/16`; 2 sub-redes públicas `/24` e 2 privadas `/24`, em 2 AZs; DNS e hostnames habilitados |
| Entradas / saídas | Entrada só pelo IGW nas públicas; saída das privadas pelo NAT |
| Estado | Implementado |
| Alternativa descartada | VPC padrão da conta, usada até a v3; ela não tem sub-rede privada, e sem ela não há como remover o IP público das cargas |
| Modo de falha previsto e mitigação | Sub-rede esgotada por crescimento do ASG: um `/24` dá 251 endereços úteis contra o teto de 6 instâncias, folga de duas ordens de grandeza |
| Custo estimado | Sem custo próprio |
| Arquivo Terraform | `apps/basica/infra/vpc.tf` |

**Ficha — NAT Gateway**

| Campo | Conteúdo |
|---|---|
| Papel no sistema | Saída para a internet das sub-redes privadas, sem permitir entrada |
| Configuração efetiva | Um NAT na primeira sub-rede pública, com Elastic IP fixo |
| Entradas / saídas | Recebe das tabelas de rota privadas; sai pelo IGW |
| Estado | Implementado |
| Alternativa descartada | (a) IP público na carga, usado até a v3: mais barato, mas desfaz a rede privada; (b) um NAT por zona, que é a recomendação de produção e dobra o custo |
| Modo de falha previsto e mitigação | Queda da AZ do NAT: as instâncias da outra zona seguem servindo tráfego, mas sem saída; o ASG não sobe instância nova ali. Mitigação declarada: subir o segundo NAT (5.1) |
| Custo estimado | ~US$ 32/mês mais o tráfego; é o item mais caro da topologia |
| Arquivo Terraform | `apps/basica/infra/vpc.tf` |

**Ficha — VPC Flow Logs e access logs do ALB**

| Campo | Conteúdo |
|---|---|
| Papel no sistema | Observabilidade da camada de rede: responde “a conexão chegou?” |
| Configuração efetiva | Flow Logs de todo o tráfego, formato customizado com `pkt-srcaddr`, agregação de 60 s, retenção de 30 dias, entregues em bucket S3 com AES256; access logs do ALB em S3 com expiração de 30 dias |
| Entradas / saídas | VPC → S3 (ou CloudWatch Logs, por `flow_logs_destination`); ALB → S3 |
| Estado | Implementado e aplicado; ver 4.6 |
| Alternativa descartada | (a) Formato padrão de flow log, que oculta o endereço real por trás do NAT; (b) destino CloudWatch Logs, inviável no laboratório porque a `LabRole` não confia em `vpc-flow-logs.amazonaws.com` (seção 8) |
| Modo de falha previsto e mitigação | Volume de log inflando custo: retenção e ciclo de vida de 30 dias em ambos |
| Custo estimado | ~US$ 1–3/mês no volume do laboratório |
| Arquivo Terraform | `apps/basica/infra/vpc_logs.tf` |

### 3.2 Acesso administrativo — Bastion Host

&emsp; As instâncias do Auto Scaling Group e o RDS não têm endereço público, e
esse é o ponto. Mas alguém precisa conseguir abrir um `psql` para investigar um
incidente, ou entrar numa instância para ler um log que não chegou ao CloudWatch.
Havia três formas de permitir isso, e duas desfazem o trabalho da seção anterior:
dar IP público às instâncias anula a rede privada, e tornar o RDS publicamente
acessível o expõe à varredura contínua, deixando a senha como única barreira. A
terceira é um host intermediário, mínimo, com uma única porta aberta para uma
faixa de endereços conhecida, e nada além disso.

&emsp; O bastion é uma `t4g.micro`, o menor tipo disponível, na primeira
sub-rede pública. Pública porque precisa ser alcançável de fora, o que é a
definição do papel. Ele não roda aplicação, não guarda dado e não tem papel IAM
de escrita: se for comprometido, o atacante ganha o que já teria com a chave SSH,
e nada além. A única coisa instalada no boot é o cliente `postgresql16`, para
que uma investigação não dependa de baixar pacote no meio do incidente.

&emsp; A chave SSH não está no repositório e não é criada pelo Terraform. A
variável `bastion_key_name` recebe o nome de um key pair que já exista na conta,
criado no console ou por `aws ec2 create-key-pair --profile g4`, com o arquivo
`.pem` guardado fora da árvore. Quando a variável está vazia, que é o padrão, o
bastion não é criado: sem chave a instância seria inalcançável, e pagar por ela
seria desperdício. É também o que permite validar e planejar a configuração numa
conta que ainda não tem o par.

&emsp; A porta 22 aceita uma única faixa de endereços, e a validação da variável
`bastion_allowed_cidr` recusa `0.0.0.0/0`, pelo mesmo mecanismo que
`db_allowed_cidr` já usava para o banco. Um bastion aberto para a internet inteira
não reduz exposição nenhuma; apenas acrescenta um salto ao caminho do atacante. O
custo da restrição é real e está assumido: quem trocar de rede, saindo do campus
ou mudando de operadora, perde o acesso até atualizar a variável e reaplicar. É o
preço de a porta 22 não ficar visível para a varredura contínua da internet.

&emsp; A partir dele fazem-se duas coisas, e a segunda é a que aparece no vídeo:

```bash
# Salto para uma instância privada do Auto Scaling Group
ssh -J ec2-user@<ip-bastion> ec2-user@<ip-privado>

# Túnel até o RDS privado, para inspecionar com um psql local
ssh -N -L 5432:<endpoint-rds>:5432 ec2-user@<ip-bastion>
psql "postgresql://argus:<senha>@localhost:5432/argus"
```

&emsp; O AWS Systems Manager Session Manager foi avaliado e descartado, não
ignorado. Esse serviço abre a sessão pelo agente da própria AWS, o que elimina a
porta 22 aberta e a chave SSH por completo, e seria a escolha em produção: um
bastion sem porta 22 exposta é uma postura estritamente melhor. Aqui ele depende de
o papel `voclabs` conceder `ssm:StartSession` e de a instância carregar um perfil
com a política `AmazonSSMManagedInstanceCore`, duas coisas que a conta de
laboratório não garante e cuja falha só apareceria na hora da demonstração. O
bastion clássico funciona em qualquer conta. A task ECS `migration`, que era o meio
de acesso administrativo até a v3, continua existindo e segue sendo o caminho das
migrations; o bastion acrescenta a inspeção interativa, não a substitui.

**Ficha — Bastion Host**

| Campo | Conteúdo |
|---|---|
| Papel no sistema | Único ponto de entrada humano na rede privada |
| Configuração efetiva | EC2 `t4g.micro`, Amazon Linux 2023 arm64, sub-rede pública, IMDSv2 obrigatório, disco de 8 GiB criptografado |
| Entradas / saídas | Entrada: TCP 22 da faixa de endereços do time. Saída: 22 → `sg-app`, 5432 → `sg-rds`, 443 |
| Estado | Condicional: só existe com `bastion_key_name` preenchido |
| Alternativa descartada | SSM Session Manager (sem porta 22 nem chave), dependente de permissão que o `voclabs` pode recusar |
| Modo de falha previsto e mitigação | Perda da chave privada: recriar o key pair e reaplicar. Troca de rede do operador: atualizar `bastion_allowed_cidr` |
| Custo estimado | ~US$ 3/mês |
| Arquivo Terraform | `apps/basica/infra/bastion.tf` |

### 3.3 Camada de aplicação — Auto Scaling Group de EC2 e Application Load Balancer

&emsp; Este é o componente que a revisão acrescenta ao caminho síncrono. Até
aqui, a API consumida pelo dashboard era uma função Lambda com Flask empacotado
por `apig-wsgi`, exposta por um HTTP API do API Gateway. Ela escalava sozinha e
custava quase nada, argumentos bons e registrados no cabeçalho de `api_read.tf`.
O que ela não oferecia era elasticidade observável: a concorrência era
implícita, não havia política para declarar, nem grupo para inspecionar, nem
instância entrando em serviço para mostrar. A capacidade de absorver carga
existia, mas não era um objeto do sistema.

&emsp; A migração é deliberadamente parcial. O caminho assíncrono de ingestão
permanece em filas com consumidores no ECS Fargate: o desacoplamento por SQS já
absorve rajada por construção, o backlog da fila é a métrica de saúde natural
daquele fluxo, e reescrevê-lo sobre EC2 acrescentaria risco de regressão sem ganho
arquitetural. A elasticidade importa onde a latência é percebida pelo usuário, que
é no caminho de leitura.

**Launch template**

&emsp; O template é versionado, e é o versionamento que torna o rollback
possível: cada mudança gera uma versão nova, e voltar atrás é apontar o grupo
para a versão anterior e disparar um *instance refresh*. Sem ele, “rollback”
seria reconstruir a configuração à mão e torcer para não esquecer um campo.

&emsp; A AMI, que é a imagem de disco com a qual a instância nasce, é o Amazon
Linux 2023 para arm64, e vem do parâmetro público do SSM em vez de um `ami-` fixo.
O identificador muda a cada release e é diferente em cada região, então fixá-lo
significa subir uma imagem sem os patches dos últimos meses e quebrar o `apply` no
dia em que aquela AMI for desregistrada. A arquitetura arm64 não é escolha de
custo, é requisito de compatibilidade: todas as imagens deste repositório são
construídas com `--platform linux/arm64`, e uma instância x86 falharia no
`docker run` com o erro *exec format error*, sintoma que chegaria como instância
reprovando na verificação de saúde, longe da causa. Por isso o tipo é `t4g.small`,
da família Graviton, e não `t3.small`.

&emsp; O código chega na instância como imagem do ECR. O `user_data`, que é o
script executado uma vez no primeiro boot, instala Docker e o agente CloudWatch,
autentica no ECR com a credencial do instance profile, puxa a imagem marcada pelo
SHA do commit e a executa com `--restart=always`. Ele reaproveita o
`backend/Dockerfile` que já existia, com gunicorn servindo 2 processos de 4 threads
na porta 5000, e o mesmo `make push` que publica as imagens dos workers, que passou
a incluir `backend` na lista `IMAGES`. A
alternativa de baixar um tarball do S3 duplicaria um empacotamento que o
Dockerfile já resolve, e um `git clone` no boot tornaria a versão que sobe não
reproduzível, esvaziando o sentido do rollback por versão de template.

&emsp; O `user_data` roda sob `set -euo pipefail`, o que faz o script abortar no
primeiro erro em vez de seguir adiante, e isso é parte do desenho: se qualquer
etapa falhar, o container nunca sobe, a verificação de saúde nunca passa, e o ASG
substitui a instância, em vez de deixá-la em serviço servindo erro.

&emsp; O token não entra na instância; o hash dele entra. Como um ALB não tem
authorizer, a validação do token Bearer passou para dentro do Flask
(`telemetry/interfaces/auth.py`). Mas a aplicação não fala com a AWS, porque a
biblioteca `boto3` foi removida dela de propósito, decisão registrada em
`backend/AGENTS.md`. Então quem consulta o Secrets Manager é o script de boot, que
extrai o SHA-256 da audiência
`dashboard` e o injeta como variável de ambiente do container. A consequência
está assumida: rotacionar o token com `make auth-rotate` exige um
`start-instance-refresh`, porque o hash foi congelado no boot; instâncias antigas
continuam aceitando o token antigo até serem substituídas.

**Auto Scaling Group**

| Parâmetro | Valor | Justificativa |
|---|---|---|
| Tipo de instância | `t4g.small` | Graviton, casando com as imagens arm64. `small` e não `micro`: gunicorn com 2×4 threads mais o agente CloudWatch deixa 1 GiB no limite durante o `docker pull` |
| `min` / `desired` / `max` | 2 / 2 / 6 | Mínimo 2 porque com uma só a perda da instância é indisponibilidade total até a substituta subir. Teto 6 limita o estrago de uma rajada anômala contra o crédito do laboratório |
| Sub-redes | as duas privadas | Sem endereço público; entrada só pelo ALB, saída só pelo NAT |
| Tipo de health check | `ELB` | Ver abaixo; é a decisão mais consequente do grupo |
| `health_check_grace_period` | 300 s | Cobre boot + `dnf install` + `docker pull` + subida do gunicorn |
| Métrica de escalonamento | `ALBRequestCountPerTarget` | Ver abaixo |
| Valor-alvo | 60 req/instância/min | Ver abaixo |
| Health check do target group | `/health/live`, 30 s, 2 de 2 para saudável, 3 para insalubre, código 200 | Ver abaixo |
| Zonas de disponibilidade | 2 | Exigência do ALB e condição para sobreviver à perda de uma zona |

&emsp; O `health_check_type` é `ELB`, e não `EC2`. Com `EC2`, a única pergunta
que o grupo faz é “a máquina virtual está ligada?”. Uma instância cujo gunicorn
morreu, cujo container saiu, ou que nunca conseguiu puxar a imagem continua
respondendo “sim” para sempre: fica `InService`, recebe tráfego do balanceador e
erra toda requisição. Com `ELB`, a pergunta passa a ser a do target group: a
instância quebrada reprova, sai do grupo e é substituída. É a diferença entre um
grupo que funciona e um que apenas parece funcionar.

&emsp; A verificação de saúde aponta para `/health/live` e não para
`/health/ready`. As duas rotas existem: `live` responde `{"status":"ok"}` fixo, sem
tocar no banco; `ready` consulta o PostgreSQL e devolve 503 quando ele não
responde. A segunda parece a escolha mais rigorosa e é a errada aqui. Uma
indisponibilidade momentânea do RDS, por troca de instância, janela de manutenção
ou esgotamento de conexão, faria todas as instâncias reprovarem ao mesmo tempo; o
ASG as substituiria em
bloco, as substitutas encontrariam o mesmo banco indisponível e reprovariam
também, e o grupo entraria em ciclo de reciclagem sem que houvesse nada errado
com elas. O problema estaria no banco, e a reação teria derrubado também a camada
que ainda funcionava. A saúde do banco é assunto de alarme, não de health check
de target.

**Política de escalonamento**

&emsp; A política é de *target tracking*, o modo em que se declara o valor que uma
métrica deve manter e a AWS ajusta o número de instâncias sozinha para persegui-lo.
A métrica é `ALBRequestCountPerTarget` e o alvo, 60 requisições por instância por
minuto. A escolha da métrica é o que decide se a política funciona.

&emsp; Esta API passa a maior parte do tempo de cada requisição esperando o
PostgreSQL responder, e não calculando. Sob carga real a CPU da instância fica na
casa de 30 a 40% enquanto a latência percebida já dobrou. Uma política com alvo de
CPU em 70% simplesmente nunca dispararia: o grupo ficaria em duas instâncias
saturadas de conexão, com a métrica afirmando que está tudo bem.
`ALBRequestCountPerTarget` mede o que de fato cresce, que é quantas requisições
cada instância está tendo que atender, e, por vir do balanceador, é a mesma
métrica que o painel do CloudWatch mostra.

&emsp; O valor 60 vem do plano de teste, e não de estimativa:
`tests/carga/rnf02_tempo_resposta.js` sustenta cerca de 600 consultas por minuto
com 10 usuários virtuais. Contra duas instâncias são 300 por alvo, cinco vezes o
alvo, o que faz a política disparar de forma observável durante a gravação e não
no limite. Alvo baixo demais faz o grupo oscilar a cada variação; alto demais só
escala quando a latência já subiu, e aí o escalonamento chega tarde.

&emsp; O `estimated_instance_warmup` está em 300 s, igual ao período de carência.
É o tempo que a AWS espera antes de contar a instância nova na média. Sem ele, a
instância que ainda está puxando a imagem entra no cálculo com zero requisição,
derruba a média e a política conclui que já escalou o bastante, parando de crescer
no meio da rajada.

&emsp; A redução automática do grupo fica ligada, e é onde mora o risco.
Desligá-la evitaria cortar requisição em voo, mas deixaria o grupo no tamanho do
pico para sempre, o que num laboratório com crédito limitado esgota o orçamento
sozinho. O risco está coberto pelo `deregistration_delay` de 30 segundos do target
group: a instância sai do balanceador, termina o que já havia aceitado e só então
é encerrada. Trinta segundos cobrem com folga a consulta mais longa da API.

&emsp; O *step scaling* foi a alternativa descartada. Nele se declara uma tabela
de degraus, dizendo quantas instâncias somar em cada faixa da métrica; daria
controle fino sobre o tamanho de cada passo, ao custo de manter dois alarmes e a
tabela à mão. O ganho aparece com padrão de carga conhecido e irregular, que não é
o caso aqui.

**Application Load Balancer**

&emsp; O balanceador resolve três coisas que a Lambda atrás do API Gateway
resolvia de graça e que passam a ser responsabilidade nossa: um endereço estável,
já que as instâncias nascem e morrem com o IP mudando junto; a distribuição entre
as duas zonas com retirada automática da instância que reprova; e o ponto de
medição, já que `RequestCountPerTarget` e `TargetResponseTime` são métricas do
balanceador, e sem ele não há o que observar nem sobre o que escalonar.

&emsp; Ele fica nas duas sub-redes públicas. É a fronteira: a única coisa do
stack que aceita conexão da internet, e é por isso que as instâncias podem ficar
privadas. Colocá-lo na sub-rede privada é o erro que torna o sistema inalcançável
sem que nada no `plan` pareça errado. A distribuição entre zonas é sempre ativa no
ALB e não é configurável, o que a mantém uniforme mesmo com número desigual de
instâncias por zona. O `idle_timeout` fica nos 60 s padrão, e a fixação de sessão
está desligada: a API lê de views e não guarda estado entre requisições, então
prender o mesmo cliente ao mesmo alvo só reduziria a uniformidade que a política
mede.

&emsp; O listener é HTTP na porta 80, e não HTTPS na 443. Não é descuido. Servir
HTTPS no ALB exige um certificado emitido pelo ACM, e o ACM só emite para um
domínio cujo DNS possamos validar; o projeto não tem domínio próprio, e a
distribuição CloudFront, que resolveria isso com o certificado
`*.cloudfront.net`, ficou fora do escopo desta sprint. A consequência está
registrada como risco na seção 8: o token Bearer que o operador cola no dashboard
trafega em claro entre o navegador e o balanceador. É a mesma dívida que
[`arquitetura-inicial.md`](arquitetura-inicial.md) §4.8 já registrava para o
endpoint de website do S3, e a correção planejada é a mesma. Vale a coerência:
como o front também é servido por HTTP, não há conteúdo misto, que é justamente o
problema que apareceria se o CloudFront fosse posto só na frente do S3, sem a
segunda origem apontando para o ALB.

**Ficha — Application Load Balancer e target group**

| Campo | Conteúdo |
|---|---|
| Papel no sistema | Fronteira pública do caminho de leitura; distribuição, retirada de alvo insalubre e ponto de medição |
| Configuração efetiva | ALB público nas 2 sub-redes públicas; listener HTTP 80; target group HTTP 5000, `target_type = instance`, health check `/health/live` a cada 30 s, `deregistration_delay` 30 s; access logs em S3 |
| Entradas / saídas | Entrada: TCP 80 de `0.0.0.0/0`. Saída: TCP 5000 para `sg-app` |
| Estado | Implementado |
| Alternativa descartada | Manter API Gateway + Lambda, que não expõe métrica de alvo nem permite política de escalonamento declarada |
| Modo de falha previsto e mitigação | Zero alvo saudável → alarme `app-sem-alvo-saudavel`, que é o gatilho declarado de rollback (5.3) |
| Custo estimado | ~US$ 16/mês + LCU |
| Arquivo Terraform | `apps/basica/infra/alb.tf` |

**Ficha — Launch template e Auto Scaling Group**

| Campo | Conteúdo |
|---|---|
| Papel no sistema | Executa a API de leitura com elasticidade declarada e substituição automática de instância insalubre |
| Configuração efetiva | `t4g.small` arm64, AL2023 pelo SSM, IMDSv2, disco 20 GiB criptografado; ASG 2/2/6 nas sub-redes privadas, health check `ELB`, grace 300 s, `instance_refresh` rolling com `min_healthy_percentage = 50` |
| Entradas / saídas | Entrada: TCP 5000 do `sg-alb`, TCP 22 do `sg-bastion`. Saída: 443, 80, 5432 |
| Estado | Implementado |
| Alternativa descartada | (a) AWS Lambda, sem política observável; (b) ECS Fargate com autoscaling de serviço, que resolveria o mesmo sem EC2 mas não atende ao item da rubrica, que pede ASG de EC2 nominalmente |
| Modo de falha previsto e mitigação | Imagem ausente no ECR → `user_data` aborta, health check reprova, instância substituída. Grace curto demais → ciclo de reciclagem; por isso 300 s |
| Custo estimado | ~US$ 12/mês por instância; 2 a 6 instâncias |
| Arquivo Terraform | `apps/basica/infra/asg.tf`, `apps/basica/infra/templates/user_data.sh.tftpl` |

### 3.4 Persistência — Amazon RDS

&emsp; A escolha do PostgreSQL sobre o DynamoDB está justificada em
[`arquitetura-inicial.md`](arquitetura-inicial.md) §3.5 e §4.2 e em
[`plano-argus-v3.md`](plano-argus-v3.md); não se repete aqui. O que muda nesta
revisão é a posição do banco na rede e quem consegue alcançá-lo.

&emsp; A instância continua sendo uma `db.t3.medium` com 100 GiB em `gp3`,
PostgreSQL 16, `publicly_accessible = false` e `storage_encrypted = true`. O que
é novo: o `db_subnet_group` passa a apontar para as sub-redes privadas da VPC
dedicada, e não mais para as sub-redes padrão da conta, que eram todas públicas.
Antes, “privado” significava apenas que o security group não tinha regra de
entrada aberta; agora significa também que não existe rota da internet até a
sub-rede onde a instância está.

&emsp; Três origens alcançam a porta 5432, todas por referência de security group
e nenhuma por CIDR: o grupo das tasks Fargate (workers, simulador, ETL, loader,
migration), o grupo das instâncias EC2 do ASG, e o grupo do bastion. A regra do
ASG é separada da regra das tasks de propósito: se um dia a API de leitura
precisar de tratamento diferente do dos workers, há onde expressar isso sem
afrouxar a regra para os dois.

&emsp; A API entra no banco como `argus_api`, e não como o usuário mestre. Esse
usuário só herda `argus_reader`, que tem `SELECT` apenas nas views `v_*`, e toda
view filtra `available_at <= sim.now()`. É essa barreira, e não um `WHERE`
esquecido numa rota, que impede vazamento de futuro. A migração de plataforma
preservou isso: o `user_data` monta a mesma `DATABASE_URL` de menor privilégio
que a Lambda usava.

&emsp; O `multi_az` continua desligado, e isso torna o banco um ponto único de
falha. A decisão é de custo: o modo Multi-AZ, que mantém uma cópia sincronizada do
banco em outra zona, dobra o preço da instância, e o orçamento do Learner Lab não
comporta. A consequência está escrita com todas as
letras em 5.1: a perda da instância é indisponibilidade total do sistema até a
restauração a partir de backup, com RPO de até 24 horas. A variável que reverte a
decisão é `db_multi_az`, e mudá-la para `true` provisiona o standby síncrono com
failover automático de endpoint. Backup automático está em 1 dia de retenção,
`deletion_protection` só em produção e `skip_final_snapshot` fora dela: num
laboratório cuja conta deixa de existir, snapshot final é lixo com custo.

&emsp; As migrations não mudaram de mecanismo. O Terraform provisiona a instância
e para; o DDL, que são os comandos de criação e alteração de tabela, vem de
`tools/migrate.py`, aplicado pela task ECS `migration` dentro da VPC, que agora
executa na sub-rede privada, junto do banco. Separar as duas coisas é o que
permite iterar o schema sem `apply`, que
numa sessão de laboratório é a diferença entre trinta segundos e cinco minutos
por tentativa. O bastion acrescenta um segundo caminho, por túnel, para inspeção
interativa.

**Ficha — Amazon RDS PostgreSQL**

| Campo | Conteúdo |
|---|---|
| Papel no sistema | Toda a persistência: bronze, silver, gold, detect, sim, etl |
| Configuração efetiva | PostgreSQL 16, `db.t3.medium`, 100 GiB `gp3`, criptografado, subnet group privado, `publicly_accessible = false`, Multi-AZ desligado, backup 1 dia |
| Entradas / saídas | TCP 5432 dos SGs das tasks, do ASG e do bastion; `sslmode=require` |
| Estado | Implementado |
| Alternativa descartada | DynamoDB (v2), justificado em `arquitetura-inicial.md` §4.2; Multi-AZ, descartado por custo nesta sprint |
| Modo de falha previsto e mitigação | Perda da instância = indisponibilidade total, sem failover automático. Mitigação: restaurar do backup; reversão da decisão por `db_multi_az = true` |
| Custo estimado | ~US$ 60/mês |
| Arquivo Terraform | `apps/basica/infra/rds.tf` |

### 3.5 Entrega do front-end — S3 e CloudFront

&emsp; O dashboard é um site estático, gerado pelo Next.js com `output: "export"`,
sincronizado para um bucket S3 por `make frontend-deploy` e servido pelo endpoint de website
do bucket. O bucket tem os quatro bloqueios de acesso público desativados e uma
policy com `Principal: "*"` para `s3:GetObject`, porque o endpoint de website
exige leitura anônima.

&emsp; Esse endpoint atende somente em HTTP, e a consequência já estava
registrada em [`arquitetura-inicial.md`](arquitetura-inicial.md) §4.8: o token que
o operador cola na página trafega em claro, e um intermediário de rede pode lê-lo
ou alterar o JavaScript entregue. O CloudFront é a correção, porque traz TLS,
permite fechar o bucket com o Origin Access Control, que autoriza somente a
distribuição a ler o bucket, e, na topologia de duas origens, elimina o CORS e o
risco de conteúdo misto.

&emsp; O CloudFront permanece como `Planejado` nesta revisão. Ficou fora do escopo
desta sprint por decisão de recorte, e há um segundo motivo registrado no
repositório para tratá-lo com cautela: `arquitetura-inicial.md` §4.8 afirma que
operações de CDN não são permitidas pelo papel `voclabs` do Learner Lab, o que
precisa ser revalidado na conta nova antes de qualquer tentativa. O plano de
inclusão, com as duas topologias possíveis e a recomendada, está na seção 4.4;
aqui fica apenas o papel do componente e o registro de que ele ainda não existe
no Terraform.

**Ficha — S3 do front-end**

| Campo | Conteúdo |
|---|---|
| Papel no sistema | Hospeda o bundle estático do dashboard |
| Configuração efetiva | Bucket com website configuration, leitura pública, criptografia SSE-S3 |
| Entradas / saídas | HTTP do navegador; escrita por `aws s3 sync` no deploy |
| Estado | Implementado, com a limitação de atender somente em HTTP |
| Alternativa descartada | Servir o front pelo próprio ALB, o que exigiria um processo servindo arquivo estático e desperdiçaria a natureza estática do bundle |
| Modo de falha previsto e mitigação | Token em claro no transporte; mitigação planejada é o CloudFront (4.4) |
| Custo estimado | < US$ 1/mês |
| Arquivo Terraform | `apps/basica/infra/frontend_s3.tf` |

**Ficha — Amazon CloudFront**

| Campo | Conteúdo |
|---|---|
| Papel no sistema | TLS na borda, origem única para front e API, bucket privado por OAC |
| Configuração efetiva | — |
| Entradas / saídas | — |
| Estado | Planejado; sem recurso Terraform |
| Alternativa descartada | Uma origem só (apenas S3), que criaria conteúdo misto ao chamar o ALB em HTTP a partir de página HTTPS |
| Modo de falha previsto e mitigação | Papel `voclabs` pode recusar a criação; nesse caso a seção 4.4 documenta o plano com a recusa evidenciada |
| Custo estimado | ~US$ 1/mês no volume do laboratório |
| Arquivo Terraform | — (planejado: `cloudfront.tf`) |

### 3.6 Pipeline assíncrono e demais serviços

&emsp; O fluxo de ingestão não mudou de desenho e está descrito em
[`arquitetura-inicial.md`](arquitetura-inicial.md) §3; não se repete aqui. O que
mudou é onde ele executa: as tasks Fargate deixam de receber endereço público e
passam a rodar nas sub-redes privadas, com saída pelo NAT Gateway. Isso muda a
rota de saída e acrescenta custo de tráfego de NAT ao que antes saía direto pelo
Internet Gateway, que é a contrapartida de as cargas deixarem de ser endereçáveis
da internet.

&emsp; Em resumo, e com ponteiro para o detalhe: o API Gateway HTTP recebe
`POST /v1/events` e `POST /v1/changes` com integração direta ao SQS, sem compute
no caminho; o SQS tem duas filas com DLQ e reencaminhamento após 5 tentativas;
**ECS Fargate** roda os dois workers de ingestão, o simulador do relógio virtual e
o container de processamento, mais as tasks avulsas `loader` e `migration`;
**ECR** guarda as imagens marcadas pelo SHA do commit, e passou a incluir o
repositório `backend`, que antes não existia porque a API era um zip de Lambda;
**Secrets Manager** guarda o SHA-256 dos dois tokens e a senha do banco;
**Lambda authorizer** continua protegendo a API de ingestão e a API de leitura
mantida no API Gateway. Apenas o novo caminho ALB/ASG deixa de depender dele, porque
a validação do Bearer ocorre dentro do Flask (3.3).

### 3.7 Matriz de conexões

&emsp; Uma linha por seta do diagrama da seção 2. Seta sem linha aqui é seta não
justificada; linha sem seta é componente esquecido no desenho.

| Origem | Destino | Protocolo / porta | Autenticação | Rede |
|---|---|---|---|---|
| Aplicações cliente | API Gateway «events» | HTTPS 443 | Bearer, audiência `ingest` | internet → borda |
| API Gateway «events» | SQS `events` / `changes` | AWS SDK, integração direta | IAM (role do gateway) | serviço gerenciado |
| ECS `event_worker` / `merge_worker` | SQS | HTTPS 443, long polling | IAM (task role) | privada → NAT |
| ECS `loader` | S3 «origem» | HTTPS 443, `GetObject` | IAM (task role) | privada → NAT |
| ECS (workers, simulador, ETL) | RDS | PostgreSQL 5432, `sslmode=require` | usuário mestre | privada |
| ECS `migration` | RDS | PostgreSQL 5432 | usuário mestre | privada |
| Navegador do usuário | S3 «frontend» | HTTP 80 | anônimo (bundle público) | internet |
| Navegador do usuário | API Gateway «read» | HTTPS 443 | CORS + Bearer, audiência `dashboard` | internet → serviço gerenciado |
| API Gateway «read» | Lambda authorizer | integração AWS | IAM do serviço; validação do Bearer | serviço gerenciado |
| API Gateway «read» | Lambda de leitura | integração AWS | contexto autorizado | serviço gerenciado |
| Lambda de leitura | RDS | PostgreSQL 5432, `sslmode=require` | usuário `argus_api` | serviço gerenciado → privada |
| Lambda de leitura | CloudWatch Logs | HTTPS 443 | IAM da função | serviço gerenciado |
| Navegador do usuário | Application Load Balancer | HTTP 80 | Bearer, audiência `dashboard` | internet → pública |
| ALB | EC2 do ASG | HTTP 5000 | — (rede: só o `sg-alb` alcança) | pública → privada |
| ALB | Target group (health check) | HTTP 5000 `/health/live` | nenhuma, por desenho | pública → privada |
| EC2 do ASG | RDS | PostgreSQL 5432, `sslmode=require` | usuário `argus_api` (só views `v_*`) | privada |
| EC2 do ASG (boot) | ECR | HTTPS 443 | IAM (instance profile) | privada → NAT |
| EC2 do ASG (boot) | Secrets Manager | HTTPS 443 | IAM (instance profile) | privada → NAT |
| EC2 do ASG | CloudWatch Logs | HTTPS 443 | IAM (instance profile) | privada → NAT |
| Estação do administrador | Bastion | SSH 22 | chave SSH, CIDR restrito | internet → pública |
| Bastion | EC2 do ASG | SSH 22 | chave SSH | pública → privada |
| Bastion | RDS | PostgreSQL 5432 (túnel) | usuário do banco | pública → privada |
| Sub-redes privadas | NAT Gateway | rota `0.0.0.0/0` | — | privada → pública |
| NAT Gateway / ALB / Bastion | Internet Gateway | rota `0.0.0.0/0` | — | pública → internet |
| VPC | S3 (Flow Logs) | serviço gerenciado | policy do bucket, com `aws:SourceAccount` e `aws:SourceArn` | — |
| ALB | S3 (access logs) | serviço gerenciado | policy do bucket | — |
| CloudWatch (alarmes) | SNS | serviço gerenciado | IAM | — |

### 3.8 Tabela de decisões arquiteturais

| # | Decisão | Alternativa descartada | Atributo de qualidade | Falha prevista e mitigação | Custo | Rollback |
|---|---|---|---|---|---|---|
| 1 | EC2 em ASG no caminho síncrono, Fargate mantido no assíncrono | Migrar tudo para EC2, ou manter tudo em Lambda/Fargate | Elasticidade observável, sem regressão no fluxo que já funciona | Duas plataformas para operar; mitigado por observabilidade comum no CloudWatch | ~US$ 24/mês em 2 instâncias | Repontar o front ao HTTP API da Lambda, que segue provisionado |
| 2 | NAT Gateway em vez de IP público nas cargas | `assign_public_ip = true` (v3) | Segurança: saída sem entrada | Custo é o mais alto da topologia | ~US$ 32/mês + tráfego | `create_network = false` |
| 3 | Um NAT em vez de um por AZ | Um NAT por zona (recomendação AWS) | Custo sobre disponibilidade | Queda da AZ do NAT deixa a outra zona sem saída | Metade do custo de NAT | Acrescentar o segundo NAT e a tabela de rotas por zona |
| 4 | Sem VPC endpoints | Endpoints para S3, ECR, Secrets Manager, Logs | Simplicidade sobre custo de tráfego | Todo `docker pull` paga NAT | Economia não realizada | Acrescentar os endpoints sem mudar a aplicação |
| 5 | Bastion clássico com porta 22 restrita | SSM Session Manager, sem porta nem chave | Portabilidade entre contas do laboratório | Chave perdida ou CIDR mudado bloqueia acesso | ~US$ 3/mês | Trocar por Session Manager se o `voclabs` permitir |
| 6 | Health check `ELB` sobre `/health/live` | `EC2`, ou `ELB` sobre `/health/ready` | Disponibilidade: evita reciclagem em massa por falha do banco | Processo travado sem morrer não é detectado; mitigado pelo alarme de latência | — | Trocar o `path` do target group |
| 7 | Target tracking por `ALBRequestCountPerTarget` | CPU média, ou step scaling | Elasticidade efetiva numa carga limitada por I/O | Rajada muito curta pode terminar antes de a instância entrar em serviço | — | Trocar `predefined_metric_type` |
| 8 | RDS sem Multi-AZ | Multi-AZ com standby síncrono | Custo sobre disponibilidade | **Ponto único de falha**: perda da instância é indisponibilidade total | Metade do custo de RDS | `db_multi_az = true` |
| 9 | ALB em HTTP, sem TLS | Listener 443 com certificado ACM | Escopo: depende do CloudFront, fora desta sprint | Token Bearer em claro no transporte | — | Acrescentar o CloudFront (4.4) e o listener 443 |
| 10 | Validação do Bearer dentro do Flask | Manter o Lambda authorizer | Necessidade: o ALB não tem authorizer | Rotação de token exige `instance_refresh` | — | Voltar ao API Gateway, que segue provisionado |
| 11 | Imagem do ECR na EC2, via `user_data` | Tarball no S3, ou `git clone` no boot | Reprodutibilidade: dá sentido ao rollback por versão de template | Imagem ausente aborta o boot; mitigado pelo health check | — | Trocar o `user_data` do template |
| 12 | Instâncias Graviton (`t4g`, arm64) | Família x86 (`t3`) | Compatibilidade com as imagens arm64 do repositório | Trocar de família sem trocar a AMI causa *exec format error* | ~10% mais barato | Trocar tipo, AMI e `--platform` juntos |

---

## 4. Plano de deploy na AWS

&emsp; O plano abaixo permite reproduzir o ambiente numa conta nova do Learner Lab.
Os comandos operacionais permanecem centralizados no `Makefile`, e os detalhes de
manutenção estão em [`apps/basica/infra/README.md`](../apps/basica/infra/README.md).
Cada etapa é ordenada pela dependência que satisfaz, para evitar instâncias iniciadas
sem imagem, banco sem schema ou front-end apontando para endpoint ainda inexistente.

### 4.1 Pré-requisitos

&emsp; A implantação da arquitetura v4 parte de uma conta nova do AWS Academy Learner
Lab, criada para a Sprint 3. O computador usado no deploy precisa das ferramentas
abaixo. Os comandos do `Makefile` devem ser executados no Git Bash ou WSL, pois usam
recursos de shell POSIX; os comandos de preparação desta subseção podem ser executados
no PowerShell.

| Ferramenta | Versão mínima ou requisito | Uso no projeto |
|---|---|---|
| Git | Versão estável atual | Clonar o repositório e identificar o SHA usado nas imagens |
| AWS CLI | 2.x | Autenticar no Learner Lab e consultar ou operar os recursos AWS |
| Terraform | 1.11 ou superior | Inicializar, validar, planejar, aplicar e executar os testes com `override_during = plan` |
| Docker Desktop | Buildx habilitado e suporte a `linux/arm64` | Construir as imagens dos serviços para o Amazon ECR |
| Python | 3.12 ou superior | Executar migrations, carga, testes e ferramentas do projeto |
| uv | Versão estável atual | Criar os ambientes Python a partir dos arquivos `pyproject.toml` |
| Node.js e npm | Node.js 20 ou superior | Instalar, testar e gerar o export estático do dashboard |
| GNU Make e Bash | Disponíveis no Git Bash ou WSL | Executar os alvos de instalação, build, deploy e verificação |

&emsp; Antes de configurar credenciais, as versões instaladas devem ser conferidas. A
execução pode continuar quando todos os comandos abaixo responderem sem erro e o
Terraform indicar uma versão igual ou superior a 1.11. Essa versão é necessária
porque os testes mockados usam `override_during = plan`, recurso introduzido no
Terraform 1.11.

```powershell
git --version
aws --version
terraform version
docker version
docker buildx version
python --version
uv --version
node --version
npm --version
make --version
```

#### 4.1.1 Credenciais e validação da conta

&emsp; As credenciais temporárias devem ser copiadas de **AWS Details → AWS CLI** no
Learner Lab e armazenadas somente no profile local `g4`. O access key, o secret key e
o session token não entram no repositório, no `.env` nem no `terraform.tfvars`. Como
as credenciais expiram, a validação é repetida antes de cada `plan` e `apply`.

```powershell
$env:AWS_PROFILE = "g4"
$env:AWS_REGION = "us-east-1"

$taskAccountId = aws sts get-caller-identity `
  --profile g4 `
  --query Account `
  --output text

if ($LASTEXITCODE -ne 0 -or $taskAccountId -notmatch '^\d{12}$') {
  throw "Não foi possível confirmar a conta ativa do Learner Lab."
}

aws ec2 describe-vpcs `
  --profile g4 `
  --region us-east-1 `
  --max-results 5 `
  --query 'Vpcs[].{VpcId:VpcId,Cidr:CidrBlock}' `
  --output table

if ($LASTEXITCODE -ne 0) {
  throw "A sessão existe, mas não possui uma credencial válida para operar a EC2."
}
```

&emsp; A segunda chamada é necessária porque testa uma permissão usada pelo deploy,
em vez de verificar apenas a identidade. O valor de `$taskAccountId` deve corresponder
à conta nova da Sprint 3. O ARN a informar em `existing_role_arn` pode ser conferido
sem digitação manual:

```powershell
$taskRoleArn = "arn:aws:iam::${taskAccountId}:role/LabRole"
$taskRoleArn
```

&emsp; Se a conta não for a esperada, nenhum comando Terraform deve ser executado.

#### 4.1.2 Isolamento do state anterior

&emsp; O `terraform.tfstate` existente descreve a conta anterior e não pode ser usado
na conta nova. Reutilizá-lo faria o Terraform procurar recursos que não existem na
sessão atual. Como a conta nova começou vazia, não há recurso da versão anterior a ser
preservado nela; o RDS e os demais componentes da v4 podem nascer diretamente na nova
VPC. O state, o backup e o `terraform.tfvars` anteriores devem ser movidos para um
diretório protegido fora do repositório antes da inicialização.

```powershell
Set-Location apps/basica/infra

$taskStamp = Get-Date -Format "yyyyMMdd-HHmmss"
$taskStateArchive = Join-Path $env:USERPROFILE "argus-state-archive\$taskStamp"
New-Item -ItemType Directory -Path $taskStateArchive -Force | Out-Null

foreach ($taskLocalFile in @("terraform.tfstate", "terraform.tfstate.backup", "terraform.tfvars")) {
  if (Test-Path -LiteralPath $taskLocalFile) {
    Move-Item -LiteralPath $taskLocalFile -Destination $taskStateArchive
  }
}

Copy-Item -LiteralPath "terraform.tfvars.example" -Destination "terraform.tfvars"
```

&emsp; O diretório de arquivo contém state e valores sensíveis e, portanto, não deve
ser sincronizado com o Git. Quando as permissões da conta permitirem criar o bucket e
o mecanismo de lock, [`backend.tf.example`](../apps/basica/infra/backend.tf.example)
deve ser usado como base para um backend remoto criptografado. Se o laboratório negar
esses recursos, o state permanece local sob responsabilidade de um único operador por
janela de implantação.

#### 4.1.3 Configuração do ambiente

&emsp; O novo `terraform.tfvars` deve ser preenchido com valores exclusivos da conta
atual. Nenhuma senha, token ou identificação real deve ser copiada para arquivos
versionados.

| Campo | Configuração para a primeira aplicação | Motivo |
|---|---|---|
| `region` | `"us-east-1"` | Região adotada pelo diagrama e pelos recursos do projeto |
| `create_iam_roles` | `false` | O Learner Lab normalmente bloqueia `iam:CreateRole` |
| `existing_role_arn` | ARN da `LabRole` formado com o account ID confirmado | Impede referência à role da conta anterior |
| `db_password_from_secrets_manager` | Conforme as permissões da conta; `false` quando o Secrets Manager for negado | Mantém um caminho compatível com o laboratório |
| `db_password`, `read_api_db_password` e `user_id_hash_salt` | Valores novos, longos e distintos | Evita reutilização de segredos da conta anterior |
| `db_publicly_accessible` | `false` | O RDS deve permanecer nas sub-redes privadas |
| `db_allowed_cidr` | `""` | Remove acesso direto ao PostgreSQL pela internet |
| `assign_public_ip` | `false` | As cargas privadas obtêm saída pelo NAT Gateway |
| `worker_desired_count` | `0` | Evita iniciar workers antes de as imagens existirem no ECR |
| `processing_desired_count` | `0` | Evita iniciar processamento antes da carga e das imagens |
| `simulator_desired_count` | `0` | O relógio virtual só é ligado depois da carga inicial |
| `db_multi_az` | `false` no laboratório ou `true` quando o orçamento permitir | A decisão de custo e disponibilidade deve permanecer explícita |

&emsp; Antes do `terraform init`, os valores de exemplo devem ser eliminados e a
classe escolhida para o RDS precisa estar disponível na região.

```powershell
$taskExampleValues = Select-String `
  -LiteralPath "terraform.tfvars" `
  -Pattern "000000000000|troque-|203\.0\.113\.10"

if ($taskExampleValues) {
  throw "O terraform.tfvars ainda contém valores de exemplo."
}

aws rds describe-orderable-db-instance-options `
  --profile g4 `
  --region us-east-1 `
  --engine postgres `
  --engine-version 16 `
  --db-instance-class db.t3.medium `
  --query 'OrderableDBInstanceOptions[].DBInstanceClass' `
  --output text

terraform init -reconfigure
terraform fmt -check -recursive
terraform validate
```

&emsp; A consulta do RDS deve retornar `db.t3.medium`; se retornar vazio, a classe
precisa ser trocada por outra oferecida pelo laboratório e a limitação deve ser
registrada. A preparação termina quando `terraform validate` responde
`Success! The configuration is valid.`. O `plan` e os dois `apply` ficam para a ordem
de implantação da seção 4.3.

#### 4.1.4 Dados necessários para a carga

&emsp; O dump bruto do parceiro não é versionado. Antes do deploy, a equipe deve
confirmar a disponibilidade autorizada de `argus_dump.sql` ou dos Parquet já gerados.
Sem nenhum dos dois, é possível validar a integração com fixtures, mas não reproduzir
a carga das 33 tabelas nem os testes sobre 68,7 milhões de linhas.

```powershell
Set-Location ../../..

Test-Path -LiteralPath "argus_dump.sql"
Test-Path -LiteralPath "data/parquet/_manifest.json"
```

&emsp; Pelo menos uma das duas verificações deve retornar `True`. Se apenas o dump
estiver disponível, `make -C apps/basica parquet` gera os Parquet antes da
sincronização com o bucket de origem.

### 4.2 Recursos provisionados

&emsp; Os arquivos abaixo são todos de `apps/basica/infra/`. A convenção do
diretório é um arquivo por recurso, sem módulos. Os quatro primeiros são novos
nesta revisão.

| Recurso AWS | Finalidade | Arquivo Terraform |
|---|---|---|
| VPC, 4 sub-redes, IGW, NAT, tabelas de rota, gateway endpoint de S3 | Isolamento de rede; saída sem entrada para as cargas privadas. O endpoint é gratuito e tira o tráfego do `loader` de cima do NAT | `vpc.tf` |
| VPC Flow Logs e seu bucket, bucket de access logs do ALB | Logs distribuídos da camada de rede (item V1-a). Destino em S3 pela restrição da `LabRole` (§8.1) | `vpc_logs.tf` |
| Bastion Host + security group | Único ponto de entrada humano na rede privada (V1-b) | `bastion.tf` |
| ALB, target group, listener, security group | Fronteira pública e ponto de medição do caminho de leitura (V1-c) | `alb.tf` |
| Launch template, ASG, política de escalonamento, SG | Execução elástica da API de leitura (V1-c) | `asg.tf` + `templates/user_data.sh.tftpl` |
| Alarmes do ALB/ASG e painel do CloudWatch | Observabilidade do caminho síncrono | `asg_observability.tf` |
| RDS PostgreSQL 16 + subnet group privado | Toda a persistência (V1-d) | `rds.tf` |
| ECR (5 repositórios, incluindo `backend`) | Imagens marcadas pelo SHA do commit | `ecr.tf` |
| ECS Fargate: cluster, 4 serviços, 2 tasks avulsas | Ingestão, simulador, ETL, carga inicial, migrations | `ecs.tf`, `ecs_*.tf` |
| API Gateway HTTP + SQS (2 filas + 2 DLQs) | Caminho assíncrono de ingestão | `apigateway*.tf`, `sqs*.tf` |
| Lambda de leitura + HTTP API | Caminho de leitura anterior, mantido durante a transição | `api_read.tf` |
| Lambda authorizer + Secrets Manager | Bearer da ingestão; hashes dos tokens e senha do banco | `auth.tf` |
| S3 do dashboard e S3 de origem | Bundle estático e Parquet da carga inicial | `frontend_s3.tf`, `s3_origem.tf` |
| SNS + 23 alarmes do CloudWatch | Notificação de falha | `observability.tf`, `asg_observability.tf` |
| Papéis e políticas IAM | Condicionais: colapsam na `LabRole` no Learner Lab | `iam.tf` |
| CloudFront + certificado ACM | **Planejado** — sem recurso; plano em 4.4 | — |

&emsp; A Lambda de leitura não foi removida. Ela e o HTTP API que a expõe
continuam provisionados de propósito: derrubar o caminho antigo no mesmo `apply`
que sobe o novo deixaria o dashboard sem API caso o Auto Scaling Group não suba.
Os dois coexistem durante a transição, e o desligamento é um passo manual e
posterior, que é remover os recursos de `api_read.tf` e as rotas correspondentes
de `auth.tf`, feito só depois de o ALB responder e o front já apontar para ele.

### 4.3 Ordem de implantação

&emsp; A primeira execução numa conta vazia ocorre em duas fases. Primeiro são
criados os repositórios ECR, porque `make push` precisa dos seus endereços. Depois
das imagens por SHA serem publicadas, o plano completo pode criar rede, grupos de
segurança, RDS, ALB, launch template, ASG e os serviços restantes sem provocar
`ImagePullBackOff`. O Terraform resolve as dependências internas: sub-redes antes
do subnet group e do ASG, security groups antes das interfaces e target group antes
do vínculo com o grupo de escalonamento.

```bash
export AWS_PROFILE=g4 AWS_REGION=us-east-1
aws sts get-caller-identity --profile g4 --query Account --output text

make -C apps/basica check
make -C apps/basica lambda-build

# Bootstrap exclusivo de uma conta cujo ECR ainda não existe.
terraform -chdir=apps/basica/infra apply \
  -target='aws_ecr_repository.images' \
  -target='aws_ecr_lifecycle_policy.images'

make -C apps/basica push
make -C apps/basica tf-plan
make -C apps/basica tf-apply

make -C apps/basica auth-rotate
make -C apps/basica migrate-status-aws
make -C apps/basica migrate-aws
make -C apps/basica db-reader-aws
make -C apps/basica origem-sync
make -C apps/basica load
make -C apps/basica frontend-deploy
make -C apps/basica smoke
```

&emsp; O primeiro `apply` completo inicia o RDS cedo porque ele é o recurso mais
demorado. A rotação dos tokens vem imediatamente depois: até ela ocorrer, a API
falha fechada com 403, como projetado. As migrations e o usuário de leitura são
criados antes da validação funcional. A carga inicial é opcional quando o objetivo
for somente provar integração com fixtures; para reproduzir as 33 tabelas ela é
obrigatória. O front-end é publicado por último para receber os endpoints do estado
já aplicado. No PowerShell, argumentos Terraform no formato `-var=valor` devem ficar
entre aspas; os pacotes Lambda são gerados pelo alvo `lambda-build`, que preserva o
layout esperado pelo runtime.

### 4.4 Inclusão do AWS CloudFront

&emsp; O CloudFront é a evolução planejada para retirar o dashboard do endpoint de
website S3, que oferece apenas HTTP. O objetivo principal é proteger o bundle e o
token de leitura com TLS; redução de latência é um benefício secundário. A opção de
uma única origem S3 foi descartada porque uma página HTTPS continuaria chamando o
ALB em HTTP, e o navegador bloquearia a requisição como conteúdo misto.

&emsp; A topologia escolhida possui duas origens. O comportamento padrão usa o S3
como origem REST, protegido por Origin Access Control; assim, o bloqueio de acesso
público pode ser reativado e somente a distribuição lê os objetos. O comportamento
`/api/*` encaminha para o ALB, desabilita cache e preserva `Authorization`, método,
query string e cabeçalhos necessários. Com front e API sob o mesmo domínio, deixa de
existir CORS entre eles. `viewer_protocol_policy = redirect-to-https` força TLS. O
domínio padrão `*.cloudfront.net` funciona sem configuração adicional; se houver
domínio próprio, o certificado do ACM precisa estar em `us-east-1`, exigência do
CloudFront.

&emsp; A distribuição não foi criada nesta sprint. Além do tempo de propagação e do
custo adicional, o papel `voclabs` pode negar CloudFront, OAC ou a alteração da policy
do bucket. Quando a conta permitir, a implementação entra em `cloudfront.tf`, expõe
`cloudfront_distribution_id` e `frontend_https_url`, troca o front para a URL HTTPS e
executa os testes de autorização antes de retirar o caminho atual. Uma recusa do
laboratório deve ser preservada como evidência da limitação, sem apresentar o site
HTTP como equivalente à solução planejada.

| Comportamento | Caminho | Origem | Cache | Cabeçalhos encaminhados |
|---|---|---|---|---|
| Padrão | `/*` | S3 REST via OAC | Longo para assets com hash; invalidação a cada publicação | Apenas os necessários à origem S3 |
| API | `/api/*` | ALB | Desabilitado | `Authorization`, `Accept`, `Content-Type`, query strings e método HTTP |

```bash
# Executar após a futura criação da distribuição e a publicação do front.
DISTRIBUTION_ID="$(terraform -chdir=apps/basica/infra output -raw cloudfront_distribution_id)"
aws cloudfront create-invalidation --distribution-id "$DISTRIBUTION_ID" --paths "/*"
```

### 4.5 Verificação pós-implantação

&emsp; O aceite abaixo foi repetido em 10 de setembro de 2026. Os comandos usam
saídas do Terraform e evitam copiar identificadores efêmeros para o documento.

| # | Verificação | Comando | Resultado esperado |
|---|---|---|---|
| 1 | Instâncias saudáveis no target group | `aws elbv2 describe-target-health --target-group-arn "$(terraform -chdir=apps/basica/infra output -raw target_group_arn)" --query 'TargetHealthDescriptions[].TargetHealth.State'` | **Verificado:** dois de dois targets em `healthy` |
| 2 | ALB responde | `curl -fsS "$(terraform -chdir=apps/basica/infra output -raw api_url_alb)/health/live"` | **Verificado:** HTTP 200 |
| 3 | Rotas: uma tabela para o IGW, outra para o NAT | `VPC="$(terraform -chdir=apps/basica/infra output -raw vpc_id)"; aws ec2 describe-route-tables --filters Name=vpc-id,Values="$VPC" --query 'RouteTables[].Routes[].{Destino:DestinationCidrBlock,IGW:GatewayId,NAT:NatGatewayId}'` | **Verificado.** Pública `0.0.0.0/0 → igw-…`; privada `0.0.0.0/0 → nat-…` |
| 4 | Instância privada sem IP público, mas com saída | Instância descartável na sub-rede privada; `user_data` grava o IP de saída como tag em si mesma (ver 4.6) | **Verificado.** `PublicIpAddress: null`, e a internet enxerga a saída com o Elastic IP do NAT — o endereço público fixo associado a ele |
| 5 | RDS privado e alcançável somente pelos componentes autorizados | `aws rds describe-db-instances --query 'DBInstances[].{Status:DBInstanceStatus,Publico:PubliclyAccessible,MultiAZ:MultiAZ}'` e inspeção das origens do SG na porta 5432 | **Verificado:** `available`, `Publico: false`; entrada limitada aos SGs da aplicação, das tasks e do bastion |
| 6 | Front publicado e estado do CloudFront | `curl -I "$(terraform -chdir=apps/basica/infra output -raw frontend_url)"` e consulta aos outputs | **Verificado:** website S3 em HTTP 200; CloudFront não implantado e corretamente marcado como planejado |
| 7 | Flow logs capturando fluxo real | `aws s3 ls --recursive "$(terraform -chdir=apps/basica/infra output -raw flow_log_destino)/"` | **Verificado.** 214 fluxos da instância de teste, com `ACCEPT` e `REJECT` |
| 8 | Logs de aplicação chegando ao CloudWatch | `aws logs describe-log-streams --log-group-name "$(terraform -chdir=apps/basica/infra output -raw app_log_group_name)" --order-by LastEventTime --descending --max-items 5` | **Verificado:** cinco streams recentes retornados na conferência final |

### 4.6 Evidências da rede aplicada

&emsp; A camada de rede foi provisionada e verificada em 8 de setembro de 2026, numa
conta do AWS Academy Learner Lab, região `us-east-1`, em workspace próprio do Terraform
(`individual`) para não tocar o estado do ambiente principal. Foram 21 recursos: 16 na
aplicação da rede e 5 na dos Flow Logs.

> **Procedência.** A configuração aplicada é a desta camada de rede, desenvolvida e
> exercitada na branch `feat/vpc-nat` e depois consolidada aqui. A topologia, o destino
> dos Flow Logs e o gateway endpoint de S3 são os mesmos que este repositório versiona
> hoje; a diferença é de nomenclatura de variável (`create_vpc` passou a
> `create_network`) e o acréscimo da validação cruzada descrita em 3.1.

| Cláusula | Evidência capturada |
|---|---|
| VPC gerenciada | `vpc-0fba74730439e3caf`, CIDR `10.0.0.0/16`, DNS support e hostnames habilitados |
| Sub-redes | Quatro, duas por AZ. `10.0.0.0/24` e `10.0.1.0/24` com *auto-assign public IP*; `10.0.10.0/24` e `10.0.11.0/24` sem |
| Rota pública | `0.0.0.0/0 → igw-0392604b075205f5a` |
| Rota privada | `0.0.0.0/0 → nat-0fb2306effb9b2662` |
| NAT em operação | Elastic IP `52.4.149.88`. Ver o teste abaixo |
| Gateway endpoint S3 | `vpce-0ae7582c8f2415388`, associado à tabela de rota privada |
| Logs distribuídos | `fl-0894f5598c97e2016`, entregando no S3. 214 fluxos capturados só da instância de teste |
| Criptografia do destino | `AES256` no bucket dos Flow Logs |

#### O teste do NAT

&emsp; Provar que o NAT funciona exige mais do que ver o recurso `available` no console:
é preciso mostrar tráfego atravessando. O teste usado foi uma instância `t3.micro`
descartável na sub-rede privada `10.0.11.0/24`, sem IP público, cujo `user_data`
consulta o próprio endereço de saída e o grava como tag em si mesma:

> **Esta instância não faz parte da arquitetura.** Ela é instrumento de medição, não
> componente: foi criada por `aws ec2 run-instances` na linha de comando, fora do
> Terraform. Não existe `aws_instance` de teste em nenhum arquivo `.tf` do projeto, e
> ela nunca entrou no estado. Foi encerrada depois da captura. A rede funciona sem
> ela; a instância só torna o funcionamento visível.

```bash
IP=$(curl -s https://checkip.amazonaws.com)
aws ec2 create-tags --resources $ID --tags Key=IPDeSaida,Value=$IP
```

&emsp; Resultado:

| Atributo | Valor |
|---|---|
| `PublicIpAddress` | `null` |
| `PrivateIpAddress` | `10.0.11.120` |
| Tag `IPDeSaida` | `52.4.149.88`, que é o Elastic IP do NAT Gateway |

&emsp; Uma máquina sem endereço público, cuja saída a internet enxerga com o IP do NAT,
só pode estar atravessando o NAT. É a demonstração direta da cláusula, e não depende de
nenhuma tela de console.

#### O que os Flow Logs mostram

&emsp; Os registros capturados são majoritariamente sondagens da internet contra a
interface pública do NAT Gateway (`10.0.0.110`):

```
162.216.149.183 -> 10.0.0.110 :36884   ACCEPT
116.90.227.175  -> 10.0.0.110 :1433    ACCEPT   <- varredura de SQL Server
91.230.168.92   -> 10.0.0.110 :1992    ACCEPT
```

&emsp; Isso é evidência de dois fatos ao mesmo tempo: a observabilidade de rede está
capturando fluxo real, e o único endereço público da VPC é sondado continuamente por
terceiros, sem que nada disso alcance as sub-redes privadas, que não têm rota de
entrada.

&emsp; A travessia do NAT também aparece nos registros. Foram 214 fluxos envolvendo a
instância de teste, e todos os que saem dela passam pela interface do NAT Gateway
(`10.0.0.110`), nenhum diretamente para a internet:

```
10.0.11.120 -> 10.0.0.110  :123    ACCEPT     <- NTP saindo pelo NAT
10.0.0.110  -> 10.0.11.120 :43766  ACCEPT     <- retorno, 15 pacotes
10.0.11.120 -> 10.0.0.110  :123    ACCEPT
10.0.0.110  -> 10.0.11.120 :52231  ACCEPT
```

&emsp; Ler esses quatro registros junto com a tabela de rota privada fecha o argumento
da cláusula: a máquina privada não tem caminho para a internet que não seja o NAT, e o
log prova que ela usou esse caminho.

&emsp; Um detalhe operacional para a gravação: a entrega no S3 tem latência própria de
cerca de cinco minutos, independente do `max_aggregation_interval` de 60 segundos. O
primeiro arquivo não aparece imediatamente depois de gerar tráfego.

---

## 5. Alta disponibilidade, escalonamento e rollback

### 5.1 Alta disponibilidade

&emsp; O que sobrevive e o que não sobrevive, item a item. A tabela é honesta
sobre o segundo caso: há um ponto único de falha declarado nesta topologia, e
ele é o banco.

| Falha | Efeito | Recuperação | Automática? |
|---|---|---|---|
| Uma instância do ASG | Capacidade cai pela metade; o ALB para de enviar tráfego para ela em até 90 s (3 checks de 30 s) | O ASG substitui a instância para voltar ao `desired`; ~5 min até entrar em serviço | Sim |
| Uma zona de disponibilidade | As instâncias da zona somem; o ALB concentra o tráfego no nó da outra zona | O ASG sobe as substitutas na zona sobrevivente. **Se for a zona do NAT**, a outra zona fica sem saída e não consegue subir instância nova até a zona voltar | Parcial |
| Instância do RDS | Indisponibilidade total do sistema; sem standby, não há para onde falhar | Restauração a partir do backup automático, com RPO de até 24 h e RTO de dezenas de minutos | Não |
| NAT Gateway | O tráfego já em curso não é afetado — o caminho de leitura não passa pelo NAT. As instâncias perdem saída: não puxam imagem, não leem segredo, não entregam log | O NAT é gerenciado e redundante *dentro* da sua AZ; a perda real é a perda da AZ inteira | Sim, dentro da AZ |
| Application Load Balancer | O ALB tem nós em duas AZs e é gerenciado; a perda de um nó é absorvida pelo DNS do serviço | — | Sim |
| Bastion | Nenhum efeito sobre o sistema: ele não está no caminho de nenhuma requisição | Recriar com `terraform apply` | Não, e não precisa ser |

&emsp; O RDS é o ponto único de falha, e a decisão é consciente. O `db_multi_az`
está em `false` porque o Multi-AZ dobra o custo da instância, de cerca de US$ 60
para US$ 120 por mês, e o crédito do Learner Lab não comporta.
A variável que reverte a decisão é exatamente essa: `db_multi_az = true`
provisiona o standby síncrono em outra zona, com failover automático de endpoint
em um a dois minutos e sem mudança na aplicação, porque o nome DNS do endpoint
não muda. É uma linha de `terraform.tfvars` e uma janela de conversão de dezenas
de minutos.

&emsp; O NAT único é o segundo compromisso. Um NAT por zona é a recomendação da
AWS e custaria mais US$ 32/mês. Vale notar o que a decisão não compromete: como o
tráfego de leitura entra pelo ALB e vai direto às instâncias, a perda da zona do
NAT não derruba o serviço; ela impede o grupo de crescer e de substituir instância
naquela zona. O impacto é sobre a capacidade de recuperação,
não sobre a disponibilidade imediata.

### 5.2 Política de escalonamento

&emsp; A política é *target tracking* sobre `ALBRequestCountPerTarget`, com alvo
de 60 requisições por instância por minuto, `min` 2 e `max` 6. O raciocínio por
trás da métrica e do número está em 3.3 e não se repete; o que interessa aqui é o
comportamento nas duas direções.

&emsp; Crescimento do grupo. O CloudWatch avalia a métrica a cada minuto.
Cruzado o alvo, a política calcula quantas instâncias faltam para trazer a média de
volta a 60 e ajusta o `desired` de uma vez, e não de uma em uma. A instância nova
leva cerca de cinco minutos até entrar em serviço: boot do Amazon Linux,
`dnf install` de Docker e do agente CloudWatch, `docker pull` da imagem e subida do
gunicorn. Durante esse período ela fica fora do cálculo da média por causa do
`estimated_instance_warmup` de 300 s. Sem isso, uma instância ainda inicializando
entraria na conta com zero requisição, derrubaria a média e faria a política
concluir que já escalou o bastante, parando de crescer no meio da rajada.

&emsp; A redução do grupo é onde mora o risco, e ele está tratado em três camadas.
Quando a média cai de forma sustentada, a política reduz o `desired` e o ASG
escolhe uma instância para encerrar. Antes de encerrá-la:

1. O ALB a coloca em `draining` e para de enviar requisições novas para ela.
2. O `deregistration_delay` do target group segura o encerramento por 30 segundos,
   tempo em que as requisições já aceitas terminam de ser servidas. Trinta
   segundos cobrem com folga a consulta mais longa desta API; se houvesse
   processamento longo, o valor teria de subir, ou seria caso de proteger a
   instância contra o encerramento automático.
3. `min_size = 2` impede que o grupo encolha a ponto de deixar uma única
   instância servindo.

&emsp; Não há proteção contra terminação configurada, e não precisa haver: a API
de leitura é sem estado, não mantém trabalho em andamento entre requisições, e
não consome fila. O único trabalho que poderia ser interrompido é a requisição em
voo, e é dela que o `deregistration_delay` cuida.

&emsp; Não há tempo de espera fixo entre ajustes, o chamado cooldown. Ele é
desaconselhado neste tipo de política, porque a própria natureza do algoritmo já
amortece a oscilação: a AWS impede um novo crescimento enquanto o anterior não
tiver efeito medido, e por padrão reduz o grupo de forma mais conservadora do que o
faz crescer. O que controla o ritmo aqui é o `instance_warmup`.

### 5.3 Estratégia de deploy e rollback

&emsp; “Política de rollback baseada em auto scale groups” tem um significado
técnico preciso, e não é “usamos Git”. Significa versão de launch template.

**Deploy**

&emsp; Uma versão nova da aplicação percorre este caminho:

1. `make push` constrói a imagem `backend` em arm64 e a publica no ECR com a tag
   do SHA do commit. O alvo recusa rodar com a árvore suja: uma imagem
   construída a partir de código não commitado não corresponde a commit nenhum,
   e o rollback deixaria de ter para onde voltar.
2. `make tf-apply` propaga a tag nova para o `user_data`, o que produz uma nova
   versão do launch template: o `user_data` faz parte do template, e mudá-lo é o
   que gera a versão.
3. O ASG aponta para `$Latest` e o `instance_refresh` substitui as instâncias de
   forma gradual, com `min_healthy_percentage = 50`. Com `min_size = 2`, isso
   significa que sempre resta uma instância servindo: o refresh derruba uma,
   espera a substituta passar no health check e no `instance_warmup` de 300 s, e
   só então segue para a próxima.

&emsp; Uma versão que não sobe não chega a receber tráfego. O `user_data` roda
sob `set -euo pipefail`: se o `docker pull` falhar, o container não é iniciado,
`/health/live` não responde, o target group reprova a instância e o refresh trava
em vez de continuar substituindo. A versão antiga permanece servindo.

**Rollback**

&emsp; O gatilho é declarado, e não deixado a critério: o alarme
`argus-events-dev-app-sem-alvo-saudavel` dispara quando `HealthyHostCount` fica
abaixo de 1 por dois períodos de 60 segundos. Ele publica no tópico SNS de alarmes
e é o sinal de que a versão nova não sobe. Quem decide é quem está conduzindo o
deploy, e o rollback não é automático de propósito: um rollback automático
disparado por uma indisponibilidade momentânea do banco reverteria uma versão que
estava correta.

&emsp; O procedimento é apontar o grupo para a versão anterior do launch template e
disparar novo refresh. O número da versão anterior sai do output
`launch_template_latest_version`, que deve ser anotado antes de publicar:

```bash
# 1. Descobrir as versões disponíveis
aws autoscaling describe-auto-scaling-groups \
  --auto-scaling-group-names argus-events-dev-app \
  --profile g4 --query 'AutoScalingGroups[0].LaunchTemplate'

# 2. Apontar o grupo para a versão anterior
aws autoscaling update-auto-scaling-group \
  --auto-scaling-group-name argus-events-dev-app \
  --launch-template LaunchTemplateId=<lt-id>,Version=<versao-anterior> \
  --profile g4

# 3. Substituir as instâncias em execução
aws autoscaling start-instance-refresh \
  --auto-scaling-group-name argus-events-dev-app \
  --profile g4

# 4. Acompanhar
aws autoscaling describe-instance-refreshes \
  --auto-scaling-group-name argus-events-dev-app \
  --profile g4 --query 'InstanceRefreshes[0].[Status,PercentageComplete]'
```

&emsp; O output `rollback_command` do Terraform imprime os passos 2 e 3 já
preenchidos com os identificadores da conta. Depois do rollback, `terraform apply`
proporia voltar para `$Latest`, então a reversão precisa ser acompanhada de
`backend_image_tag` fixada na tag boa em `terraform.tfvars`, senão o próximo
`apply` desfaz o rollback.

&emsp; O rollback do banco é separado e não é automático. Migration aplicada é
imutável por construção, porque `tools/migrate.py` guarda o checksum e aborta se o
arquivo mudar, e uma alteração destrutiva de schema não é revertida por trocar a
versão do launch template. O procedimento é outro: snapshot manual antes da
migration destrutiva, e restauração a partir dele se necessário, o que implica
substituir a instância e reapontar a `DATABASE_URL`. Por isso migration
destrutiva e deploy de aplicação não devem ir na mesma janela.

### 5.4 Observabilidade e alarmes

&emsp; O repositório já tinha 17 alarmes cobrindo ingestão, ETL, motor de
hipóteses e banco. Nenhum deles enxergava o caminho de leitura depois da
migração: o alarme `read-api-erros` observa `AWS/Lambda`, e a Lambda deixou de
estar no caminho. Os seis abaixo fecham essa lacuna. Todos publicam no mesmo
tópico SNS dos demais, porque destino único é o que evita metade dos alarmes ir
para um lugar que ninguém acompanha.

| Alarme | Métrica | Limiar | Ação |
|---|---|---|---|
| `app-sem-alvo-saudavel` | `HealthyHostCount` (mínimo) | < 1 por 2× 60 s | SNS → e-mail. **Gatilho de rollback** (5.3) |
| `alb-5xx` | `HTTPCode_ELB_5XX_Count` | > 5 em 5 min | SNS → e-mail. Erro do balanceador, não da aplicação |
| `app-5xx` | `HTTPCode_Target_5XX_Count` | > 5 em 5 min | SNS → e-mail. Sucessor do `read-api-erros` |
| `app-latencia` | `TargetResponseTime` p95 | > 5 s por 2× 5 min | SNS → e-mail. Alvo do RNF02 |
| `app-cpu` | `CPUUtilization` do ASG | > 80% por 3× 5 min | SNS → e-mail. Se a carga não subiu junto, é consulta cara |
| `app-no-maximo` | `GroupInServiceInstances` | ≥ `asg_max_size` por 2× 5 min | SNS → e-mail. Sem margem para a próxima rajada |

&emsp; Dois detalhes de configuração que mudam o comportamento e valem registro.
O alarme de alvo saudável usa `treat_missing_data = "breaching"`, ao contrário dos
demais: ausência de dado nessa métrica não é silêncio benigno, é o balanceador sem
nada para medir. E o alarme de latência observa o percentil 95, não a média: a
média esconde a cauda, e é a cauda que o usuário percebe. O percentil 95 é o valor
abaixo do qual 95% das respostas ficaram; alarmá-lo no limite que o RNF02 exige do
percentil 99 dá margem para agir antes de o requisito ser violado.

&emsp; Um alarme sem destinatário não é observabilidade. A assinatura de
e-mail do tópico SNS é condicional à variável `alarm_email`, que está comentada no
`terraform.tfvars.example`. Sem ela, o tópico é criado e ninguém é avisado. Está
registrado como risco na seção 8, e preenchê-la é pré-requisito de aceite (4.5).

**Painel**

&emsp; Até esta revisão o repositório tinha alarmes e nenhum painel: dava para
saber que algo quebrou, não para ver o sistema funcionando. O painel
`argus-events-dev` no CloudWatch agrega quatro visões, que são a leitura do
caminho síncrono de cima para baixo:

1. Requisições e erros no ALB: `RequestCount`, `HTTPCode_Target_5XX_Count` e
   `HTTPCode_Target_4XX_Count`.
2. Tempo de resposta do alvo: `TargetResponseTime` nos percentis 50, 95 e 99, com
   linha de anotação no alvo do RNF02.
3. Escalonamento: `GroupInServiceInstances`, `HealthyHostCount` e
   `RequestCountPerTarget`, com linha de anotação no valor-alvo da política. É
   este quadro que torna o escalonamento visível numa tela só: a carga sobe, cruza
   a linha, e a contagem de instâncias sobe atrás.
4. Banco: `CPUUtilization` e `DatabaseConnections` do RDS.

&emsp; O terceiro quadro é o material do Vídeo 1: ele mostra causa e efeito na
mesma imagem, o que a aba *Activity* do ASG sozinha não faz.

---

## 6. Vídeo 1 — Infraestrutura provisionada

&emsp; O primeiro vídeo reúne as quatro evidências de infraestrutura exigidas pela
rubrica diretamente no console da AWS: rede e logs distribuídos, acesso por bastion,
balanceamento com autoescalonamento e banco RDS.

**Link:** [Vídeo 1 — Infraestrutura provisionada](https://drive.google.com/file/d/1mkoyWfkYK4TOf163Gpez1w779KHUotQt/view?usp=sharing)

---

## 7. Vídeo 2 — Integração front-end e back-end

&emsp; O segundo vídeo demonstra o dashboard publicado e acompanha uma requisição
real entre o navegador, o API Gateway, as funções Lambda, o RDS e o CloudWatch. Este
é o caminho operacional mantido durante a migração; ele não é confundido com o
caminho ALB/ASG, demonstrado separadamente no Vídeo 1.

**Link:** [Vídeo 2 — Integração front-end e back-end](https://drive.google.com/file/d/125nh0PC_9Dq5Mtutgv6KJw86Plm8RIA1/view?usp=sharing)

### 7.1 Testes de validação funcional

&emsp; Os casos abaixo foram executados no ambiente publicado durante a preparação e
a gravação. As suítes correspondentes podem ser repetidas com `make -C apps/basica
test-authorizer`, `test-backend` e `test-frontend`.

| # | Caso | Pré-condição | Passos | Resultado esperado | Resultado obtido |
|---|---|---|---|---|---|
| 1 | Carregamento do front | Website S3 publicado | Abrir a URL pública | Página de autenticação disponível | HTTP 200 e tela carregada |
| 2 | Preflight CORS | Origem exata do website S3 configurada | Enviar `OPTIONS /api/v1/clock` com `Access-Control-Request-Headers: authorization` | Resposta permite a origem e o cabeçalho | HTTP 204 com CORS aceito |
| 3 | Token inválido | API disponível | Informar Bearer diferente do token da audiência `dashboard` | Acesso recusado sem detalhe sensível | 401/403 e mensagem tratada “Token recusado” |
| 4 | Token válido | Token de leitura recém-rotacionado | Autenticar e consultar `/api/v1/clock` | Painel abre e a API responde | HTTP 200; relógio e estrutura do painel carregados |
| 5 | Período sem eventos | Banco disponível, sem eventos na janela virtual selecionada | Abrir timeline, fontes, mudanças e incidentes | Estado vazio legível, sem erro de renderização | Endpoints HTTP 200 e componentes exibindo ausência de dados |

### 7.2 Comunicação entre serviços

&emsp; No caminho filmado, o bundle estático é obtido do S3 e chama a API HTTPS.
O preflight libera somente a origem configurada; em seguida, o authorizer valida o
Bearer da audiência `dashboard`. A função de leitura consulta o PostgreSQL com TLS,
devolve JSON ao navegador e grava a mesma operação no CloudWatch. O token permanece
mascarado na interface e não é persistido fora da aba.

| Salto | Origem → destino | Protocolo | Autenticação | Falha esperada se indisponível |
|---|---|---|---|---|
| 1 | Navegador → S3 website | HTTP 80 | Leitura pública apenas dos arquivos estáticos | Página indisponível; a evolução para HTTPS está planejada em 4.4 |
| 2 | Navegador → API Gateway | HTTPS 443 | CORS para a origem do front e `Authorization: Bearer` | CORS bloqueia a chamada ou a interface informa que a API não respondeu |
| 3 | API Gateway → Lambda authorizer | Integração AWS | Invocação autorizada pelo serviço; Bearer comparado aos hashes do Secrets Manager | Requisição falha fechada com 401/403 |
| 4 | API Gateway → Lambda de leitura | Integração AWS | Contexto validado pelo authorizer, com audiência `dashboard` | API retorna 5xx e o front apresenta erro controlado |
| 5 | Lambda de leitura → RDS | PostgreSQL 5432 com TLS | Usuário de leitura e senha fornecidos por configuração protegida | Consulta falha, resposta 5xx e ocorrência registrada no CloudWatch |
| 6 | Lambda de leitura → CloudWatch Logs | API do serviço em HTTPS | Permissão da `LabRole` | A API ainda pode responder, mas perde o rastro operacional até o envio ser restabelecido |

---

## 8. Riscos e limitações conhecidas

&emsp; Risco listado sem mitigação é lista de desculpas. As duas primeiras linhas
não são previsões: foram confirmadas no `apply` de 8 de setembro de 2026 e estão
detalhadas logo abaixo da tabela.

| Risco | Impacto | Probabilidade | Mitigação | Responsável |
|---|---|---|---|---|
| A `LabRole` não confia em `vpc-flow-logs.amazonaws.com` | Flow Logs no CloudWatch são criados sem erro e nunca escrevem — cláusula (a) sem evidência | **Confirmado** | Destino padrão em S3, que usa política de bucket em vez de papel IAM | Infraestrutura |
| A SCP — *Service Control Policy*, a regra que a organização impõe acima da conta e que nenhuma permissão local supera — nega `s3:GetBucketObjectLockConfiguration` | Todo `aws_s3_bucket` criado pelo stack quebra o `plan` seguinte; sem contorno, o stack completo não aplica | **Confirmado** | `flow_logs_bucket_name` e `alb_logs_bucket_name` aceitam bucket criado fora do Terraform; `-refresh=false` como paliativo para os buckets antigos | Infraestrutura |
| Trocar `create_network` recria o RDS | Perda das 33 tabelas carregadas | Alta, por desenho — a AWS não move instância entre VPCs | Snapshot manual antes do `apply`; `make load` reconstrói em 20–30 min | Infraestrutura |
| NAT em AZ única | Queda da AZ derruba a saída das duas sub-redes privadas; o ASG não sobe instância nova ali | Certa, por decisão de custo | Declarada, não escondida. Subir o segundo NAT dobra o custo (~US$ 32/mês) | Decisão de projeto |
| `db_multi_az` desligado | O RDS é ponto único de falha | Certa, por decisão de custo | Declarada. Em produção deve ser tratada como obrigatória | Decisão de projeto |
| Sessão do Learner Lab expira em horas, e o account ID muda a cada recriação | Trabalho interrompido no meio de um `apply`; saídas versionadas apontariam para conta inexistente | Alta | Nenhum identificador de conta é versionado; `make tf-test` valida a rede offline, sem sessão ativa | Infraestrutura |
| `terraform.tfstate` sem backend remoto | Estado local perdido significa recursos órfãos, invisíveis ao Terraform | Média | Procedimento de backend em S3 documentado em `infra/README.md` §2; adotar antes de mais de uma pessoa aplicar | Infraestrutura |
| Custo dos recursos ociosos contra o crédito do laboratório | NAT, ALB, ASG e bastion cobram por hora existindo, em uso ou não (~US$ 74/mês somados) | Alta | Provisionar próximo à apresentação e destruir depois; `make pause` não remove esses quatro | Infraestrutura |
| Saída irrestrita na porta 443 pelas sub-redes privadas | O NAT não protege contra exfiltração — só contra conexão de entrada | Média | VPC endpoints de interface com política de endpoint; não implementado, custo de ~US$ 7/mês por endpoint por AZ | Backlog |
| Nenhum alarme verifica a API de fora | Indisponibilidade da ponta só aparece pelo usuário | Média | Canário sintético do CloudWatch, ~US$ 10/mês; não implementado | Backlog |
| Carga inicial indisponível sem o dump de 4,15 GB | Banco recriado não volta ao estado anterior | Baixa | Os Parquet no bucket `origem` são a fonte de `make load`, e são versionados fora do repositório | Infraestrutura |
| A aplicação está em `/apps/basica` | A especificação da entrega cita `/apps/fullstack` | Certa | Divergência registrada na abertura deste artefato; decisão de nomenclatura a alinhar antes da tag da Sprint | Time |
| Restrições da `LabRole` para CloudFront, OAC, políticas e papéis IAM | O plano pode funcionar em uma conta AWS comum e falhar no laboratório, impedindo o bucket privado, o TLS do front-end ou a criação de identidades dedicadas | Alta | Validar previamente as ações exigidas pela topologia; quando houver negação, registrar a operação e o erro, reutilizar somente papéis autorizados e documentar o fallback do laboratório sem apresentá-lo como equivalente à arquitetura de produção | Infraestrutura e segurança |
| Regra SSH do bastion dependente do CIDR do administrador | Uma origem ampla expõe a porta 22; uma origem desatualizada bloqueia o acesso operacional quando a rede do administrador muda | Média | Restringir a entrada a um CIDR `/32`, nunca usar `0.0.0.0/0`, manter chaves individuais e rotacionáveis e revisar a regra antes e depois da manutenção; preferir Session Manager quando as permissões permitirem | Infraestrutura e segurança |
| Política incorreta do CloudFront para `/api/*` | A omissão do cabeçalho `Authorization` retorna 401; habilitar cache para respostas autenticadas pode servir dados fora do contexto correto | Média | Criar comportamento específico para `/api/*`, desabilitar o cache, encaminhar `Authorization` e testar sessões distintas antes da publicação; o comportamento padrão permanece exclusivo para os arquivos estáticos do S3 via OAC | Infraestrutura e back-end |
| Migração da API de Lambda para EC2 incompatível com o schema ou com o health check | Instâncias novas podem falhar o `/health/live`, entrar em ciclo de substituição ou receber tráfego antes das migrations necessárias | Média | Manter migrations retrocompatíveis, aplicar alterações de banco antes de liberar a nova versão, validar `/health/live` no target group e preservar a versão anterior do launch template para rollback por `instance refresh` | Back-end, dados e infraestrutura |

### 8.1 As duas restrições do ambiente, em detalhe

&emsp; As duas apareceram só no `apply`, e as duas condicionam o desenho da camada de
rede, e não são incômodos de operação.

&emsp; **1. A `LabRole` não confia no serviço de Flow Logs.** A verificação da política
de confiança devolve 53 serviços, entre eles `apigateway`, `ecs-tasks`, `lambda`,
`ec2` e `elasticloadbalancing`, e `vpc-flow-logs.amazonaws.com` não está na lista. Com `create_iam_roles = false`, obrigatório no laboratório, o destino
CloudWatch Logs é inviável. O padrão em S3, escolhido preventivamente, é o que permitiu
a cláusula ser atendida.

```bash
aws iam get-role --role-name LabRole \
  --query 'Role.AssumeRolePolicyDocument.Statement[].Principal.Service' --output json
```

&emsp; **2. A SCP da organização nega `s3:GetBucketObjectLockConfiguration`.** O
provider AWS chama essa API ao reler qualquer `aws_s3_bucket` recém-criado. O bucket
nasce, o `apply` falha na releitura e o recurso fica no estado quebrando todo `plan`
seguinte. Verificou-se que apenas essa chamada é negada: `GetBucketPolicy`,
`GetPublicAccessBlock`, `GetBucketEncryption`, `GetBucketLifecycleConfiguration` e
`GetBucketVersioning` são permitidas.

&emsp; A solução foram as variáveis `flow_logs_bucket_name` e `alb_logs_bucket_name`:
quando preenchidas, o Terraform não cria o bucket, mas continua gerenciando política,
bloqueio público, criptografia e ciclo de vida. Nenhum controle é perdido.

&emsp; Esta segunda restrição não é específica desta entrega. Ela atinge igualmente
`aws_s3_bucket.origem` e `aws_s3_bucket.frontend`, que já existiam: os dois foram
testados e recebem a mesma negação. Na prática, o stack completo não roda `plan` nem
`apply` nessa conta sem contorno. O paliativo imediato é `terraform plan
-refresh=false`, já que esses buckets estão no estado e sem refresh o provider não os
relê. A correção definitiva é estender o padrão de `flow_logs_bucket_name` aos outros
dois buckets, ou avaliar a migração para o provider 6.x, trabalho independente desta
camada de rede.

---

## Apêndice A — Variáveis e saídas do Terraform

&emsp; Apenas o que esta sprint introduziu. As demais estão documentadas com um
parágrafo cada em `apps/basica/infra/variables.tf`.

| Variável | Padrão | Efeito |
|---|---|---|
| `create_network` | `true` | Cria a VPC dedicada e tudo que depende dela: NAT, bastion, ALB, ASG. `false` volta à VPC padrão da conta. **Trocar para `false` num ambiente aplicado substitui o RDS e apaga o banco** |
| `vpc_cidr` | `10.0.0.0/16` | Bloco da VPC |
| `public_subnet_cidrs` | `["10.0.0.0/24","10.0.1.0/24"]` | Sub-redes públicas; validação exige no mínimo duas |
| `private_subnet_cidrs` | `["10.0.10.0/24","10.0.11.0/24"]` | Sub-redes privadas; validação exige no mínimo duas |
| `bastion_key_name` | `""` | Nome de um key pair existente. **Vazio não cria o bastion** |
| `bastion_allowed_cidr` | `0.0.0.0/32` | Única faixa de endereços na porta 22. A validação recusa `0.0.0.0/0` |
| `bastion_instance_type` | `t4g.micro` | Tipo do bastion |
| `app_port` | `5000` | Porta do gunicorn e do target group. Mudar aqui sem mudar o `Dockerfile` reprova todas as instâncias |
| `app_instance_type` | `t4g.small` | Instâncias do ASG. Graviton por compatibilidade com as imagens arm64, não por custo |
| `asg_min_size` | `2` | Validação exige ≥ 2 |
| `asg_max_size` | `6` | Teto; limita o estrago de rajada anômala |
| `asg_desired_capacity` | `2` | Tamanho inicial |
| `asg_target_requests_per_target` | `60` | Valor-alvo da política, em req/instância/min |
| `asg_health_check_grace_period` | `300` | Também serve como `instance_warmup`. Curto demais causa ciclo de reciclagem |
| `instance_profile_name` | `LabInstanceProfile` | Perfil das instâncias; no lab vem anexado à `LabRole` |
| `backend_image_tag` | `""` | Tag da imagem do backend. Vazio segue `worker_image_tag` |
| `alb_access_logs_enabled` | `true` | Access logs do ALB em S3 |
| `alb_access_logs_retention_days` | `30` | Expiração dos access logs |
| `alarm_latencia_p95_segundos` | `5` | Limiar do alarme de latência; alvo do RNF02 |

**Saídas úteis**

| Saída | Para quê |
|---|---|
| `api_url_alb` | URL base da API pelo ALB; é o valor de `ARGUS_API_URL` no `.env` |
| `alb_dns_name` / `alb_zone_id` | DNS do balanceador e zona hospedada, para alias futuro |
| `target_group_arn` | Alvo de `aws elbv2 describe-target-health` |
| `asg_name` | Nome do grupo, usado em todo comando de escalonamento e rollback |
| `launch_template_id` / `launch_template_latest_version` | **Anotar antes de todo deploy** — é a versão para a qual o rollback volta |
| `rollback_command` | O comando de rollback já preenchido com os identificadores da conta |
| `bastion_public_ip` | Destino do SSH e do túnel para o RDS |
| `vpc_id`, `private_subnet_ids`, `public_subnet_ids` | Conferência da topologia |
| `nat_gateway_ip` | IP de saída das sub-redes privadas; é o que um terceiro liberaria numa allowlist |
| `flow_log_destino`, `app_log_group_name` | Bucket S3 dos Flow Logs e log group da aplicação |
| `dashboard_url` | Link direto do painel do CloudWatch |

## Apêndice B — Comandos de verificação e diagnóstico

&emsp; Estes comandos verificam o ambiente sem registrar account ID, ARN, endereço
efêmero ou segredo na documentação. Eles pressupõem `AWS_PROFILE=g4` e
`AWS_REGION=us-east-1`.

```bash
export AWS_PROFILE=g4 AWS_REGION=us-east-1

# Confirma que a sessão está válida antes de qualquer operação.
aws sts get-caller-identity --query Account --output text

# Resume a capacidade e o estado das instâncias do ASG.
ASG="$(terraform -chdir=apps/basica/infra output -raw asg_name)"
aws autoscaling describe-auto-scaling-groups \
  --auto-scaling-group-names "$ASG" \
  --query 'AutoScalingGroups[0].{Min:MinSize,Desired:DesiredCapacity,Max:MaxSize,Instances:Instances[].LifecycleState}'

# Confere os targets e o health check do ALB.
TG="$(terraform -chdir=apps/basica/infra output -raw target_group_arn)"
aws elbv2 describe-target-health \
  --target-group-arn "$TG" \
  --query 'TargetHealthDescriptions[].TargetHealth.State'
curl -fsS "$(terraform -chdir=apps/basica/infra output -raw api_url_alb)/health/live"

# Confere o RDS sem imprimir endpoint ou credencial.
aws rds describe-db-instances \
  --query 'DBInstances[?contains(DBInstanceIdentifier, `argus-events-dev`)].{Status:DBInstanceStatus,Publico:PubliclyAccessible,MultiAZ:MultiAZ}'

# Confere os registros mais recentes da aplicação.
LOG_GROUP="$(terraform -chdir=apps/basica/infra output -raw app_log_group_name)"
aws logs describe-log-streams \
  --log-group-name "$LOG_GROUP" \
  --order-by LastEventTime --descending --max-items 5

# Executa o portão local de lint, testes, build e validação do Terraform.
make -C apps/basica check
```

## Apêndice C — Proveniência das decisões

&emsp; A tabela registra as decisões que alteraram a topologia ou o procedimento de
deploy entre as sprints. “Equipe G04” representa a decisão coletiva registrada no
repositório e nas sessões de implantação.

| Data | Decisão | Origem | Participantes |
|---|---|---|---|
| 08/09/2026 | Flow Logs entregues em S3, e não em CloudWatch Logs | Restrição do ambiente: a `LabRole` não confia em `vpc-flow-logs.amazonaws.com`, confirmado no `apply` (§8.1) | Equipe G04 |
| 08/09/2026 | Buckets desta camada aceitam nome criado fora do Terraform | Restrição do ambiente: a SCP nega `s3:GetBucketObjectLockConfiguration`, confirmado no `apply` (§8.1) | Equipe G04 |
| 08/09/2026 | Um NAT Gateway, e não um por AZ | Custo: ~US$ 32/mês por unidade contra o crédito do laboratório | Equipe G04 |
| 09/09/2026 | Manter Lambda/API Gateway enquanto o caminho ALB/ASG é validado | Rollback sem indisponibilidade e separação entre a evidência de infraestrutura e o fluxo integrado já estável | Equipe G04 |
| 10/09/2026 | CloudFront permanece planejado, com topologia de duas origens | TLS e bucket privado são necessários, mas o recurso não foi criado no Learner Lab desta sprint | Equipe G04 |
