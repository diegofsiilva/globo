# Argus — Sprint 05

Apresentação em português, 16:9, com a paleta preta, vermelha e branca das referências fornecidas. Corte do conteúdo: **06/10/2026**. Base documental: revisão `f3c498e` de `develop`, incluindo a ingestão por arquivos finalizada em 05/10.

## Arquivos

- `Argus-Sprint-05.pptx`: 25 slides, com textos, diagramas, dez tabelas e dois gráficos editáveis. Os gráficos têm workbooks incorporados. A captura histórica da interface permanece como imagem original.
- `Argus-Sprint-05.pdf`: versão visual para apresentação e consulta.
- `roteiro.md`: notas de fala, limites de cada afirmação e fontes por slide. O PPTX também incorpora essas notas.
- `custos.csv`: orçamento mensal de laboratório, em USD, sem arredondamento intermediário.
- `tco.csv`: sensibilidade do modelo acadêmico de três anos, em BRL.
- `generate.mjs` e `render_deck.py`: fontes para regenerar a apresentação.

A narrativa segue problema, entendimento das causas, arquitetura, implementação, implantação, condições de teste, resultados, gargalos, custos e conclusão. O slide 25 é um apêndice de rastreabilidade. As pesquisas e matrizes aparecem de forma breve, conforme solicitado.

## Limites das evidências

Os resultados de carga e resiliência vêm dos ensaios versionados, sem uma nova execução integral nesta tarefa. Os slides distinguem o ambiente AWS, o kind local e os testes de arquivos. Os 38 min 32 s de frescor são uma amostra única, não p95. A saturação de 21/09 ocorreu sem métricas do HPA. Em 24/09 as métricas funcionaram, mas não houve aumento de réplicas no EKS.

O motor determinístico de 11 famílias é implementado e testado. O refinador Ollama é opcional e não foi validado no EKS. O agente de investigação alternativo é uma proposta experimental, sem modelo definido ou publicação comprovada. A ingestão CSV/Parquet tem código e testes locais, mas os novos Deployments ainda não têm execução AWS comprovada.

A interface apresentada é a captura histórica já versionada, não uma fotografia da implantação atual. O ganho de MTTR, a qualidade causal em incidentes reais e a prontidão para produção não foram demonstrados.

## Orçamento de nuvem

Premissas: `us-east-1`, 730 horas/mês, sem impostos, créditos do laboratório, free tier ou descontos. Tarifas AWS consultadas em 06/10/2026. Este é um **orçamento**, não a fatura ou o inventário da conta.

| Parcela | Cálculo ou origem | USD/mês |
|---|---|---:|
| RDS + 100 GB | Estimativa histórica do README de infraestrutura, ainda a cotar | 62,00 |
| Fargate ARM | 730 × (1,5 vCPU × 0,03237984 + 3 GB × 0,00356004) | 43,25 |
| EKS, suporte padrão | 730 × 0,10 | 73,00 |
| NAT, horas | 730 × 0,045, sem bytes | 32,85 |
| ALB, horas | 730 × 0,0225, sem LCU | 16,43 |
| Três IPv4 | 730 × 3 × 0,005 | 10,95 |
| Subtotal parcial | Soma com precisão completa | **238,48** |

Fargate assume dois workers de 0,25 vCPU/0,5 GB e simulator/processing de 0,5 vCPU/1 GB cada. O simulador fica ligado o mês inteiro nesta estimativa. O upload novo fica nos nós EKS, cuja capacidade precisa ser confirmada. O subtotal não é um mínimo garantido, pois o RDS usa uma estimativa e nem todos os recursos foram cotados.

O cenário base acrescenta dois nós com uma **provisão de USD 0,05 por nó-hora**, incluindo EC2 e Auto Mode, além de USD 30 para serviços auxiliares e USD 10 para uso variável. Total: **USD 351,48/mês**. O ampliado usa quatro nós, USD 60 de serviços auxiliares e USD 50 variáveis. Total: **USD 494,48/mês**. A provisão dos nós não é uma tarifa AWS verificada. Substituí-la pelo tipo de instância, tarifa de Auto Mode e tempo observado no Billing é obrigatório para transformar o orçamento em cotação.

As reservas agrupam EBS, S3, ECR, bastion, backups, CloudWatch, Lambda, SQS, APIs, LCU, bytes de NAT e transferências. O número de IPv4 pode crescer se houver endereços públicos nos nós ou no bastion. Banco Multi-AZ, maior disponibilidade, pessoal, impostos e LLM externo exigem orçamento separado. Um segundo NAT com um IPv4 adiciona USD 36,50/mês antes do tráfego. O suporte estendido do EKS também muda a conta.

**Custo unitário:** orçamento mensal ÷ (eventos válidos persistidos ÷ 1.000.000). A redução do custo unitário em 10 milhões de eventos só ocorre se o mesmo orçamento atender à carga, hipótese ainda não comprovada. Retenção de 90 dias em 10 milhões de eventos/mês e 1 kB lógico por evento implica 30 GB antes de índices, WAL, réplicas e camadas adicionais.

Fontes primárias de tarifas: [EKS](https://aws.amazon.com/eks/pricing/), [Fargate](https://aws.amazon.com/fargate/pricing/), [VPC/NAT/IPv4](https://aws.amazon.com/vpc/pricing/), [ALB](https://aws.amazon.com/elasticloadbalancing/pricing/). A estimativa histórica de RDS está em `apps/fullstack/infra/README.md`.

## TCO e valor operacional

O TCO reapresenta, de forma condicional, o modelo acadêmico de `artefatos/entendimento_negocio.md`. Não extrapola o orçamento do laboratório para a produção e não trata o contrato hipotético como gasto real do parceiro.

Fórmulas utilizadas:

```text
Investimento = R$ 1.015.000
Baseline do contrato = R$ 4.064.000/ano (premissa)
Operação anual = R$ 282.000 + R$ 810.000 × rollout
Contrato residual = baseline × (1 − substituição × rollout)
TCO construir = investimento + soma(operação + contrato residual)
TCO contratar = 3 × baseline
```

Base: substituição de 50%, rollout de 40%/80%/100%. TCO construir de R$ 11.364.600, contra R$ 12.192.000 de contrato. Economia de R$ 827.400, aproximadamente 6,8%. A virada acumulada é perto do mês 25, assumindo fluxo linear no terceiro ano. Pessimista: substituição de 30%, rollout de 20%/40%/60%. TCO construir de R$ 13.561.960, R$ 1.369.960 mais caro. A conta usa valores completos antes do arredondamento, evitando diferenças da soma das tabelas em milhares.

O potencial de 302,4 horas/ano de plantão vem de 3 engenheiros × 6 horas × 4 incidentes/mês × 12 × 35% de redução. É uma hipótese do modelo, não uma economia observada e não entra no TCO. O piloto precisa medir tempo até uma hipótese útil, precisão das evidências e custo por evento persistido.

## Regeneração

Requisitos: Node.js, Python 3 e os pacotes `reportlab`, `Pillow` e `openpyxl`. Nesta máquina foram usados os runtimes já fornecidos pelo Codex, sem instalação de dependências. A fonte espera as fontes Arial em `C:/Windows/Fonts`.

```powershell
node slides/sprint-05/generate.mjs --python 'C:/caminho/para/python.exe'
```

Para preservar a entrega durante uma revisão, indique `--out` com uma pasta de rascunho. O comando padrão regenera os arquivos desta pasta. Os dados intermediários e prévias ficam em `.codex/slides-build`, ignorado pelo Git.

O pacote JavaScript `@oai/artifact-tool` do runtime disponível tinha diretórios vazios e não resolvia seu entrypoint. A geração usa uma alternativa em OOXML nativo, sem `python-pptx`, e um PDF vetorial produzido a partir da mesma geometria. O pacote PPTX, seus relacionamentos, a geometria e os caches dos gráficos com seus workbooks passaram pelos validadores disponíveis. O PDF foi revisado visualmente. A abertura e a renderização nativas em PowerPoint não foram verificadas, e o PDF não é uma captura de PowerPoint.
