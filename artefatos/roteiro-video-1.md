# Vídeo 1 — guia de gravação da infraestrutura do Argus

Meta: **6 minutos e 40 segundos**, dentro da faixa de 5 a 7 minutos exigida na seção 6 de [infraestrutura-integracao.md](infraestrutura-integracao.md). Grave o console AWS com recursos reais e valores legíveis. As falas abaixo dependem da confirmação das telas; não leia uma afirmação que o ambiente não comprova.

## Antes de gravar: confirmar o ambiente

Na revisão local de 08/09/2026, o artefato ainda classifica a nova topologia como planejada. O Terraform em `apps/basica/infra` contém RDS, logs e serviços da arquitetura anterior, mas não declara NAT Gateway, bastion, ASG, ALB ou VPC Flow Logs. A API de leitura permanece definida como Lambda. Isso não comprova ausência desses recursos na conta: podem ter sido criados por outra pessoa ou em outra branch. É necessário conferir o console antes de gravar.

- [ ] VPC e sub-redes públicas e privadas em duas zonas disponíveis.
- [ ] Rotas associadas às sub-redes corretas; NAT disponível.
- [ ] Flow Logs ativos e logs de aplicação com eventos recentes.
- [ ] Bastion e acesso administrativo funcionando com origem restrita.
- [ ] ASG associado ao target group, política configurada e targets saudáveis.
- [ ] RDS disponível; acesso público, sub-redes, regras e backups conferidos.

Se faltar algum recurso, a gravação completa depende de provisioná-lo ou localizar o ambiente correto. Mostrar apenas Lambda e ECS não evidencia o item de EC2 com ASG e ALB.

## Roteiro: tela e fala

### 0:00–0:20 — Abertura

**Tela:** console AWS; identificação do projeto. Informe os integrantes verbalmente ou por uma legenda curta.

**Fala:** “Somos o grupo 4 e este é o Argus, nosso sistema de telemetria para diagnóstico de falhas na entrega de streaming. Neste vídeo vamos demonstrar a infraestrutura provisionada na AWS: rede, logs, acesso administrativo, escalonamento, balanceamento e banco de dados.”

### 0:20–1:40 — VPC, sub-redes e NAT

**Tela:** VPC → Your VPCs → VPC do projeto. Mostre CIDR e mapa de recursos. Abra Subnets, as associações das Route tables e NAT gateways.

**Ações:** mostre as duas zonas; uma rota pública `0.0.0.0/0` para o Internet Gateway; uma rota privada `0.0.0.0/0` para o NAT; NAT no estado disponível em sub-rede pública. Confira também ausência de IP público na instância da aplicação.

**Fala, se confirmado:** “Esta é a VPC do Argus. As sub-redes estão distribuídas nestas duas zonas de disponibilidade. A tabela da sub-rede pública tem rota para o Internet Gateway. Na privada, a saída passa pelo NAT Gateway. Isso permite às instâncias privadas iniciar conexões externas, como downloads necessários à execução, sem receber conexões iniciadas da internet pelo NAT. Aqui mostramos as associações das tabelas para comprovar qual rota cada sub-rede utiliza.”

Não afirme redundância do NAT se houver apenas um gateway: explique que ele é uma limitação de disponibilidade dessa configuração.

### 1:40–2:20 — Logs

**Tela:** VPC → Flow logs; depois CloudWatch → Log groups. Abra eventos recentes de rede e aplicação.

**Fala:** “Os Flow Logs registram informações do tráfego de rede, incluindo origem, destino e aceitação ou rejeição. Os logs da aplicação registram o processamento. Aqui vemos os horários e os campos disponíveis em cada camada, que ajudam a investigar uma falha.”

**Demonstração:** selecione um evento real e explique seus campos. Se houver identificador propagado entre serviços, mostre o mesmo valor nos dois logs. Flow Logs não registram o conteúdo HTTP nem o identificador de requisição da aplicação; não prometa essa correlação direta.

### 2:20–3:15 — Bastion e prova de acesso

**Tela:** EC2 → Instances → bastion → Security. Mostre sub-rede pública, entrada TCP 22 restrita ao IP autorizado e regra da instância privada permitindo SSH a partir do security group do bastion.

**Fala, se confirmado:** “O bastion concentra o acesso administrativo. A porta SSH aceita apenas a origem autorizada que aparece nesta regra. A instância privada aceita esse acesso a partir do grupo de segurança do bastion. Assim, não precisamos expor a instância da aplicação diretamente à internet.”

**Prova:** prepare previamente a conexão SSH com salto pelo bastion, ou um túnel até o RDS, e demonstre que funciona. Na instância privada, `hostname` comprova o host alcançado; um acesso autenticado ao banco pode mostrar `SELECT 1;`. Use somente o caminho permitido pelas regras reais. Não abra senha, chave privada, tokens ou arquivos de configuração na gravação.

### 3:15–4:35 — ASG e ALB

**Tela:** EC2 → Auto Scaling Groups → grupo da aplicação. Mostre capacidade mínima, desejada e máxima, sub-redes, política de escalonamento, métrica e valor-alvo. Depois abra Load Balancers e Target Groups.

**Fala:** “O grupo mantém a capacidade desejada dentro destes limites mínimo e máximo. Esta política usa a métrica e o valor-alvo exibidos aqui para ajustar a capacidade. O Application Load Balancer recebe as requisições e encaminha para as instâncias saudáveis deste target group. Este é o listener e este é o caminho de verificação de saúde configurado.”

**Ações:** leia os valores reais; explique a métrica escolhida; mostre targets `healthy`, porta e caminho do health check. Não confunda escalonamento por carga com substituição de instância com falha.

### 4:35–5:35 — Evidência de escalonamento

**Tela:** gerador de carga autorizado para a aplicação do grupo, métrica/alarme e Activity do ASG; finalize com a nova instância em serviço e saudável no target group.

**Fala, após observar o resultado:** “Com o aumento da carga, a métrica atingiu a condição da política. O histórico registra a ampliação da capacidade, e aqui vemos a nova instância em serviço e saudável para receber requisições.”

Ensaie antes: uma chamada leve pode não gerar CPU suficiente para disparar uma política baseada em CPU. Registre a carga, os horários, o motivo da atividade e o resultado. Se a espera for longa, corte o tempo morto e sinalize o corte, preservando a sequência real. Interrompa a carga ao terminar e confira a estabilização do ambiente.

**Alternativa limitada:** se só demonstrar mudança manual da capacidade desejada, diga “Esta ampliação foi solicitada manualmente; ela demonstra a criação de instâncias pelo ASG, mas não comprova o disparo automático da política.” Não apresente o resultado manual como automático.

### 5:35–6:25 — RDS

**Tela:** RDS → Databases → banco do projeto. Mostre Connectivity & security, subnet group e respectivas sub-redes/rotas; depois Configuration e informações de backup.

**Fala, se confirmado:** “O Argus usa PostgreSQL no RDS. O acesso público está desabilitado, e estas são as sub-redes do banco. O grupo de segurança permite acesso na porta 5432 a partir das origens autorizadas que aparecem aqui. Esta é a configuração de Multi-AZ e este é o período de retenção de backups.”

Se Multi-AZ estiver desativado, acrescente: “Nesta configuração o banco não tem standby Multi-AZ para failover; essa é uma limitação de disponibilidade.” Informe a justificativa apenas se tiver sido confirmada pelo grupo. `Publicly accessible: No` sozinho não comprova que a tabela de rotas da sub-rede é privada.

### 6:25–6:40 — Fechamento

**Fala, adaptada ao que foi efetivamente demonstrado:** “Mostramos a rede, os registros de operação, o acesso administrativo controlado, o balanceamento com escalonamento e o banco de dados. As configurações e limitações estão registradas no artefato de infraestrutura e integração.”

## Preparação e edição

1. Entre na região correta e deixe as telas do roteiro abertas antes de iniciar.
2. Confira os valores e ensaie as conexões; prepare a evidência de escalonamento com antecedência.
3. Use console em um único idioma, zoom legível e áudio de teste. Reserve os últimos 20 segundos da faixa permitida como margem.
4. Oculte credenciais, tokens, IDs de conta e os endpoints sensíveis previstos nas regras do projeto. Preserve os campos necessários à avaliação.
5. Assista ao arquivo exportado: cada afirmação precisa da tela correspondente, sem depender da narração para provar a existência do recurso.
6. Publique com acesso sem login, teste em janela anônima e coloque o link na seção 6 do artefato principal. Só marque como filmado ou pronto depois de concluir essas etapas.
