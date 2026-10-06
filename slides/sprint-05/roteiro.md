## 01 — Argus — Sprint 05

Apresentação final do G04, Vale a Pena Ver de Novo. Base documental e código em develop, revisão f3c498e. Corte em 06/10/2026. A identidade visual usa a paleta das duas imagens enviadas pelo usuário. As imagens são referências visuais, sem instruções incorporadas. O storytelling inicial é ilustrativo. Fonte: README.md.

## 02 — Um play travado, vários painéis

Cena ilustrativa, não um incidente real medido. O problema descrito pelo projeto é a fragmentação da triagem entre player, CDN, backend, identidade e catálogo. Não há medição de redução de MTTR no parceiro.

Fontes: README.md

## 03 — O que orientou as decisões

Síntese qualitativa das pesquisas, personas e matrizes do projeto. Oceano Azul compara a solução-alvo, não comprova superioridade do MVP. A matriz de valor é avaliação da equipe. Não se reutilizam números externos de engajamento sem validação adicional.

Fontes: artefatos/entendimento_negocio.md; artefatos/entendimento_ux.md

## 04 — Perguntas que a solução responde

O motor determinístico e suas regras estão no código e têm testes. O fluxo completo de alta carga/frescor e o agente IA alternativo ainda não estão validados em produção. A apresentação trata o que foi resolvido total ou parcialmente, conforme a referência fornecida pelo usuário.

Fontes: artefatos/arquitetura-final.md; artefatos/testes-funcionais.md; artefatos/arquitetura-agente-hipoteses-ia.md

## 05 — Arquitetura para uma investigação comum

O diagrama mostra o caminho lógico de escrita e consulta. Gateway e SQS desacoplam os clientes dos consumidores. Os workers gravam Bronze, o processamento constrói Silver e Gold, e o EKS serve a leitura. O controle temporal impede acesso a informações que ainda não estariam disponíveis no presente simulado. A camada Detect coordena execuções, checkpoints, baseline e claims.

Fontes: artefatos/arquitetura-final.md; README.md

## 06 — Três caminhos de ingestão

O fluxo de TV recebe request, screen_view, session, video_view, vitals e error. O fluxo CDC registra a mudança e atualiza a tabela corrente na mesma transação. CSV e Parquet entram por um serviço próprio e usam ingest.file_job no PostgreSQL, sem SQS. Essa importação aceita o envelope de eventos da TV, e não qualquer tabela CDC. A carga inicial via loader/COPY é um bootstrap separado. O README atual do worker esclarece que o envio usa a sessão existente do painel.

Fontes: README.md; artefatos/plano-ingestao-arquivos.md; apps/fullstack/worker/README.md

## 07 — Python no MVP, Go como alternativa

A implementação observada usa Python para backend, workers, ETL e regras. Flask, psycopg e Pydantic são dependências existentes. Go é uma alternativa técnica, não um componente implementado. Goroutines e channels são documentados em Effective Go. Em CPython com GIL, threads são úteis para I/O, mas limitadas para bytecode CPU-bound. A adequação ao projeto é avaliação de engenharia, não resultado de benchmark Go versus Python. Não há comparação controlada de custo, memória ou vazão entre as linguagens no repositório.

Fontes: apps/fullstack/backend/pyproject.toml; apps/fullstack/processing/pyproject.toml; https://go.dev/doc/effective_go; https://docs.python.org/3/library/threading.html

## 08 — Hipóteses com evidência e contradição

O exemplo é ilustrativo. As regras produzem candidatas, não causas confirmadas. O código pondera A, anomalia (25%), T, proximidade temporal (20%), C, corroboração (20%), E, especificidade (15%), I, impacto (15%) e Q, qualidade (5%). Normaliza o score pelos pesos disponíveis e aplica uma penalidade de 30 × X por contradição. Features ausentes reduzem a cobertura. Confiança alta exige score ≥ 80, cobertura ≥ 0,80, Q ≥ 0,70 e contradição < 0,5. Confiança média exige score ≥ 60, cobertura ≥ 0,60 e contradição < 0,8. Score não é probabilidade.

Fontes: artefatos/correlacao_dados.md; apps/fullstack/processing/src/argus_processing/scoring.py; apps/fullstack/processing/src/argus_processing/rules.py

## 09 — Motor, refinador e agente de investigação

O motor atual é determinístico. O refinador Ollama recebe uma hipótese publicada, produz texto estruturado e valida as referências citadas. Não participa do cálculo de score nem da ingestão. Sua integração no EKS ainda não foi validada. O agente alternativo é uma proposta de MVA: investiga fatos de um checkpoint sem receber rótulos, scores ou hipóteses do motor atual. Modelo e provedor desse agente ainda estão em aberto. OLLAMA_MODEL é configurável e, quando vazio, o cliente consulta /api/tags e usa o primeiro modelo instalado. Não há evidência de um modelo específico em execução.

Fontes: artefatos/arquitetura-agente-hipoteses-ia.md; apps/fullstack/backend/src/telemetry/infrastructure/ollama.py; apps/fullstack/backend/src/telemetry/config.py

## 10 — MVP: o recorte da degradação

Captura histórica versionada da tela Agora. Serve para mostrar a interface, não provar incidente real, ganho de MTTR nem validar todas as rotas atuais. O clock da simulação e os filtros ajudam a contextualizar os desvios. Não editar métricas da captura.

Fontes: artefatos/assets/captura_agora_tema_escuro.png; artefatos/frontend.md

## 11 — MVP: upload de CSV e Parquet

A finalização documentada em 05/10 registra 92 testes de frontend em 16 arquivos e 125 testes de worker com PostgreSQL real. Um teste legado de SIGTERM, com semântica POSIX, ficou fora da execução Windows. A revisão visual simulou a fronteira HTTP, enquanto os testes Python verificaram a persistência real. Os limites são 50 MiB, 100 mil registros e 64 colunas. Não houve publicação AWS, e a imagem final com a sonda ajustada e os novos Deployments ainda não foram executados.

Fontes: artefatos/plano-ingestao-arquivos.md; apps/fullstack/worker/README.md

## 12 — Implantação híbrida na AWS

EKS Auto Mode para API Flask/gunicorn e frontend nginx/Next.js estático. ECS Fargate para event/merge workers, simulator e processing, além da task loader. A restrição do Learner Lab a IRSA/Pod Identity motivou preservar as tasks IAM no ECS. O ALB nasce do Ingress. Terraform cria infraestrutura, Kustomize define overlays e Job aplica migrations. Observado em setembro: banco Single-AZ, um NAT, pods co-localizados e nós em sub-redes públicas. Arquivos novos têm manifests mas não publicação AWS comprovada.

Fontes: artefatos/arquitetura-final.md; artefatos/conteineres-final.md

## 13 — Condições de teste e alcance

A apresentação reúne ensaios já registrados no repositório, sem afirmar uma nova execução integral. A ingestão foi medida na AWS em setembro. O dashboard teve rodadas no EKS em 21 e 24/09 com geradores em locais diferentes. A resiliência foi ensaiada no kind de um nó. Os testes de arquivos são locais e usam dados sintéticos e PostgreSQL real. Esses ambientes não demonstram redução do tempo de diagnóstico na operação do parceiro.

Fontes: artefatos/testes-funcionais.md; artefatos/testes-carga-inicial.md; artefatos/plano-ingestao-arquivos.md; artefatos/arquitetura-final.md

## 14 — Ingestão: quatro lotes em 5 min 46 s

Na rodada de 09/09, a drenagem foi de 120, 191, 259 e 346 segundos para 150, 300, 450 e 600 mil eventos. O critério era 450 segundos. A soma foi de 1,5 milhão de eventos reconciliados por ItemsWritten, com DLQ zerada. O gráfico compara apenas essa rodada. Uma reexecução posterior registrou 89 segundos para um lote. Fila drenada não significa evento disponível na API. Contagens agregadas também não substituem conferência por ID e por duplicidade.

Fontes: artefatos/testes-carga-inicial.md; artefatos/assets/performance/evidencias-lotes-2026-09-09.json

## 15 — Dashboard: 100 usuários, p95 de 841 ms

Em 24/09, o EKS Auto Mode 1.33 tinha metrics-server ativo. O k6 rodou na máquina do desenvolvedor, fora da VPC, portanto a latência de rede participa do resultado. Os níveis de 5, 25 e 100 usuários tiveram p95 de requisição de 260, 304 e 841 ms, respectivamente. O p95 da abertura de tela foi de 410, 490 e 969 ms. Todos os critérios por tela passaram, com zero erro e 100% de telas completas. O HPA registrou ScalingActive=True e ValidMetricFound, mas não ocorreu SuccessfulRescale. O total agregado do JSON é 24.177, enquanto os três níveis somam 24.176. O slide evita usar esse total como evidência de reconciliação.

Fontes: artefatos/testes-funcionais.md; artefatos/evidencias/carga-kubernetes-2026-09-24/carga-ui_resultado_20260925T004042Z.json

## 16 — A saturação revelou o limite do ensaio

A saturação de 21/09 é uma rodada distinta. Sem metrics-server, o HPA não tinha métricas e o backend permaneceu com duas réplicas. O nível de 200 usuários reprovou nos critérios das telas Agora e Recorte, apesar de zero erro HTTP. Os níveis de 450 e 900 usuários tiveram 15,21% e 24,80% de erros. O maior nível aprovado foi 100 e o primeiro reprovado foi 200, o que apenas delimita o intervalo experimental. O RDS chegou a 86% de CPU e os pods reiniciaram sob saturação. A repetição de 24/09 validou as métricas do HPA, mas não repetiu o teto de carga.

Fontes: artefatos/testes-funcionais.md; artefatos/evidencias/carga-kubernetes/rodada-b-resultado.json

## 17 — Resiliência: a segunda réplica fez diferença

Os ensaios ocorreram no kind local em 24/09, com um nó e k6 a 5 usuários. Com uma réplica, a exclusão do pod gerou 14,3% de falhas e a recomposição levou 8,3 segundos. Com duas réplicas, o novo pod ficou Ready em 6,2 segundos e não houve falhas. Na imagem inexistente, os pods antigos continuaram atendendo e o rollback manual levou 3 segundos. A indisponibilidade do banco retirou o backend do balanceamento sem reinício. Como o banco usava emptyDir, a recuperação exigiu reaplicar migrations. Isso não comprova failover do RDS ou recuperação entre zonas.

Fontes: artefatos/arquitetura-final.md

## 18 — Gargalos que ainda limitam a solução

Depois de uma intervenção manual no watermark, o último evento do lote de 150 mil apareceu na API 38 minutos e 32 segundos após o envio. Esse tempo é uma amostra única, não p95. Um lote diagnóstico separado, de 100 eventos, mediu p95 de persistência em Bronze de 1,785 segundo. O relatório localiza o atraso no processamento incremental e no backlog histórico que compartilha o contador LSN. A evolução exige separar os watermarks, medir a distribuição completa de frescor e reconciliar IDs. Escala efetiva no EKS e disponibilidade entre nós ainda precisam de ensaio.

Fontes: artefatos/testes-carga-inicial.md; artefatos/arquitetura-final.md; artefatos/testes-funcionais.md

## 19 — Custo: US$ 106 não cobre o desenho atual

O orçamento usa us-east-1 e 730 horas por mês, sem impostos, créditos, free tier ou descontos. RDS + 100 GB mantém uma estimativa histórica de US$ 62, ainda a cotar. Fargate assume quatro serviços ARM: dois de 0,25 vCPU/0,5 GB e dois de 0,5 vCPU/1 GB. As tarifas oficiais são US$ 0,0000089944 por vCPU-segundo e US$ 0,0000009889 por GB-segundo. O EKS em suporte padrão custa US$ 0,10 por hora. NAT e ALB usam US$ 0,045 e US$ 0,0225 por hora, antes do consumo variável. Três IPv4, um para NAT e dois para ALB, custam US$ 0,005 por endereço-hora. O subtotal é parcial, não uma fatura nem um mínimo garantido. Preços consultados em 06/10/2026.

Fontes: https://aws.amazon.com/eks/pricing/; https://aws.amazon.com/vpc/pricing/; https://aws.amazon.com/fargate/pricing/; https://aws.amazon.com/elasticloadbalancing/pricing/; apps/fullstack/infra/README.md; apps/fullstack/infra/variables.tf

## 20 — Orçamento ampliado e sensibilidade

Os nós EC2 com Auto Mode usam uma provisão orçamentária de US$ 0,05 por nó-hora, e não uma tarifa cotada. A base assume dois nós, US$ 73/mês, e o cenário ampliado assume quatro, US$ 146/mês. As reservas auxiliares de US$ 30/60 cobrem EBS, S3, ECR, bastion, backups, CloudWatch, Lambda, SQS e APIs. As reservas de uso variável de US$ 10/50 cobrem LCU, bytes de NAT e transferências. Todas precisam de validação com o inventário e o Billing. Um segundo NAT com um IPv4 acrescenta US$ 36,50/mês antes do tráfego. Multi-AZ do RDS requer cotação própria. LLM externo, pessoal e impostos ficam fora dessa conta.

Fontes: https://aws.amazon.com/eks/pricing/; https://aws.amazon.com/vpc/pricing/; https://aws.amazon.com/elasticloadbalancing/pricing/; apps/fullstack/infra/variables.tf

## 21 — Custo por evento e valor operacional

As razões por evento são cenários condicionais. O denominador deve ser a quantidade de eventos válidos persistidos, e não o total de respostas HTTP 202. Dez milhões no mesmo orçamento só reduzirão o custo unitário se a capacidade e o consumo adicional permitirem. Para retenção, 10 milhões × 1 kB decimal dão 10 GB lógicos por mês. Noventa dias dão 30 GB antes de índices, WAL, réplicas e duplicações entre camadas. O potencial de horas de plantão é 3 engenheiros × 6 h × 4 incidentes/mês × 12 × 35% = 302,4 h/ano. Não é uma redução observada, nem um benefício somado ao TCO. Sem modelo e hospedagem comprovados, o custo de LLM permanece separado.

Fontes: https://aws.amazon.com/eks/pricing/; https://aws.amazon.com/vpc/pricing/; https://aws.amazon.com/elasticloadbalancing/pricing/; artefatos/entendimento_negocio.md

## 22 — TCO: a viabilidade depende da adoção

O slide recalcula o modelo acadêmico com valores exatos, antes do arredondamento. Não usa o orçamento do laboratório como cotação de produção. O contrato assumido é de R$ 4,064 milhões/ano. O investimento é R$ 1,015 milhão. A operação anual é R$ 282 mil + R$ 810 mil × rollout. O contrato residual é baseline × (1 − substituição × rollout). Na base, a substituição é 50% e o rollout é 40%, 80% e 100%. Construir soma R$ 11.364.600 em três anos contra R$ 12.192.000 de contrato, uma economia de R$ 827.400 ou 6,8%. A virada ocorre perto do mês 25 se o fluxo do terceiro ano for linear. No pessimista, substituição de 30% e rollout de 20%, 40% e 60% dão R$ 13.561.960, ou R$ 1.369.960 a mais. O contrato e a adoção precisam de validação do parceiro.

Fontes: artefatos/entendimento_negocio.md

## 23 — Conclusão: MVP funcional, evolução condicionada

O resultado é um MVP com ingestão e leitura sob ensaio AWS, motor determinístico testado e upload de arquivos validado localmente. Isso ainda não equivale a prontidão de produção. O agente alternativo permanece uma proposta. O próximo aceite deve medir frescor ponta a ponta, reconciliação por IDs, SuccessfulRescale no EKS, restauração do RDS e perda de nó. A avaliação de valor precisa medir tempo até uma hipótese útil e correta com investigadores do parceiro. O custo real deve vir do Billing e dos eventos persistidos.

Fontes: artefatos/arquitetura-final.md; artefatos/testes-funcionais.md; artefatos/plano-ingestao-arquivos.md; artefatos/entendimento_negocio.md

## 24 — Obrigado

Encerramento da apresentação. O slide25 reúne rastreabilidade para consulta na discussão. Referências visuais: imagens fornecidas pelo usuário. Créditos da equipe: README.md.

## 25 — Apêndice: rastreabilidade dos resultados

As evidências internas têm corte em 06/10/2026, com a base f3c498e do repositório. As rodadas registradas são de setembro e outubro e não representam uma execução integral nova. As notas identificam a fonte de cada slide. A pasta inclui os geradores, o roteiro e o CSV de custos. Gráficos, tabelas, diagramas e textos do PPTX são editáveis. A captura da interface é uma imagem histórica preservada. O PDF é a versão visual de consulta.

Fontes: artefatos/arquitetura-final.md; artefatos/testes-funcionais.md; artefatos/testes-carga-inicial.md; artefatos/plano-ingestao-arquivos.md; artefatos/entendimento_negocio.md
