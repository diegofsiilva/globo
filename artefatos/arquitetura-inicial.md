# Arquitetura da Solução — Argus v3

&emsp; Este artefato detalha a arquitetura da plataforma de Monitoração Agêntica no seu
estado atual, batizado internamente de **Argus v3**: o diagrama de implantação dos
componentes na AWS, a descrição de cada nó e como eles se conectam, a justificativa
técnica das decisões de arquitetura e tecnologia adotadas, e o plano de deploy dos
recursos AWS envolvidos. O detalhamento de schema de banco, DDL completo e passo a
passo de migração vive em [`plano-argus-v3.md`](plano-argus-v3.md); este documento
referencia esse material onde apropriado, sem duplicá-lo, e foca no que a rubrica de
arquitetura pede: nós, conexões, justificativa e deploy.

&emsp; O sistema descrito aqui é o resultado de um pivot de escopo em relação ao MVP
original (ver [`mvp-inicial.md`](mvp-inicial.md)): em vez de um coletor próprio de
telemetria de frontend, a solução passou a ser um **consumidor de change data
capture (CDC)** das tabelas já tratadas pelo Argus — o correlator de incidentes já em
produção na Globo — mantendo-as replicadas e atualizadas na infraestrutura do projeto,
e derivando delas as camadas analíticas que alimentam o dashboard. A justificativa
completa dessa mudança de premissa está na seção 3.1.

---

## 1. Diagrama de implantação

&emsp; A Figura 1 mostra o diagrama de implantação do Argus v3, no padrão UML de nós
(estereótipo `«device»` para infraestrutura gerenciada como armazenamento, e
`«execution environment»` para ambientes que executam código próprio) e artefatos de
software (estereótipo `«artifact»`) hospedados dentro de cada nó. As setas indicam
caminhos de comunicação entre nós, rotuladas com o protocolo ou mecanismo usado. O nó
com borda tracejada laranja (`Amazon EventBridge Scheduler`) está marcado como
planejado: aparece no desenho original da arquitetura, mas ainda não existe como
recurso Terraform aplicado — ver a pendência registrada na seção 5.

<div align="center">

<sub>Figura 1 - Diagrama de implantação do Argus v3, com nós, artefatos de software e
caminhos de comunicação, no estado atual do Terraform em `apps/basica/infra/`</sub>

![Diagrama de implantação do Argus v3](assets/arquitetura-implantacao-v3.png)

<sup>Fonte: material produzido pelos autores (2026).</sup>

</div>

&emsp; O diagrama é organizado da esquerda para a direita seguindo o fluxo do dado: a
fonte (bucket S3 de origem) alimenta a carga inicial e o simulador; o simulador emite
change events por HTTPS para a camada de ingestão (API Gateway e SQS); dois serviços
ECS consomem essas filas e escrevem no RDS PostgreSQL, o nó central que hospeda as
quatro camadas do desenho medallion (bronze, silver, gold, detect); um serviço de
processamento roda o ETL incremental sobre esse banco; e a camada de consulta (Lambda
mais API Gateway) expõe as views a um dashboard estático servido via S3, acessado pelo
navegador do usuário. Uma faixa transversal na base do diagrama reúne os nós de
operação, segurança e observabilidade, comuns a todos os serviços acima.
