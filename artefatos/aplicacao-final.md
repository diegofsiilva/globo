# Aplicação final: sistema distribuído de telemetria

&emsp; Esta documentação apresenta a aplicação final Linceu, do grupo Vale a Pena Ver de Novo, desenvolvida no projeto com o Grupo Globo. A implementação, identificada no repositório como Argus, reúne ingestão de telemetria, processamento incremental e investigação de degradações de streaming. O documento concentra a arquitetura distribuída, a execução dos componentes em contêineres, a orquestração com Kubernetes e os mecanismos de recuperação frente a falhas.

## 1. Vídeo de apresentação da aplicação distribuída

**Vídeo de apresentação:** [ver vídeo](https://youtu.be/4U6GvE_Xhgw)

&emsp; A apresentação audiovisual complementa a documentação técnica com uma demonstração detalhada da aplicação distribuída. Seu escopo abrange os fluxos entre os componentes, a execução da API em Docker, a orquestração do frontend e do backend no Kubernetes, os serviços assíncronos no ECS Fargate e os mecanismos de recuperação após a perda de uma réplica. A consulta de dados históricos pela Timeline exemplifica o funcionamento integrado da interface, da API e da persistência na AWS.

## 2. Objetivo e funcionalidades

&emsp; A aplicação apoia a investigação de incidentes em uma cadeia de streaming monitorada por diferentes fontes. A proposta combina uma entrada padronizada para eventos com normalização, agregação e correlação temporal, permitindo consultar sinais e examinar hipóteses com suas evidências. O objetivo é reduzir a fragmentação da investigação entre player, CDN, backend e identidade.

&emsp; A ingestão recebe os seis tipos de evento do MVP: `request`, `screen_view`, `session`, `video_view`, `vitals` e `error`. Um segundo caminho recebe mudanças de registros de telemetria, representadas como eventos CDC. Ambos alimentam o PostgreSQL, mas possuem filas e consumidores próprios.

| Tela | Papel na investigação |
|---|---|
| Agora | Apresentação de sinais em desvio no período consultado. |
| Explorar | Exploração de métricas agregadas e consulta de eventos recentes de sessão. |
| Comparar | Comparação do volume de eventos com janelas de referência. |
| Hipóteses | Consulta de explicações candidatas, scores e evidências associadas. |
| Timeline | Reconstrução temporal dos sinais das fontes, com possibilidade de focar o instante de uma hipótese. |
| Recorte | Análise do escopo afetado por dimensões disponíveis nos dados. |

&emsp; As telas dependem dos dados disponíveis e da janela selecionada. Um recorte sem resultados representa uma consulta concluída sem registros elegíveis, enquanto erros de consulta possuem tratamento próprio. Hipóteses e scores apoiam a priorização da análise humana; não representam confirmação automática de causa raiz. As regras de domínio estão detalhadas no [artefato de hipóteses](./hipoteses.md).
