# Plano de correção da Sprint 4 (`fix/develop`)

Este plano separa a correção versionada da comprovação em nuvem. As evidências
de 17 a 24/09/2026 registram a execução anterior; elas não foram reclassificadas
como aprovadas pela mudança de código de 25/09.

| Parte | Problema observado | Correção versionada | Verificação e estado |
|---|---|---|---|
| Entrada e autenticação | O navegador acessava o ALB público por HTTP com Bearer. | API Gateway fornece HTTPS no domínio padrão, sem exigir domínio próprio. A Lambda de entrada encaminha ao ALB interno; o bucket S3 fica privado. | `terraform validate` e testes locais da Lambda aprovados. Aplicação e smoke test na AWS pendentes. |
| Recuperação de falhas | A troca para S3/API Lambda era manual e não ensaiada. | A entrada tenta o ALB e, diante de erro de rede ou 502/503/504, usa API de leitura Lambda para consultas ou export S3 na mesma URL. Escritas incertas não são repetidas automaticamente. | Testes locais de caminho principal, API de contingência, S3, escrita sem repetição e validação de host aprovados. Ensaio de indisponibilidade na AWS pendente. |
| Nós EKS | Em 24/09, nós receberam IP público e todas as réplicas da aplicação ficaram no mesmo nó. | O cluster recebe só sub-redes privadas. O overlay AWS exige hosts distintos para as duas réplicas mínimas de cada Deployment. | Teste Terraform e renderização do overlay aprovados. Conferência de nós e exercício de perda de nó na AWS pendentes. |
| Jobs de banco | O README descrevia um Job para migration e login, enquanto o cluster usa dois. | README e runbook descrevem a ordem real: `argus-db-migrate` e `argus-db-reader`. | Documentação conferida com Makefile e manifestos. |
| Integração TI-05.2 | A última execução AWS falhou em 17/09; a migration 030 foi validada só localmente. | O alvo `test-implantacao` falha se URLs ou tokens faltarem, impedindo aprovação por teste pulado. | Resultado AWS continua **reprovado/pendente de reexecução**. |
| Entrega | A tag `SPRINT4` não existia; o vídeo de contêineres já está acessível e mostra os itens exigidos. | Criar a tag na revisão corrigida, sem alterar o vídeo. | Tag local criada ao fechar a revisão; publicação remota ainda depende de `git push`. |

## Sequência de validação na próxima sessão do Learner Lab

1. Conferir a conta do profile `g4`, ajustar `existing_role_arn` no
   `terraform.tfvars` privado e revisar `make -C apps/fullstack tf-plan`.
2. Aplicar a infraestrutura e publicar o export estático privado com
   `make -C apps/fullstack frontend-deploy`.
3. Publicar o cluster e executar `make -C apps/fullstack k8s-edge-register`.
   Confirmar que `k8s-url` responde por HTTPS e que `/api` aceita apenas o
   Bearer de leitura.
4. Verificar que os nós não possuem IP público e que as réplicas de backend e
   frontend estão em hosts distintos. Executar um ensaio controlado de perda
   do Ingress e medir a troca para API Lambda/S3 pela mesma URL HTTPS.
5. Com os tokens no ambiente, executar `make -C apps/fullstack test-implantacao`
   e anexar a saída sanitizada ao relatório funcional. Só então atualizar o
   resultado do TI-05.2.
