## 4. Análise Financeira do Projeto

### 4.1. Introdução

&emsp; Esta seção apresenta a análise financeira preliminar da solução de telemetria distribuída para monitoração de frontends multiplataforma do Globoplay, considerando um horizonte de 1 ano. O objetivo é demonstrar a viabilidade econômica da proposta por meio do cálculo do ROI (*Return on Investment*), tratando o benefício como custo evitado e ganho operacional, com premissas justificadas.

&emsp; O parceiro não disponibilizou orçamento fechado para a implementação. Os valores apresentados são estimativas baseadas em premissas justificadas e fontes públicas. Quando uma estimativa é assumida pelo grupo, isso é explicitado.

&emsp; **Nota metodológica.** O parceiro não forneceu dados financeiros próprios. Todas as premissas vêm de fontes públicas (balanços, imprensa especializada, guias salariais, benchmarks de mercado) ou são estimativas da equipe, sempre sinalizadas na coluna "Confiança". Ajuste os números marcados como *Baixa* confiança assim que houver dado real do parceiro — eles são o principal risco do modelo.

&emsp; **Nota sobre simplificações didáticas.** Para fins didáticos, esta análise adota quatro simplificações que, em um estudo de viabilidade corporativo, seriam tratadas de forma mais granular: (i) o CAPEX é amortizado integralmente no Ano 1, sem distribuição plurianual; (ii) não se aplica taxa de desconto (WACC) ao fluxo de caixa do período, dado o horizonte de apenas 12 meses; (iii) o benefício é modelado exclusivamente como custo evitado com ferramenta de mercado, sem monetizar ganhos indiretos de retenção, SLA ou churn; (iv) o custo de infraestrutura de produção é derivado de um modelo de volume da própria equipe, e não de pricing negociado. Essas escolhas tornam o modelo mais transparente na leitura do resultado, sem comprometer a validade da conclusão qualitativa.

---

### 4.2. Premissas declaradas

&emsp; Escala de confiança: **Alta** = dado oficial ou fonte primária; **Média** = fonte secundária confiável, não é dado direto do parceiro; **Baixa** = estimativa da equipe, não validada.

#### Contexto financeiro da organização

&emsp; O Globoplay alcançou breakeven e lucro em 2025, pela primeira vez em 10 anos de operação, com cerca de 30 milhões de usuários ativos mensais (EXAME, 2026). O Grupo Globo fechou o ano com receita líquida consolidada de R$ 16,87 bi e lucro líquido de R$ 1,45 bi (TELETIME, 2026; ISTOÉ DINHEIRO, 2026).

&emsp; O dado operacionalmente relevante para esta análise é a escala de usuários (A1), que determina o volume de telemetria e, por consequência, o custo de infraestrutura calculado em 4.4. Os indicadores consolidados do grupo servem apenas para dimensionar a ordem de grandeza do investimento frente à capacidade financeira do parceiro.

#### A. Operação do parceiro

| # | Premissa | Valor | Confiança | Fonte |
|---|---|---|---|---|
| A1 | Usuários ativos mensais do Globoplay | ~30 milhões | Média | EXAME (2026). Base paga não divulgada |
| A2 | Receita líquida consolidada do Grupo Globo (2025) | R$ 16,87 bi | Alta | TELETIME (2026) |

&emsp; **Modelo de benefício.** O projeto é infraestrutura interna e não gera receita direta; o benefício é modelado como custo evitado com ferramentas de observabilidade de mercado, conforme o documento de escopo do parceiro.

#### B. Benefícios esperados

| # | Premissa | Valor | Confiança | Fonte |
|---|---|---|---|---|
| B1 | Contrato enterprise de observabilidade para operação de porte similar | US$ 800 mil – 2 mi/ano | Baixa | VENDORBENCHMARK (2026). A faixa descreve a trajetória de custo de organizações que não controlaram consumo, não um benchmark de operação comparável — ver limitação 1 |
| B2 | Câmbio USD/BRL | R$ 5,08 | Média | INVESTING.COM (2026), 3 ago. 2026 |
| B3 | Escopo da ferramenta de mercado substituível pelo MVP no 1º ano | 30–70% (cenários) | Baixa | Estimativa da equipe |
| B4 | Taxa de captura (rollout na base de dispositivos) no 1º ano | 20–60% (cenários) | Baixa | Estimativa da equipe |

#### D. Custos de implementação

| # | Premissa | Valor | Confiança | Fonte |
|---|---|---|---|---|
| D1 | Equipe do projeto (custo de mercado) | 5 devs (2 sênior + 3 pleno) | Baixa | Equipe típica de projeto Inteli |
| D2 | Duração do módulo acadêmico (MVP) | 10 semanas | Alta | Cronograma do módulo |
| D3 | Salário — Dev Back-End Sênior (SP) | R$ 12.250–20.600/mês | Alta | ROBERT HALF (2026) |
| D4 | Salário — Dev Full-Stack Pleno (SP) | R$ 9.550–15.900/mês | Alta | ROBERT HALF (2026) |
| D5 | Nuvem — ambiente de desenvolvimento e teste | ~R$ 3.000/mês | Baixa | Estimativa não detalhada por serviço |

#### D'. Premissas complementares derivadas pela equipe

&emsp; D1 a D5 não cobrem todos os itens de uma implantação em produção. As quatro premissas abaixo foram acrescentadas pelo grupo.

| # | Premissa | Valor | Confiança | Derivação |
|---|---|---|---|---|
| D6 | Encargos sobre salário (CLT) | +35% sobre o bruto | Média | Prática de mercado |
| D7 | Custo mensal carregado — sênior / pleno | R$ 24.000 / R$ 17.500 | Média | Médio-superior de D3 e D4 + D6 |
| D8 | Prazo até produção estável | 6 meses | Baixa | D2 (10 semanas) + ~3,5 meses de hardening, integração e governança |
| D9 | Volume de eventos em rollout total | ~3,6 bi eventos/mês | Baixa | A1 (30 mi) × ~8 sessões/mês × ~15 eventos/sessão |

&emsp; **Validação futura.** As premissas de menor confiança tornam-se verificáveis já no primeiro trimestre de operação, a partir de métricas que a própria plataforma coleta: custo por evento, cobertura de dispositivos e volume de eventos processados. Este modelo deve ser recalculado quando esses dados existirem.

---

### 4.3. Investimento inicial

&emsp; Estimativa do custo que o Grupo Globo incorreria para levar a solução a produção, não do custo do projeto acadêmico. A Fase 1 corresponde ao escopo do módulo (D2); as Fases 2 a 4 cobrem o que separa o MVP de um sistema em produção sob carga real.

| Fase | Escopo | Duração | Custo (R$) |
|---|---|---|---|
| 1. MVP | API única de ingestão, protocolos legados, pipeline de ingestão e armazenamento, normalização mínima, consultas de falhas críticas, dashboard | 10 semanas (~2,5 meses) | 274.000 |
| 2. Hardening e escala | Resiliência da ingestão, backpressure, tolerância a perda de eventos, testes de carga em pico, ajuste de retenção | 1,5 mês | 164.000 |
| 3. Integração e rollout | SDKs e agentes para TV, mobile e web; integração com pipeline de dados e stack de alertas do Globoplay; deploy gradual | 1,5 mês | 217.000 |
| 4. Segurança, privacidade e governança | Adequação à LGPD, política de retenção e anonimização, controle de acesso, documentação | Paralelo às Fases 2 e 3 (~0,5 FTE) | 60.000 |
| **Total** | | **~6 meses** | **R$ 715.000** |

**Composição.** Equipe core (D1 + D7) = 2 × R$ 24.000 + 3 × R$ 17.500 = R$ 100.500/mês.

| Item | Cálculo | Valor (R$) |
|---|---|---|
| Equipe core (Fases 1 a 3) | R$ 100.500 × 5,5 meses | 553.000 |
| Infraestrutura de desenvolvimento e teste (D5) | R$ 3.000 × 6 | 18.000 |
| Gestão técnica (~20% de dedicação) | R$ 30.000 × 20% × 6 | 36.000 |
| Especialistas do Globoplay (integração) | 2 engenheiros × 1 mês | 48.000 |
| Segurança, privacidade e governança | 0,5 FTE sênior × 4 meses + revisão jurídica | 60.000 |
| **Total** | | **715.000** |

---

### 4.4. Custos operacionais anuais

&emsp; Uma plataforma proprietária transfere o custo da licença para a operação interna. Esses custos são o principal contrapeso do benefício.

**Derivação da infraestrutura de produção (cenário base, B4 = 40%):**

| Etapa | Cálculo | Resultado |
|---|---|---|
| Volume em rollout total (D9) | 30 mi × 8 sessões × 15 eventos | ~3,6 bi eventos/mês |
| Volume no cenário base | 3,6 bi × 40% (B4) | ~1,44 bi eventos/mês |
| Dados brutos | 1,44 bi × ~500 bytes | ~720 GB/mês |
| Dados armazenados | compressão colunar ~10:1 | ~72 GB/mês |
| Recursos em regime permanente | fila + banco colunar + object storage + API autoescalada | ~35–40 vCPU |
| Custo mensal | nuvem com redundância (AMAZON WEB SERVICES, 2026; UPTRACE, 2026) | **~R$ 25.000/mês** |

| Item | Anual (R$) | Premissa |
|---|---|---|
| Infraestrutura de produção (nuvem) | 300.000 | R$ 25.000/mês; escala com B4 |
| Sustentação e plantão (dev pleno, 50%) | 105.000 | D7: R$ 17.500 × 50% × 12 |
| Evolução dos SDKs e agentes (dev sênior, 30%) | 86.000 | D7: R$ 24.000 × 30% × 12 |
| Suporte a engenharia e produto (~20h/mês) | 27.000 | D7: R$ 17.500 ÷ 160h × 20h × 12 |
| **Total** | **518.000** | R$ 218.000 fixos + R$ 300.000 variáveis |

&emsp; A parcela variável (R$ 750.000 × B4) é o item mais sensível do modelo e o único que a equipe controla por decisões de arquitetura: política de retenção, agregação de dados históricos, compressão e particionamento. Nenhum ganho de otimização foi incorporado ao modelo, por falta de premissa quantificável.

---

### 4.5. Benefícios econômicos estimados

&emsp; O projeto não gera receita direta. A fórmula `Baseline = Receita + Economia + Outros Benefícios` reduz-se ao termo de economia: o gasto anual evitado com uma plataforma de observabilidade de mercado. Adota-se o **piso** de B1 (US$ 800 mil/ano), por ser a estimativa mais defensável na ausência de dado do parceiro.

| Etapa | Fórmula | Cenário base |
|---|---|---|
| Baseline | B1 × B2 | US$ 800.000 × R$ 5,08 = **R$ 4.064.000/ano** |
| Ganho potencial | Baseline × B3 | R$ 4.064.000 × 50% = **R$ 2.032.000/ano** |
| Ganho efetivo (Ano 1) | Ganho potencial × B4 | R$ 2.032.000 × 40% = **R$ 812.800** |

&emsp; B3 mede a fração do escopo funcional que o MVP cobre — a solução própria não replica APM completo, tracing distribuído, integrações prontas e suporte contínuo. B4 mede a rampagem: o contrato só deixa de ser pago na proporção em que a base de dispositivos migra.

&emsp; **Nota metodológica.** (i) O benefício é custo evitado bruto; o custo de operar a plataforma própria é descontado em 4.6. (ii) O rollout parcial reduz simultaneamente benefício e custo de infraestrutura, por isso ambos são recalculados em conjunto na sensibilidade. (iii) No teto de B1 (US$ 2 mi/ano), todos os ganhos devem ser multiplicados por 2,5.

---

### 4.6. Cálculo do ROI

```
ROI = Benefício Líquido ÷ Investimento Inicial × 100
Benefício Líquido = Ganhos estimados (1 ano) − Custos operacionais anuais
```

#### Cenário base

| Componente | Valor | Origem |
|---|---|---|
| Investimento inicial | R$ 715.000 | 4.3 |
| Custos operacionais anuais | R$ 518.000 | 4.4 |
| Ganho efetivo no Ano 1 | R$ 813.000 | 4.5 (B3 = 50%, B4 = 40%) |
| **Benefício líquido** | **R$ 295.000** | R$ 813.000 − R$ 518.000 |
| **ROI (Ano 1)** | **~41%** | R$ 295.000 ÷ R$ 715.000 |

#### Análise de sensibilidade

&emsp; B3 e B4 são os principais vetores de incerteza (ambos Baixa confiança). Os cenários variam os dois simultaneamente; a parcela variável dos custos (R$ 750.000 × B4) é recalculada em cada linha.

| Cenário | B3 | B4 | Ganho efetivo Y1 | Custos anuais | Benefício líquido | ROI |
|---|---|---|---|---|---|---|
| Pessimista | 30% | 20% | R$ 244 mil | R$ 368 mil | −R$ 124 mil | −17% |
| Base | 50% | 40% | R$ 813 mil | R$ 518 mil | R$ 295 mil | 41% |
| Otimista | 70% | 60% | R$ 1.707 mil | R$ 668 mil | R$ 1.039 mil | 145% |

&emsp; No cenário pessimista o resultado é negativo: o custo de operar a plataforma própria supera o contrato evitado. No cenário base o projeto recupera boa parte do investimento já no Ano 1.

#### Comparativo de TCO: construir vs. contratar (3 anos)

&emsp; O ROI acima mede um único ano e trata custo evitado como se fosse entrada de caixa. Duas ressalvas tornam essa leitura insuficiente para uma decisão de infraestrutura. Primeiro, o projeto não visa lucro: é substituição de uma despesa por outra, e a métrica adequada é custo total de propriedade, não retorno. Segundo, contratos enterprise de observabilidade têm compromisso anual de volume mínimo — substituir 20% do uso não gera 20% de economia na fatura do mesmo ano.

&emsp; O comparativo abaixo confronta os dois caminhos ao longo de 3 anos, mantendo B3 = 50% e assumindo trajetória de rollout de 40% → 80% → 100% (B4). Na coluna *build*, o Globoplay paga simultaneamente a construção, a operação própria e o contrato residual sobre a fração ainda não substituída.

| R$ mil | Ano 1 | Ano 2 | Ano 3 | Total |
|---|---|---|---|---|
| **Contratar** — contrato integral | 4.064 | 4.064 | 4.064 | **12.192** |
| Construir — investimento (4.3) | 715 | — | — | 715 |
| Construir — operação (4.4) | 518 | 818 | 968 | 2.304 |
| Construir — contrato residual | 3.251 | 2.438 | 2.032 | 7.721 |
| **Construir** — total | 4.484 | 3.256 | 3.000 | **10.741** |
| **Diferença anual** | −420 | +808 | +1.064 | **+1.451** |

&emsp; Construir custa R$ 420 mil **a mais** que contratar no Ano 1: paga-se a construção e o contrato ao mesmo tempo. A virada ocorre no Ano 2, com cruzamento acumulado por volta do mês 18. Em 3 anos, a economia é de R$ 1,45 milhão, ou ~12% do TCO.

&emsp; A mesma comparação sob os cenários de sensibilidade:

| Cenário (B3; trajetória de B4) | TCO contratar | TCO construir | Diferença em 3 anos |
|---|---|---|---|
| Pessimista (30%; 20→40→60%) | 12.192 | 12.998 | **−806** (construir é mais caro) |
| Base (50%; 40→80→100%) | 12.192 | 10.741 | **+1.451** |
| Otimista (70%; 60→90→100%) | 12.192 | 8.324 | **+3.868** |

&emsp; O intervalo é largo o bastante para inverter a decisão: no cenário pessimista, contratar é a escolha economicamente correta ao longo de todo o horizonte.

---

### 4.7. Interpretação dos resultados

#### Viabilidade financeira

&emsp; No cenário base, construir é economicamente preferível a contratar, com economia de ~12% do TCO em 3 anos e virada no mês ~18.

| Referência | Valor | Proporção |
|---|---|---|
| Investimento inicial | R$ 715 mil | ~18% de um ano de contrato de mercado (baseline B1) |
| Operação anual em regime permanente | R$ 968 mil | ~24% do baseline |
| Custo operacional / ganho bruto (Ano 1) | R$ 518 mil / R$ 813 mil | 64% |

&emsp; O denominador correto é o gasto com observabilidade, e não o resultado do grupo: comparar R$ 715 mil ao lucro consolidado produz um percentual sem significado decisório. A decisão não se sustenta pelo Ano 1, e sim pela trajetória — o benefício cresce com o rollout, enquanto o investimento é pago uma única vez.

#### Justificativa do resultado

&emsp; Três fatores limitam o ROI do Ano 1:

- **Rampagem (B4 = 40%).** O contrato de mercado continua sendo pago na fração não migrada. Em regime permanente (B4 = 100%, B3 = 50%), o benefício líquido anual seria de ~R$ 1,06 milhão.
- **Substituição parcial (B3 = 50%).** Enquanto houver escopo residual, o contrato é reduzido de tier, não cancelado — e contratos com volume mínimo podem não permitir nem isso dentro do ciclo vigente.
- **Custo operacional próprio elevado (64% do ganho bruto no Ano 1).** Característico de projetos de construir em vez de comprar: parte do que se paga a um fornecedor é infraestrutura, que apenas muda de dono.

#### Ponto de equilíbrio

&emsp; Com B3 = 50%, o benefício bruto iguala os custos operacionais quando:

```
R$ 2.032.000 × B4 = R$ 218.000 + R$ 750.000 × B4  →  B4 ≈ 17%
```

| Marco | Condição |
|---|---|
| Sustentabilidade operacional (benefício = custos anuais) | B4 ≈ 17% |
| Virada do TCO acumulado (construir passa a ser mais barato) | mês ~18 |
| Recuperação integral do investimento via TCO | Ano 3 |

#### Benefícios operacionais não monetizados

| Benefício | Estimativa | Situação |
|---|---|---|
| Redução do tempo de diagnóstico de incidentes | ~3 engenheiros × 6h × 4 incidentes/mês × 35% de redução ≈ 300h/ano ≈ **R$ 45 mil/ano** (custo D7) | Não incluído no ROI |
| Visibilidade sobre dispositivos legados | Não quantificável — churn não diagnosticado em segmentos que hoje nenhuma ferramenta de mercado observa | Não incluído |
| Operação em eventos de pico (Copa 2026) | Não quantificável — custo reputacional de degradação não detectada | Não incluído |

#### Limitações da análise

**1. B1 pode superestimar o baseline.** A faixa de US$ 800 mil a US$ 2 mi/ano descreve organizações cujo consumo de observabilidade cresceu sem controle, e não o custo de uma operação de porte comparável ao Globoplay. A mesma fonte modela uma implantação de 500 hosts com APM e logs entre US$ 358 mil e US$ 678 mil em preço de tabela, caindo para US$ 197 mil a US$ 441 mil após negociação enterprise. Se o gasto real do parceiro estiver nessa faixa negociada, o baseline cai para cerca de metade a um quarto do adotado. O modelo é sensível a B1 nas duas direções:

| Parâmetro | Cenário negociado | Piso adotado | Teto da faixa |
|---|---|---|---|
| B1 | US$ 300 mil/ano | US$ 800 mil/ano | US$ 2 mi/ano |
| Baseline anual | R$ 1.524 mil | R$ 4.064 mil | R$ 10.160 mil |
| Benefício líquido Ano 1 | −R$ 213 mil | R$ 295 mil | R$ 1.514 mil |
| Diferença de TCO em 3 anos | −R$ 1.343 mil | +R$ 1.451 mil | +R$ 8.157 mil |

&emsp; Com B1 em US$ 300 mil/ano, construir é mais caro que contratar em todos os três anos. Este é o primeiro dado a solicitar ao parceiro; enquanto não houver o valor real do contrato do Globoplay, a conclusão de viabilidade permanece condicional.

**2. B3 e B4 não foram validados.** Sem plano de rollout acordado nem inventário de escopo funcional. A amplitude entre cenários vai de −R$ 806 mil a +R$ 3.868 mil de diferença de TCO — larga o bastante para inverter a decisão.

**3. Custo de infraestrutura é derivado, não cotado.** Um erro de fator 2 em D9 altera o custo operacional em ~R$ 300 mil/ano, suficiente para inverter o sinal do benefício. A métrica de custo por evento corrige essa premissa no primeiro trimestre de operação.

**4. Contrato residual tratado como proporcional.** O modelo assume que o contrato de mercado é reduzido na exata proporção do escopo substituído. Compromissos anuais de volume mínimo e ciclos de renovação podem atrasar essa redução em um ano inteiro, empurrando a virada do TCO para o Ano 3.

**5. Custos de time do parceiro possivelmente subestimados.** Assume-se ~2 engenheiros por 1 mês para integração. Se cada plataforma exigir SDK mantido por time separado, integração e manutenção anual crescem de forma relevante.

**6. Nenhum ganho de receita foi modelado — e este é o benefício principal do projeto.** A solução existe para detectar falhas de frontend, não para reduzir licença de software. Se 0,1% da base de assinantes for retida por melhor qualidade de experiência, o efeito superaria todo o custo evitado aqui modelado. Na ausência de dados de churn do parceiro, o benefício central do projeto permanece fora da conta, e o resultado apresentado deve ser lido como piso, não como estimativa central.

---

### Referências bibliográficas

AMAZON WEB SERVICES. Pricing de serviços de computação e armazenamento. Seattle: AWS, 2026. Disponível em: https://aws.amazon.com/pricing/. Acesso em: 4 ago. 2026.

BEM PARANÁ. Globoplay acelera em 2026, supera falhas e se impõe na guerra do streaming. Curitiba, 1 maio 2026. Coluna TV Canal 1, por Ayrton Tartuce. Disponível em: https://www.bemparana.com.br/publicacao/colunas/tv-canal-1/globoplay-acelera-em-2026-supera-falhas-e-se-impoe-na-guerra-do-streaming/. Acesso em: 4 ago. 2026.

EXAME. Após 1º lucro em 10 anos de vida, Globoplay se prepara para virar o jogo na guerra do streaming. São Paulo, 25 fev. 2026. Por Mateus Omena. Disponível em: https://exame.com/pop/apos-1o-lucro-em-10-anos-de-vida-globoplay-se-prepara-para-virar-o-jogo-na-guerra-do-streaming/. Acesso em: 4 ago. 2026.

INVESTING.COM. Cotação USD/BRL. 2026. Disponível em: https://br.investing.com/currencies/usd-brl. Acesso em: 3 ago. 2026.

ISTOÉ DINHEIRO. Globo fatura R$ 18,2 bilhões em 2025, mas lucro cai; veja números do balanço. São Paulo, 25 mar. 2026. Disponível em: https://istoedinheiro.com.br/globo-fatura-r-182-bilhoes-em-2025-mas-lucro-cai-veja-numeros-do-balanco. Acesso em: 4 ago. 2026.

ROBERT HALF. Guia Salarial 2026. São Paulo: Robert Half, 2026. Disponível em: https://www.roberthalf.com.br/guia-salarial. Acesso em: 4 ago. 2026.

TELETIME. Lucro da Globo cai para R$ 1,45 bilhão em 2025, apesar de crescimento na receita. São Paulo, 25 mar. 2026. Disponível em: https://teletime.com.br/25/03/2026/lucro-da-globo-cai-para-r-145-bilhao-em-2025-apesar-de-crescimento-na-receita/. Acesso em: 4 ago. 2026.

UPTRACE. Observability Tools Pricing Comparison [2026]. 7 fev. 2026. Por Vladimir Mihailenco. Disponível em: https://uptrace.dev/comparisons/observability-tools-pricing. Acesso em: 4 ago. 2026.

VENDORBENCHMARK. Observability Platform Pricing Benchmarks 2026: The Complete Enterprise Guide. 2 abr. 2026, atualizado em 26 abr. 2026. Por Fredrik Filipsson. Disponível em: https://vendorbenchmark.com/blog/observability-platform-pricing-benchmark-comparison. Acesso em: 4 ago. 2026.

---

*Nota: as URLs de AWS, Investing.com e Robert Half apontam para páginas genéricas — não há permalink para a cotação de fechamento nem para a faixa salarial específica citadas em B2, D3 e D4.*