/** Argus Sprint 05. Native PPTX and vector PDF from one reviewable scene graph.
 * No application credentials, partner raw data, network calls or npm install.
 * Usage: node generate.mjs --python PATH_TO_PYTHON [--out OUTPUT_DIRECTORY]
 */
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, '../..');
const arg = key => { const i=process.argv.indexOf(key); return i<0 ? null : process.argv[i+1]; };
const out = path.resolve(arg('--out') || here);
const build = path.join(root, '.codex/slides-build');
await fs.mkdir(build,{recursive:true});
await fs.mkdir(out,{recursive:true});
const C={bg:'0A0A0A',red:'FF1A00',deep:'820000',white:'FFFFFF',gray:'B9B9BE',line:'363638'};
const slides=[];
const money=(n,d=2)=>n.toLocaleString('pt-BR',{minimumFractionDigits:d,maximumFractionDigits:d});
const cost={hours:730,rds:62,cpu:0.0000089944*3600,gb:0.0000009889*3600};
cost.fargate=730*(1.5*cost.cpu+3*cost.gb);
cost.eks=730*.10;cost.nat=730*.045;cost.alb=730*.0225;cost.ipv4=730*.005*3;
cost.subtotal=cost.rds+cost.fargate+cost.eks+cost.nat+cost.alb+cost.ipv4;
cost.base=cost.subtotal+2*730*.05+30+10;
cost.expanded=cost.subtotal+4*730*.05+60+50;
const tco = (replacement,rollout,baseline=4064000)=>{
 const investment=1015000;
 const years=rollout.map(r=>({operation:282000+810000*r,residual:baseline*(1-replacement*r)}));
 const build=investment+years.reduce((sum,y)=>sum+y.operation+y.residual,0);
 return {baseline,investment,years,build,buy:baseline*3,saving:baseline*3-build};
};
const tcoBase=tco(.5,[.4,.8,1]);const tcoPessimistic=tco(.3,[.2,.4,.6]);
const sources={
 arch:'artefatos/arquitetura-final.md', tests:'artefatos/testes-funcionais.md',
 ingestion:'artefatos/testes-carga-inicial.md',business:'artefatos/entendimento_negocio.md',
 correlation:'artefatos/correlacao_dados.md', agent:'artefatos/arquitetura-agente-hipoteses-ia.md',
 files:'artefatos/plano-ingestao-arquivos.md', scoring:'apps/fullstack/processing/src/argus_processing/scoring.py',
 eks:'https://aws.amazon.com/eks/pricing/', nat:'https://aws.amazon.com/vpc/pricing/',
 ecs:'https://aws.amazon.com/fargate/pricing/', alb:'https://aws.amazon.com/elasticloadbalancing/pricing/'
};
function shape(s,type,x,y,w,h,fill=C.bg,stroke=null,sw=1){s.elements.push({type,x,y,w,h,fill,stroke,sw});}
function t(s,text,x,y,w,h,size=27,color=C.white,bold=false,align='left'){
 s.elements.push({type:'text',text,x,y,w,h,size,color,bold,align});
}
function line(s,x,y,w,color=C.line,sw=1){shape(s,'line',x,y,w,0,null,color,sw);}
function slide(title,refs,narration=''){
 const s={title,background:C.bg,elements:[],notes:narration+'\n\nFontes: '+refs.join('; ')};
 slides.push(s);shape(s,'rect',64,54,7,38,C.red);
 t(s,title,91,46,1105,96,42,C.white,true);
 line(s,64,663,1152);t(s,'ARGUS  /  G04',64,676,400,22,14,C.gray);
 t(s,String(slides.length).padStart(2,'0'),1185,675,31,25,16,C.gray,false,'right');return s;
}
function note(s,text){t(s,text,64,607,1152,45,19,C.gray);}
function cols(s,items,y=185){let w=340;items.forEach((a,i)=>{let x=64+i*406;t(s,a[0],x,y,w,65,33,C.red,true);t(s,a[1],x,y+86,w,230,26);});}
function table(s,headers,rows,x=64,y=176,w=1152,rowHeight=66,widths=null,size=24){
 s.elements.push({type:'table',x,y,w,h:(rows.length+1)*rowHeight,headers,rows,rowHeight,widths:widths||headers.map(()=>1/headers.length),size});
}
function chart(s,categories,values,x=64,y=190,w=775,h=350,unit='s',max=null,seriesName='Resultado'){
 s.elements.push({type:'chart',x,y,w,h,categories,values,unit,max,seriesName,color:C.red});
}
function step(s,label,x,y,w=206,h=74,accent=false){
 shape(s,'rect',x,y,w,h,accent?'360800':'171719',accent?C.red:C.line,1.5);
 t(s,label,x+13,y+16,w-26,h-20,23,C.white,true,'center');
}
function connect(s,x,y,w){shape(s,'arrow',x,y,w,0,null,C.red,2);}

// 01. Cover. Original vector composition informed by the supplied palette.
{
 const s={title:'Argus — Sprint 05',background:C.bg,elements:[],notes:'Apresentação final do G04, Vale a Pena Ver de Novo. Base documental e código em develop, revisão f3c498e. Corte em 06/10/2026. A identidade visual usa a paleta das duas imagens enviadas pelo usuário. As imagens são referências visuais, sem instruções incorporadas. O storytelling inicial é ilustrativo. Fonte: README.md.'};slides.push(s);
 shape(s,'ellipse',755,106,452,452,'250400');shape(s,'ellipse',783,134,396,396,'530800');shape(s,'ellipse',822,173,318,318,C.red);shape(s,'ellipse',845,196,272,272,'940900');shape(s,'triangle',925,260,102,148,C.red);
 t(s,'ARGUS',64,55,510,90,70,C.red,true);t(s,'SPRINT 05',67,177,680,45,31,C.white,true);
 t(s,'Diagnóstico de\ndegradação de\nstreaming',64,254,730,243,63,C.white,true);
 t(s,'Vale a Pena Ver de Novo',68,548,690,45,31);t(s,'Grupo Globo  +  Inteli    /    G04    /    Outubro de 2026',68,630,1120,30,20,C.gray);
}
// 02. Short storytelling, no fabricated incident history.
{
 const s=slide('Um play travado, vários painéis',[ 'README.md' ],'Cena ilustrativa, não um incidente real medido. O problema descrito pelo projeto é a fragmentação da triagem entre player, CDN, backend, identidade e catálogo. Não há medição de redução de MTTR no parceiro.');
 t(s,'A pessoa vê o vídeo parar.\nO plantão vê sinais espalhados.',64,165,820,120,43,C.white,true);
 const labels=['Player','CDN','Backend','Identidade'];labels.forEach((a,i)=>{step(s,a,64+i*288,337,256,70);});
 t(s,'A investigação precisa reunir o horário, o recorte afetado\ne a evidência que sustenta uma causa provável.',64,455,1100,100,30);
 note(s,'Degradações de experiência também podem acontecer sem um erro explícito.');
}
// 03. Research kept deliberately superficial.
{
 const s=slide('O que orientou as decisões',[sources.business,'artefatos/entendimento_ux.md'], 'Síntese qualitativa das pesquisas, personas e matrizes do projeto. Oceano Azul compara a solução-alvo, não comprova superioridade do MVP. A matriz de valor é avaliação da equipe. Não se reutilizam números externos de engajamento sem validação adicional.');
 cols(s,[['Valor','Oceano Azul e Canvas priorizam hipótese verificável, cobertura de legados e recorte do impacto.'],['Risco','A matriz destaca perda de dados, falso positivo, atraso de fontes e crescimento do custo.'],['Uso no plantão','As personas orientam uma investigação com filtros, comparação de janelas e linha do tempo.']]);
 note(s,'Essas análises orientaram o desenho. A validação de desempenho veio depois, nos ensaios.');
}
// 04.
{
 const s=slide('Perguntas que a solução responde',[sources.arch,sources.tests,sources.agent],'O motor determinístico e suas regras estão no código e têm testes. O fluxo completo de alta carga/frescor e o agente IA alternativo ainda não estão validados em produção. A apresentação trata o que foi resolvido total ou parcialmente, conforme a referência fornecida pelo usuário.');
 table(s,['Pergunta do plantão','Resposta do Argus','Alcance'],[
 ['Onde aparece a degradação?','Sinais, filtros e recortes do dashboard','Implementado'],
 ['O que mudou antes do efeito?','Timeline e comparação de janelas','Implementado'],
 ['Quais causas são plausíveis?','11 famílias e evidências ranqueadas','Motor testado'],
 ['Quais anomalias podem gerar incidentes?','Desvios do baseline e contexto','Sem garantia preditiva']
 ],64,173,1152,80,[.34,.46,.20],24);
 note(s,'A causa permanece candidata e exige revisão humana. O ganho no tempo de diagnóstico ainda precisa de medição.');
}
// 05.
{
 const s=slide('Arquitetura para uma investigação comum',[sources.arch,'README.md'],'Diagrama lógico editável. O pipeline de escrita segue no ECS Fargate e a leitura principal no EKS. Bronze guarda os eventos e as mudanças, Silver normaliza, Gold expõe produtos de leitura e hipóteses. Detect coordena checkpoints, baseline, runs e claims. O fluxo de arquivos da migration 034 aparece no próximo slide.');
 step(s,'Eventos de TV',64,189,240);step(s,'Mudanças CDC',64,299,240);
 step(s,'API Gateway',356,189,220);step(s,'SQS + workers',628,189,240);
 connect(s,304,226,52);connect(s,576,226,52);connect(s,868,226,58);
 step(s,'PostgreSQL',926,189,290,184,true);t(s,'Bronze  /  Silver\nGold  /  Detect',948,270,246,78,26,C.gray,false,'center');
 shape(s,'line',332,226,0,110,null,C.red,2);connect(s,304,336,28);
 step(s,'Dashboard',64,452,240);step(s,'ALB / Ingress',356,452,220);step(s,'API Flask no EKS',628,452,240);step(s,'Views de leitura',926,452,290);
 connect(s,304,489,52);connect(s,576,489,52);connect(s,868,489,58);
 shape(s,'line',1071,373,0,79,null,C.red,2);
 note(s,'Disponibilidade temporal: as views respeitam available_at ≤ sim.now().');
}
// 06.
{
 const s=slide('Três caminhos de ingestão',[ 'README.md',sources.files,'apps/fullstack/worker/README.md'],'Eventos de TV têm seis tipos: request, screen_view, session, video_view, vitals, error. Mudanças simuladas usam change_log e MERGE corrente na mesma transação. Os arquivos CSV/Parquet usam fila PostgreSQL ingest.file_job, separada do SQS. A carga histórica Parquet via loader/COPY é bootstrap e não equivale ao upload de arquivos. O README de worker indica que o envio usa a sessão existente do painel, corrigindo a expressão antiga de credencial independente no plano.');
 table(s,['Origem','Caminho de escrita','Garantia principal'],[
 ['Eventos de TV','Gateway, SQS, event worker, bronze.event','Validação e deduplicação'],
 ['CDC simulado','Gateway, SQS, merge worker, change_log','Log + MERGE transacional'],
 ['CSV / Parquet','File API, fila no Postgres, file worker','Lease, fencing e rollback']
 ],64,184,1152,86,[.22,.49,.29],25);
 t(s,'O loader prepara a base histórica via COPY antes da ingestão incremental.',64,550,1152,38,28);
 note(s,'Upload de arquivos: implementação e testes locais. A publicação na AWS ainda está pendente.');
}
// 07.
{
 const s=slide('Python no MVP, Go como alternativa',[ 'apps/fullstack/backend/pyproject.toml','apps/fullstack/processing/pyproject.toml','https://go.dev/doc/effective_go','https://docs.python.org/3/library/threading.html'],'A implementação observada usa Python para backend, workers, ETL e regras. Flask, psycopg e Pydantic são dependências existentes. Go é uma alternativa técnica, não um componente implementado. Goroutines e channels são documentados em Effective Go. Em CPython com GIL, threads são úteis para I/O, mas limitadas para bytecode CPU-bound. A adequação ao projeto é avaliação de engenharia, não resultado de benchmark Go versus Python. Não há comparação controlada de custo, memória ou vazão entre as linguagens no repositório.');
 table(s,['Critério','Python, implementação atual','Go, alternativa'],[
 ['Integração','Reutiliza contratos, ETL e regras existentes','Exige portar contratos e testes'],
 ['Concorrência','Processos do gunicorn e espera de I/O','Goroutines e channels'],
 ['Evolução do motor','Regras e análise no mesmo ecossistema','Serviço dedicado possível'],
 ['Decisão do projeto','Preservar o MVP e medir o gargalo','Avaliar com o mesmo ensaio']
 ],64,172,1152,79,[.23,.42,.35],24);
 note(s,'Não há benchmark Go versus Python no projeto. Os gargalos observados não justificam, sozinhos, uma reescrita.');
}
// 08.
{
 const s=slide('Hipóteses com evidência e contradição',[sources.correlation,sources.scoring,'apps/fullstack/processing/src/argus_processing/rules.py'],'O cenário desenhado é ilustrativo. As 11 famílias são regras determinísticas. O código usa A anomalia 25%, T proximidade temporal 20%, C corroboração 20%, E especificidade 15%, I impacto 15%, Q qualidade 5%. O cálculo normaliza só pelos pesos disponíveis, retira not_applicable do denominador de cobertura e subtrai 30X. Confiança alta: score≥80, coverage≥0,80, Q≥0,70 e contradiction<0,5. Confiança média: score≥60, coverage≥0,60 e contradiction<0,8. O score não é probabilidade de causa.');
 const labels=['Checkpoint','Fatos e baseline','Desvios','11 famílias'];labels.forEach((a,i)=>{step(s,a,64+i*293,194,256,78,i===3);if(i<3)connect(s,320+i*293,233,37);});
 t(s,'Exemplo ilustrativo',64,315,600,35,22,C.red,true);
 t(s,'Um deploy precede o aumento de erros.\nOutra fonte corrobora o desvio.\nUma evidência contrária reduz a confiança.',64,366,760,139,32);
 t(s,'Score e cobertura',895,364,321,54,31,C.red,true);t(s,'Evidências disponíveis\nnormalizam o score.\nContradições reduzem\na confiança.',895,432,310,132,25);
 note(s,'Correlação temporal sustenta uma candidata. A confirmação da causa continua humana.');
}
// 09.
{
 const s=slide('Motor, refinador e agente de investigação',[sources.agent,'apps/fullstack/backend/src/telemetry/infrastructure/ollama.py','apps/fullstack/backend/src/telemetry/config.py'],'Três escopos distintos. O motor atual é especialista determinístico. O refinador Ollama recebe hipóteses publicadas e valida as referências em resposta estruturada, sem gerar o score e sem participar da ingestão. Sua integração não foi validada no EKS. O agente alternativo é documento de MVA, experimental e não publicado: consulta fatos do checkpoint sem rótulos, scores e hipóteses atuais como entrada. O modelo/provedor do agente ainda não foi escolhido. OLLAMA_MODEL vazio escolhe o primeiro modelo instalado via /api/tags. Logo, não há modelo fixo comprovado para informar.');
 cols(s,[['Motor atual','11 famílias determinísticas. Score explicável, cobertura e evidências. Implementado e testado.'],['Ollama opcional','Refina o texto de uma hipótese publicada. Resposta com fontes. Sem validação no EKS.'],['Agente proposto','Investiga fatos de um checkpoint e procura contradições. MVA experimental ainda não publicado.']]);
 note(s,'LLM: configurável em OLLAMA_MODEL. O repositório não comprova um modelo específico em execução.');
}
// 10.
{
 const s=slide('MVP: o recorte da degradação',[ 'artefatos/assets/captura_agora_tema_escuro.png','artefatos/frontend.md'],'Captura histórica versionada da tela Agora. Serve para mostrar a interface, não provar incidente real, ganho de MTTR nem validar todas as rotas atuais. O clock da simulação e os filtros ajudam a contextualizar os desvios. Não editar métricas da captura.');
 s.elements.push({type:'image',path:'artefatos/assets/captura_agora_tema_escuro.png',x:64,y:157,w:888,h:506});
 t(s,'Uma janela\nde investigação',925,214,291,114,31,C.red,true);t(s,'Filtros do recorte\n\nDesvio do baseline\n\nAcesso às hipóteses',925,357,291,213,25);
 // Image touches the divider intentionally; move it above the footer.
 s.elements.at(-3).h=432;s.elements.at(-3).w=758;s.elements.at(-3).x=64;s.elements.at(-3).y=165;
 t(s,'Captura histórica da interface',64,612,900,29,19,C.gray);
}
// 11.
{
 const s=slide('MVP: upload de CSV e Parquet',[sources.files,'apps/fullstack/worker/README.md'],'Estado de 05/10/2026. Frontend: 92 testes em 16 arquivos, lint e build. Worker: 125 testes com Postgres real, excluindo um teste POSIX/SIGTERM no Windows. A verificação visual usou fronteira HTTP simulada, e a persistência real foi exercitada pelos testes Python. Não houve publicação AWS, nem execução final dos novos Deployments. Limites de 50MiB, 100.000 registros e 64 colunas. Campos obrigatórios timestamp, event_name, session_id e device_id. Os arquivos não importam genericamente as tabelas CDC.');
 ['Prévia','Mapeamento','Envio original','Protocolo'].forEach((a,i)=>{step(s,a,64+i*293,185,256,73,i===3);if(i<3)connect(s,320+i*293,221,37);});
 t(s,'O servidor valida o arquivo completo e informa\ninseridos, duplicados e rejeitados.',64,304,1140,92,35,C.white,true);
 t(s,'92',64,443,210,84,69,C.red,true);t(s,'testes frontend',64,531,280,42,25);
 t(s,'125',468,443,260,84,69,C.red,true);t(s,'testes worker com Postgres',468,531,395,42,25);
 t(s,'50 MiB',895,443,320,79,59,C.red,true);t(s,'limite por arquivo',895,531,310,42,25);
 note(s,'Evidências locais de 05/10. A imagem final e os novos Deployments ainda precisam de execução.');
}
// 12.
{
 const s=slide('Implantação híbrida na AWS',[sources.arch,'artefatos/conteineres-final.md'],'EKS Auto Mode para API Flask/gunicorn e frontend nginx/Next.js estático. ECS Fargate para event/merge workers, simulator e processing, além da task loader. A restrição do Learner Lab a IRSA/Pod Identity motivou preservar as tasks IAM no ECS. O ALB nasce do Ingress. Terraform cria infraestrutura, Kustomize define overlays e Job aplica migrations. Observado em setembro: banco Single-AZ, um NAT, pods co-localizados e nós em sub-redes públicas. Arquivos novos têm manifests mas não publicação AWS comprovada.');
 cols(s,[['EKS Auto Mode','API de leitura e frontend. Deployments, probes, HPA, PDB e Ingress com ALB.'],['ECS Fargate','Ingestão e processamento assíncronos. IAM por task para acesso a filas e armazenamento.'],['PostgreSQL 16','Camadas compartilhadas. Views com controle temporal e usuário de leitura restrito.']]);
 note(s,'Terraform + Kustomize + Job de migrations. Single-AZ, NAT único e distribuição dos pods limitam a disponibilidade.');
}
// 13.
{
 const s=slide('Condições de teste e alcance',[sources.tests,sources.ingestion,sources.files,sources.arch],'Não são testes executados nesta tarefa. São evidências versionadas. k6 carga de ingestão 02/09 e lotes09/09, reexecução11/09. Dashboard EKS21/09 e24/09, com geradores distintos. Resiliência24/09 em kind de um nó. Arquivos05/10 testes locais com sintéticos e PostgreSQL real. Não transformar evidência sintética em validação de operação real do parceiro.');
 table(s,['Ensaio','Ambiente e carga','O que comprova'],[
 ['Ingestão','AWS, k6, 150 mil a 600 mil eventos','Aceite, drenagem, contagem'],
 ['Dashboard','EKS, 5 / 25 / 100 VUs, 6 min','Latência e limiares por tela'],
 ['Resiliência','kind, 1 nó, k6 com 5 VUs','Pods, probes e rollback'],
 ['Arquivos','Local, dados sintéticos e Postgres','Contrato, dedup e transação']
 ],64,169,1152,82,[.21,.45,.34],24);
 note(s,'Dados de simulação e ensaios controlados. Nenhuma rodada demonstra MTTR menor em produção do parceiro.');
}
// 14.
{
 const s=slide('Ingestão: quatro lotes em 5 min 46 s',[sources.ingestion,'artefatos/assets/performance/evidencias-lotes-2026-09-09.json'],'Resultados de09/09. Um lote150.000: drenagem120s; dois300.000:191s; três450.000:259s; quatro600.000:346s. Critério450s. Total1.500.000 eventos reconciliados por ItemsWritten, DLQ0. Drenagem é fila até zero, não chegada à Gold/API. A contagem agregada não substitui reconciliação por identificador e análise de duplicidades. O histórico inclui reexecução posterior com89s para um lote, mas não se misturam rodadas no gráfico.');
 chart(s,['150 mil','300 mil','450 mil','600 mil'],[120,191,259,346],64,185,770,365,'s',450,'Tempo de drenagem');
 t(s,'1,5 milhão',885,195,331,74,48,C.red,true);t(s,'eventos reconciliados\nna rodada de 09/09',885,290,331,85,26);
 t(s,'104 s',885,414,331,70,58,C.white,true);t(s,'de margem no pior lote\npara o limite de 450 s',885,501,331,75,25);
 note(s,'Zero erro no aceite e DLQ zerada. A fila drenada ainda não garante frescor na consulta.');
}
// 15.
{
 const s=slide('Dashboard: 100 usuários, p95 de 841 ms',[sources.tests,'artefatos/evidencias/carga-kubernetes-2026-09-24/carga-ui_resultado_20260925T004042Z.json'],'Rodada24/09, EKS Auto Mode1.33, metrics-server ativo, k6 na máquina do desenvolvedor fora da VPC. 962+4.764+18.450=24.176 requisições conforme os níveis do JSON. O parágrafo do relatório diz24.177, discrepância de1 que não afeta a latência, registrada sem repetir a soma divergente. Todos os níveis e limiares por tela passaram, 0erros, 100% telas completas. p95 requisição260,304,841ms; tela410,490,969ms. HPA ScalingActive=True/ValidMetricFound, mas sem SuccessfulRescale porqueCPU abaixo60%.');
 chart(s,['5 VUs','25 VUs','100 VUs'],[260,304,841],64,185,760,360,'ms',1000,'p95 das requisições');
 t(s,'0%',892,199,320,97,80,C.red,true);t(s,'erros nos três níveis',892,309,320,73,27);
 t(s,'969 ms',892,426,320,68,51,C.white,true);t(s,'p95 da abertura de tela\nno nível de 100 usuários',892,510,320,73,25);
 note(s,'24/09, gerador fora da VPC. HPA com métrica válida, sem aumento de réplicas observado.');
}
// 16.
{
 const s=slide('A saturação revelou o limite do ensaio',[sources.tests,'artefatos/evidencias/carga-kubernetes/rodada-b-resultado.json'],'Rodada21/09 distinta da rodada24/09. metrics-server ausente, HPA sem métricas, duas réplicas fixas.200VUs reprovado nos critérios por tela mesmo semerroHTTP.450VUs15,21% erros.900VUs24,80% erros e timeout30s. Maior nível observado aprovado100, primeiroreprovado200: intervalo experimental, não teto exato. CPU RDS chegou86%, e dois pods reiniciaram duas vezes cada. A inferência documentada é gargalo de aplicação nesta rodada; não causa exclusiva definitiva nem prova de ganho com linguagem diferente.');
 table(s,['Usuários','p95 das requisições','Erros','Critérios por tela'],[
 ['200','2.766 ms','0%','Reprovado'],['450','9.486 ms','15,21%','Reprovado'],['900','30.001 ms','24,80%','Reprovado']
 ],64,181,1152,86,[.18,.33,.20,.29],28);
 t(s,'Entre 100 e 200 usuários no ensaio com duas réplicas',64,544,1138,52,30,C.red,true);
 note(s,'21/09: HPA sem metrics-server. A rodada de 24/09 corrigiu as métricas, mas não repetiu a saturação.');
}
// 17.
{
 const s=slide('Resiliência: a segunda réplica fez diferença',[sources.arch],'Ensaios24/09 no kind local,1nó,5VUs, mesmomanifesto sem topologiaEKS. Reposição uma réplica14,3%503 e8,3sReady, duas réplicas0falhas e6,2s. Rollback imagem inexistente detectada17,1s, undo3,0s, antigasReady. Perda de banco: readinessFalse29,8s,RESTARTS0 e health/live200, mas recuperação exigiu migrations porque bancoemptyDir voltou vazio. Não prova failoverRDS nem recuperaçãodeAZ.');
 table(s,['Falha controlada','Resultado observado','Leitura'],[
 ['Excluir pod, 1 réplica','8,3 s até Ready, 14,3% de falhas','Sem capacidade reserva'],
 ['Excluir pod, 2 réplicas','6,2 s até Ready, zero falhas','Outra réplica atende'],
 ['Imagem inexistente','Pods antigos atendem, undo em 3 s','Rollback manual'],
 ['Banco indisponível','Readiness retira pod, zero reinício','Dependência isolada']
 ],64,177,1152,79,[.27,.42,.31],24);
 note(s,'kind local, um nó, 24/09. Recuperação de nós, zonas e RDS na AWS ainda precisa de ensaio.');
}
// 18.
{
 const s=slide('Gargalos que ainda limitam a solução',[sources.ingestion,sources.arch,sources.tests],'Frescor: após correção manual do watermark, o últimoevento do lote150.000 apareceuAPI38min32s depois doenvio. Amostraúnica, não p95. Um diagnóstico distinto100eventosmediu p95bronze1,785s. Backloghistórico deLSNnafrentedoeventoexplicou atrasoETL. Prioridadesdesenho: separar watermarkbootstrap/incremental, medir distribuiçãocompletap95 por test_id, repetir carga e reconciliação porIDs. HPA métricas corrigidas, escala ainda pendenteEKS. Pods co-localizados, bancoSingleAZ eNATúnico tornam disponibilidade limitada.');
 t(s,'38 min 32 s',64,173,650,94,72,C.red,true);t(s,'até o último evento aparecer na API\nAmostra única de um lote de 150 mil',64,288,768,89,29);
 line(s,64,415,1152);cols(s,[['Frescor','Separar o bootstrap histórico do watermark incremental e medir o p95 completo.'],['Capacidade','Repetir a saturação com HPA ativo e observar aumento real de réplicas.'],['Disponibilidade','Distribuir pods e nós. Ensaiar RDS, perda de nó e recuperação na AWS.']],444);
 // Shorter body boxes on this slide to reserve the footer.
 for(const e of s.elements){if(e.type==='text' && e.y===530){e.h=113;e.size=23;}if(e.type==='text'&&e.y===444){e.size=28;e.h=45;}}
}
// 19.
{
 const s=slide('Custo: US$ 106 não cobre o desenho atual',[sources.eks,sources.nat,sources.ecs,sources.alb,'apps/fullstack/infra/README.md','apps/fullstack/infra/variables.tf'],'Modelo de orçamento, não fatura. us-east-1,730h/mês, semfree-tier/créditos/impostos/descontos. RDS62USDéestimativa históricadorepo, não cotação atual. Fargate4servicesARM: doisworkers0,25CPU0,5GB e simulator/processing0,5CPU1GB, total1,5vCPU3GB. Taxas oficiaisARM0,0000089944USDvCPU/s e0,0000009889USDGB/s. EKS0,10/h em suporte padrão. NAT0,045/h sembytes. ALB0,0225/h semLCU. IPv4mínimo3:1NAT+2ALB,0,005/h. Subtotal não é valor mínimo garantido, pois inclui estimativaRDS e não inventaria recursos da conta. FontesAWS consultadas06/10/2026.');
 table(s,['Componente','Premissa mensal','US$ / mês'],[
 ['RDS + 100 GB','Estimativa histórica do repositório',money(cost.rds)],
 ['Fargate ARM','1,5 vCPU + 3 GB, 730 h',money(cost.fargate)],
 ['EKS, plano de controle','Suporte padrão, US$ 0,10/h',money(cost.eks)],
 ['NAT + ALB + IPv4','Horas e 3 IPv4, sem uso variável',money(cost.nat+cost.alb+cost.ipv4)],
 ['Subtotal parcial','Nós EKS e tráfego ainda por somar',money(cost.subtotal)]
 ],64,167,1152,73,[.31,.48,.21],24);
 note(s,'Estimativa para 730 h em us-east-1. Inclui uma premissa histórica de RDS e exclui créditos e impostos.');
}
// 20.
{
 const s=slide('Orçamento ampliado e sensibilidade',[sources.eks,sources.nat,sources.alb,'apps/fullstack/infra/variables.tf'],'Premissas explícitas, não preçoscotados: nósEC2+AutoMode orçadosa0,05USD/nó-h, tipodenóe taxa realaindaaverificar. Cenário base2nós,73USD; cenário ampliado4nós146USD. ReservaparaEBS/S3/ECR/bastion/backups/CloudWatch/Lambda/SQS/API30ou60USD. ReservaparaLCU,NATbytes,transferência10ou50USD. O orçamentoagrupa variáveisdeconsumo, não resulta emcertificação dequeacomportará1Mou10Meventos. NovoNAT+IPv4 adiciona730*(0,045+0,005)=36,50USD/mês antesdotráfego. MultiazdeRDS exige cotação àparte. EKSsuporteestendido troca73por438,delta365USD/mês. LLMexterno,equipeeimpostosnãoincluídos.');
 table(s,['Item','Base, 2 nós','Ampliado, 4 nós'],[
 ['Subtotal parcial',money(cost.subtotal),money(cost.subtotal)],
 ['Nós EKS + Auto Mode, premissa',money(2*730*.05),money(4*730*.05)],
 ['Reserva de serviços auxiliares','30,00','60,00'],['Reserva de uso variável','10,00','50,00'],
 ['Orçamento mensal, US$',money(cost.base),money(cost.expanded)]
 ],64,165,1152,73,[.52,.24,.24],24);
 note(s,'Nós: provisão de US$ 0,05 por nó-hora, ainda a cotar. Segundo NAT + IPv4: +US$ 36,50/mês, antes do tráfego.');
}
// 21.
{
 const s=slide('Custo por evento e valor operacional',[sources.eks,sources.nat,sources.alb,sources.business],'Métricas condicionais; não benchmarkdecapacidade. Com custofixoestimadobase351,48USDevolume1Meventos,milhõesconsumidos1:351,48USD/M.10Meventosmesmoorçamento:35,15USD/M, pressupostoquenãohavercusto/capacidadeextra, nãocomprovado. Usar eventosválidospersistidos, nãoHTTP202. Retenção:10Meventos/mês,1kBdecimallógicoporevento=10GBpor30dias,30GBpor90diasantesdeíndices,WAL,rés/camadas. Horasdiagnóstico do modelolegadonoportunidade:3engenheiros*6h*4incidentes/mês*12*0,35=302,4h/ano, não redução observada. Em mercado hipotético190BRL/h=57.456BRL/ano, não somado ao TCO para evitar dupla contagem. Fórmula custoLLMservidorh*USDh/amostraseoupreçoportokens, nenhum modelo/taxa fixos comprovados.');
 t(s,'US$ '+money(cost.base),64,174,640,80,61,C.red,true);t(s,'por milhão, se o mês tiver 1 milhão\nde eventos válidos persistidos',64,270,762,90,29);
 t(s,'US$ '+money(cost.base/10),887,174,325,80,51,C.white,true);t(s,'por milhão com 10 milhões\ne o mesmo orçamento',887,276,325,115,27);
 line(s,64,423,1152);t(s,'Retenção',64,454,285,45,30,C.red,true);t(s,'10 milhões × 1 kB = 10 GB/mês\n90 dias = 30 GB, antes de índices e WAL',64,515,770,88,26);
 t(s,'302 h/ano',887,452,330,60,45,C.white,true);t(s,'potencial de economia de plantão\nHipótese: redução de 35%',887,518,324,84,23);
 note(s,'Capacidade para 10 milhões/mês e economia de plantão são hipóteses. LLM, pessoal e impostos ficam fora do orçamento cloud.');
}
// 22.
{
 const s=slide('TCO: a viabilidade depende da adoção',[sources.business],'Reapresentação condicional do modelofinanceiroacadêmicodoseção4.6, nãovalidaçãodomercado nemnovacotação. Baselineassumido4.064.000BRL/ano, substituição50%, rollout40%-80%-100%; investimento1.015.000. Operação282.000+810.000*rollout. Contratoresidualbaseline*(1-.5*rollout). Recalcularvaloresexatos, não somar tabelasarredondadas. Ano1build1.015.000+606.000+3.251.200=4.872.200; ano2build930.000+2.438.400=3.368.400;ano3build1.092.000+2.032.000=3.124.000,total11.364.600. Buy12.192.000, diferença827.400. Economia6,786%=6,8%. Primeiroano808.200maiscaro. Crossover24+112.600/940.000*12=25,44meses, comfluxolinearnoterceiroano. Cenáriopessimista30%substituição,20-40-60%rollout:build13.563.880,perda1.371.880. Baseline300milUSD*5,08BRL=1.524.000;mesmabasebuild6.284.600,buy4.572.000,build1.712.600maiscaro, diferente do número1.967.000dodocumento. Não incluir essevalor divergente no slide, registrar emREADME. Câmbio5,08éapenasparâmetroantigodomodelo,nãocotaçãoatual. Não extrapolarcloudlaboratórioparabilhõeseventos.');
 table(s,['TCO em 3 anos, R$ milhões','Base acadêmica','Cenário pessimista'],[
 ['Manter o contrato assumido',money(tcoBase.buy/1e6,3),money(tcoPessimistic.buy/1e6,3)],
 ['Construir + operar + residual',money(tcoBase.build/1e6,3),money(tcoPessimistic.build/1e6,3)],
 ['Economia estimada',money(tcoBase.saving/1e6,3),money(tcoPessimistic.saving/1e6,3)]
 ],64,176,1152,87,[.50,.25,.25],27);
 t(s,'6,8%',64,530,218,65,52,C.red,true);t(s,'economia no cenário base\nVirada acumulada perto do mês 25',310,524,903,72,29);
 note(s,'Premissas sem validação do parceiro: contrato de R$ 4,064 mi/ano, substituição de 50% e rollout de 40% / 80% / 100%.');
}
// 23.
{
 const s=slide('Conclusão: MVP funcional, evolução condicionada',[sources.arch,sources.tests,sources.files,sources.business],'Conclusão baseada noescopoevidenciado. IngestãoeconsultatêmensaiosAWS. Motordeterminísticotemtestes. Arquivosvalidadoslocalmente, nãoAWS. Agentealternativoaindaproposto, nãoautomaçãoatualdecausaraiz. Critérioevolução: distribuiçãocompleta p95frescor/reconciliaçãoIDs,SuccessfulRescaleEKSsobcarga,testesrestoreRDS/falhanó,contratocustovalidados. Não concluir produção pronta ouROI garantido.');
 t(s,'O Argus reúne sinais e apresenta\ncausas candidatas verificáveis.',64,166,1120,120,43,C.white,true);
 t(s,'Comprovado',64,344,380,46,32,C.red,true);t(s,'Ingestão e leitura sob carga\nMotor determinístico testado\nUpload validado localmente',64,408,510,148,28);
 t(s,'Próximo aceite',680,344,500,46,32,C.red,true);t(s,'Frescor medido ponta a ponta\nEscala e recuperação na AWS\nCusto e valor com dados do parceiro',680,408,532,148,28);
 note(s,'O piloto deve medir tempo até hipótese útil, evidência correta e custo por evento persistido.');
}
// 24.
{
 const s={title:'Obrigado',background:C.bg,elements:[],notes:'Encerramento da apresentação. O slide25 reúne rastreabilidade para consulta na discussão. Referências visuais: imagens fornecidas pelo usuário. Créditos da equipe: README.md.'};slides.push(s);
 shape(s,'ellipse',820,127,364,364,'440600');shape(s,'ellipse',850,157,304,304,C.red);shape(s,'ellipse',887,194,230,230,'720600');shape(s,'triangle',965,250,70,111,C.red);
 t(s,'ARGUS',64,57,600,88,66,C.red,true);t(s,'OBRIGADO!',64,264,1160,144,110,C.white,true);
 t(s,'Vale a Pena Ver de Novo',69,490,1100,61,37);t(s,'G04    /    Grupo Globo + Inteli',69,613,1100,40,24,C.gray);
}
// 25. Evidence appendix.
{
 const s=slide('Apêndice: rastreabilidade dos resultados',[sources.arch,sources.tests,sources.ingestion,sources.files,sources.business],'Todo o material é derivado do estadoobserváveldoprojeno desenvolvimento. Fontesinternasfixadosemcommitf3c498e, corte06/10/2026. Evidênciasmedidas são de setembroeoutubro, não uma execuçãointegralnova. FontesexternasdepreçosAWSconsultadas06/10/2026. Os arquivosdiretamentedisponíveisnofolderincluemroteirofonte, notas, custoCSV eREADME. Os recursosnativechartetablePPTXpermitemeditar; ascreenshotUIéimagem original.');
 table(s,['Tema','Documento no repositório'],[
 ['Arquitetura e recuperação','artefatos/arquitetura-final.md'],['Carga e Kubernetes','artefatos/testes-funcionais.md'],['Lotes e frescor','artefatos/testes-carga-inicial.md'],['Upload, corte 05/10','artefatos/plano-ingestao-arquivos.md'],['Premissas de TCO','artefatos/entendimento_negocio.md']
 ],64,166,1152,71,[.34,.66],25);
 note(s,'Preços oficiais AWS e fontes por slide nas notas. Corte do projeto: 06/10/2026, base f3c498e.');
}

// Speaker notes: explain the claim and its limits in readable prose.
const narrations={
 5:'O diagrama mostra o caminho lógico de escrita e consulta. Gateway e SQS desacoplam os clientes dos consumidores. Os workers gravam Bronze, o processamento constrói Silver e Gold, e o EKS serve a leitura. O controle temporal impede acesso a informações que ainda não estariam disponíveis no presente simulado. A camada Detect coordena execuções, checkpoints, baseline e claims.',
 6:'O fluxo de TV recebe request, screen_view, session, video_view, vitals e error. O fluxo CDC registra a mudança e atualiza a tabela corrente na mesma transação. CSV e Parquet entram por um serviço próprio e usam ingest.file_job no PostgreSQL, sem SQS. Essa importação aceita o envelope de eventos da TV, e não qualquer tabela CDC. A carga inicial via loader/COPY é um bootstrap separado. O README atual do worker esclarece que o envio usa a sessão existente do painel.',
 8:'O exemplo é ilustrativo. As regras produzem candidatas, não causas confirmadas. O código pondera A, anomalia (25%), T, proximidade temporal (20%), C, corroboração (20%), E, especificidade (15%), I, impacto (15%) e Q, qualidade (5%). Normaliza o score pelos pesos disponíveis e aplica uma penalidade de 30 × X por contradição. Features ausentes reduzem a cobertura. Confiança alta exige score ≥ 80, cobertura ≥ 0,80, Q ≥ 0,70 e contradição < 0,5. Confiança média exige score ≥ 60, cobertura ≥ 0,60 e contradição < 0,8. Score não é probabilidade.',
 9:'O motor atual é determinístico. O refinador Ollama recebe uma hipótese publicada, produz texto estruturado e valida as referências citadas. Não participa do cálculo de score nem da ingestão. Sua integração no EKS ainda não foi validada. O agente alternativo é uma proposta de MVA: investiga fatos de um checkpoint sem receber rótulos, scores ou hipóteses do motor atual. Modelo e provedor desse agente ainda estão em aberto. OLLAMA_MODEL é configurável e, quando vazio, o cliente consulta /api/tags e usa o primeiro modelo instalado. Não há evidência de um modelo específico em execução.',
 11:'A finalização documentada em 05/10 registra 92 testes de frontend em 16 arquivos e 125 testes de worker com PostgreSQL real. Um teste legado de SIGTERM, com semântica POSIX, ficou fora da execução Windows. A revisão visual simulou a fronteira HTTP, enquanto os testes Python verificaram a persistência real. Os limites são 50 MiB, 100 mil registros e 64 colunas. Não houve publicação AWS, e a imagem final com a sonda ajustada e os novos Deployments ainda não foram executados.',
 13:'A apresentação reúne ensaios já registrados no repositório, sem afirmar uma nova execução integral. A ingestão foi medida na AWS em setembro. O dashboard teve rodadas no EKS em 21 e 24/09 com geradores em locais diferentes. A resiliência foi ensaiada no kind de um nó. Os testes de arquivos são locais e usam dados sintéticos e PostgreSQL real. Esses ambientes não demonstram redução do tempo de diagnóstico na operação do parceiro.',
 14:'Na rodada de 09/09, a drenagem foi de 120, 191, 259 e 346 segundos para 150, 300, 450 e 600 mil eventos. O critério era 450 segundos. A soma foi de 1,5 milhão de eventos reconciliados por ItemsWritten, com DLQ zerada. O gráfico compara apenas essa rodada. Uma reexecução posterior registrou 89 segundos para um lote. Fila drenada não significa evento disponível na API. Contagens agregadas também não substituem conferência por ID e por duplicidade.',
 15:'Em 24/09, o EKS Auto Mode 1.33 tinha metrics-server ativo. O k6 rodou na máquina do desenvolvedor, fora da VPC, portanto a latência de rede participa do resultado. Os níveis de 5, 25 e 100 usuários tiveram p95 de requisição de 260, 304 e 841 ms, respectivamente. O p95 da abertura de tela foi de 410, 490 e 969 ms. Todos os critérios por tela passaram, com zero erro e 100% de telas completas. O HPA registrou ScalingActive=True e ValidMetricFound, mas não ocorreu SuccessfulRescale. O total agregado do JSON é 24.177, enquanto os três níveis somam 24.176. O slide evita usar esse total como evidência de reconciliação.',
 16:'A saturação de 21/09 é uma rodada distinta. Sem metrics-server, o HPA não tinha métricas e o backend permaneceu com duas réplicas. O nível de 200 usuários reprovou nos critérios das telas Agora e Recorte, apesar de zero erro HTTP. Os níveis de 450 e 900 usuários tiveram 15,21% e 24,80% de erros. O maior nível aprovado foi 100 e o primeiro reprovado foi 200, o que apenas delimita o intervalo experimental. O RDS chegou a 86% de CPU e os pods reiniciaram sob saturação. A repetição de 24/09 validou as métricas do HPA, mas não repetiu o teto de carga.',
 17:'Os ensaios ocorreram no kind local em 24/09, com um nó e k6 a 5 usuários. Com uma réplica, a exclusão do pod gerou 14,3% de falhas e a recomposição levou 8,3 segundos. Com duas réplicas, o novo pod ficou Ready em 6,2 segundos e não houve falhas. Na imagem inexistente, os pods antigos continuaram atendendo e o rollback manual levou 3 segundos. A indisponibilidade do banco retirou o backend do balanceamento sem reinício. Como o banco usava emptyDir, a recuperação exigiu reaplicar migrations. Isso não comprova failover do RDS ou recuperação entre zonas.',
 18:'Depois de uma intervenção manual no watermark, o último evento do lote de 150 mil apareceu na API 38 minutos e 32 segundos após o envio. Esse tempo é uma amostra única, não p95. Um lote diagnóstico separado, de 100 eventos, mediu p95 de persistência em Bronze de 1,785 segundo. O relatório localiza o atraso no processamento incremental e no backlog histórico que compartilha o contador LSN. A evolução exige separar os watermarks, medir a distribuição completa de frescor e reconciliar IDs. Escala efetiva no EKS e disponibilidade entre nós ainda precisam de ensaio.',
 19:'O orçamento usa us-east-1 e 730 horas por mês, sem impostos, créditos, free tier ou descontos. RDS + 100 GB mantém uma estimativa histórica de US$ 62, ainda a cotar. Fargate assume quatro serviços ARM: dois de 0,25 vCPU/0,5 GB e dois de 0,5 vCPU/1 GB. As tarifas oficiais são US$ 0,0000089944 por vCPU-segundo e US$ 0,0000009889 por GB-segundo. O EKS em suporte padrão custa US$ 0,10 por hora. NAT e ALB usam US$ 0,045 e US$ 0,0225 por hora, antes do consumo variável. Três IPv4, um para NAT e dois para ALB, custam US$ 0,005 por endereço-hora. O subtotal é parcial, não uma fatura nem um mínimo garantido. Preços consultados em 06/10/2026.',
 20:'Os nós EC2 com Auto Mode usam uma provisão orçamentária de US$ 0,05 por nó-hora, e não uma tarifa cotada. A base assume dois nós, US$ 73/mês, e o cenário ampliado assume quatro, US$ 146/mês. As reservas auxiliares de US$ 30/60 cobrem EBS, S3, ECR, bastion, backups, CloudWatch, Lambda, SQS e APIs. As reservas de uso variável de US$ 10/50 cobrem LCU, bytes de NAT e transferências. Todas precisam de validação com o inventário e o Billing. Um segundo NAT com um IPv4 acrescenta US$ 36,50/mês antes do tráfego. Multi-AZ do RDS requer cotação própria. LLM externo, pessoal e impostos ficam fora dessa conta.',
 21:'As razões por evento são cenários condicionais. O denominador deve ser a quantidade de eventos válidos persistidos, e não o total de respostas HTTP 202. Dez milhões no mesmo orçamento só reduzirão o custo unitário se a capacidade e o consumo adicional permitirem. Para retenção, 10 milhões × 1 kB decimal dão 10 GB lógicos por mês. Noventa dias dão 30 GB antes de índices, WAL, réplicas e duplicações entre camadas. O potencial de horas de plantão é 3 engenheiros × 6 h × 4 incidentes/mês × 12 × 35% = 302,4 h/ano. Não é uma redução observada, nem um benefício somado ao TCO. Sem modelo e hospedagem comprovados, o custo de LLM permanece separado.',
 22:'O slide recalcula o modelo acadêmico com valores exatos, antes do arredondamento. Não usa o orçamento do laboratório como cotação de produção. O contrato assumido é de R$ 4,064 milhões/ano. O investimento é R$ 1,015 milhão. A operação anual é R$ 282 mil + R$ 810 mil × rollout. O contrato residual é baseline × (1 − substituição × rollout). Na base, a substituição é 50% e o rollout é 40%, 80% e 100%. Construir soma R$ 11.364.600 em três anos contra R$ 12.192.000 de contrato, uma economia de R$ 827.400 ou 6,8%. A virada ocorre perto do mês 25 se o fluxo do terceiro ano for linear. No pessimista, substituição de 30% e rollout de 20%, 40% e 60% dão R$ 13.561.960, ou R$ 1.369.960 a mais. O contrato e a adoção precisam de validação do parceiro.',
 23:'O resultado é um MVP com ingestão e leitura sob ensaio AWS, motor determinístico testado e upload de arquivos validado localmente. Isso ainda não equivale a prontidão de produção. O agente alternativo permanece uma proposta. O próximo aceite deve medir frescor ponta a ponta, reconciliação por IDs, SuccessfulRescale no EKS, restauração do RDS e perda de nó. A avaliação de valor precisa medir tempo até uma hipótese útil e correta com investigadores do parceiro. O custo real deve vir do Billing e dos eventos persistidos.',
 25:'As evidências internas têm corte em 06/10/2026, com a base f3c498e do repositório. As rodadas registradas são de setembro e outubro e não representam uma execução integral nova. As notas identificam a fonte de cada slide. A pasta inclui os geradores, o roteiro e o CSV de custos. Gráficos, tabelas, diagramas e textos do PPTX são editáveis. A captura da interface é uma imagem histórica preservada. O PDF é a versão visual de consulta.'
};
for(const [n,narration] of Object.entries(narrations)){
 const s=slides[Number(n)-1];
 const refs=s.notes.includes('\n\nFontes:')?s.notes.split('\n\nFontes:')[1]:'';
 s.notes=narration+'\n\nFontes:'+refs;
}
// Geometry/content safeguards before writing a package.
for(const [i,s] of slides.entries())for(const e of s.elements){
 if([e.x,e.y,e.w,e.h].some(v=>!Number.isFinite(v)))throw new Error(`Nonfinite geometry on slide ${i+1}`);
 if(e.x<0||e.y<0||e.x+e.w>1280.1||e.y+e.h>720.1)throw new Error(`Out of canvas on slide ${i+1}: ${e.type}`);
}
const spec={width:1280,height:720,font:'Arial',root,cost,tcoBase,tcoPessimistic,slides};
const specPath=path.join(build,'deck.json');await fs.writeFile(specPath,JSON.stringify(spec,null,2));
await fs.writeFile(path.join(out,'roteiro.md'),slides.map((s,i)=>`## ${String(i+1).padStart(2,'0')} — ${s.title}\n\n${s.notes}\n`).join('\n'));
const csv=[['item','usd_mes','tipo'],['RDS_100GB',cost.rds,'estimativa_historica'],['Fargate',cost.fargate,'taxa_oficial_e_config_assumida'],['EKS',cost.eks,'taxa_oficial'],['NAT_horas',cost.nat,'taxa_oficial'],['ALB_horas',cost.alb,'taxa_oficial'],['IPv4_3_enderecos',cost.ipv4,'taxa_oficial_e_qtd_assumida'],['subtotal_parcial',cost.subtotal,'calculado'],['nos_base',73,'provisao_a_cotar'],['servicos_auxiliares_base',30,'reserva'],['uso_variavel_base',10,'reserva'],['total_base',cost.base,'orcamento'],['total_ampliado',cost.expanded,'orcamento']].map(r=>r.join(',')).join('\n');
await fs.writeFile(path.join(out,'custos.csv'),csv+'\n');
const tcoRows=[['cenario','investimento_brl','operacao_3a_brl','contrato_residual_3a_brl','tco_construir_brl','tco_contratar_brl','economia_brl'],...Object.entries({base:tcoBase,pessimista:tcoPessimistic}).map(([k,v])=>[k,v.investment,v.years.reduce((s,y)=>s+y.operation,0),v.years.reduce((s,y)=>s+y.residual,0),v.build,v.buy,v.saving])];
await fs.writeFile(path.join(out,'tco.csv'),tcoRows.map(r=>r.join(',')).join('\n')+'\n');
const result=spawnSync(arg('--python')||'python',[path.join(here,'render_deck.py'),specPath,out],{stdio:'inherit'});
if(result.status!==0)process.exit(result.status||1);
console.log(`Created ${slides.length} slides. Partial subtotal: $${cost.subtotal.toFixed(2)}. Base budget: $${cost.base.toFixed(2)}.`);
