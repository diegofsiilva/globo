# Arquitetura final da aplicação

## 1. Diagrama de implantação

> Inserir o diagrama de implantação da arquitetura distribuída, indicando os componentes, os ambientes de execução e as conexões entre eles.


### 1.1 Componentes e justificativas

> Listar os principais componentes do diagrama, suas responsabilidades, tecnologias utilizadas e justificativas para as escolhas arquiteturais.


## 2. Inventário de contêineres, Docker e Kubernetes


### 2.1 Dockerfiles

> Listar cada Dockerfile, o serviço ou imagem gerada, a finalidade do contêiner e o componente correspondente no diagrama.


### 2.2 Execução local

> Informar os arquivos usados para executar a aplicação localmente, incluindo sua finalidade e os serviços iniciados.


### 2.3 Orquestração e infraestrutura Terraform

> Listar os arquivos de orquestração e infraestrutura, os recursos declarados e a forma como eles implantam ou conectam os componentes da arquitetura.


## 3. Plano de recuperação de falhas

> Documentar as estratégias de recuperação da aplicação diante de falhas de serviços, contêineres, rede, banco de dados e infraestrutura.

### 3.1 Objetivos e níveis de severidade

> Informar os objetivos de recuperação, incluindo RTO, RPO, níveis de severidade, impacto esperado e responsáveis pelo acionamento.


### 3.2 Estratégias implementadas

> Descrever replicação de serviços, fallback automático, políticas de reinicialização, health checks, substituição de instâncias e rollback de versões.


### 3.3 Procedimento de resposta

> Descrever as etapas para detectar, conter, recuperar e validar a normalização após uma falha.


### 3.4 Limitações e decisões pendentes

> Registrar limitações conhecidas, dependências de configuração, riscos residuais e decisões arquiteturais ainda pendentes.


## 4. Evidências de validação

> Inserir evidências do diagrama, da execução dos contêineres, da infraestrutura implantada e dos testes de recuperação de falhas.

