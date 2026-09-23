# Testes funcionais, unitários e de carga

&emsp; Este documento registra como os testes do Argus foram planejados, escritos e
executados, e o que eles produziram. A seção de testes unitários cobre unidades
de lógica de quatro serviços: backend, worker de ingestão, simulador e motor de
processamento, integradas na branch `develop`.

## Testes Unitários

### Objetivo e escopo

&emsp; O que torna estes testes unitários é o isolamento. Cada um exercita uma função,
um método ou uma classe em memória, sem subir PostgreSQL, sem tocar nas filas SQS
e sem chamar a AWS. A suíte roda em `pytest` e cobre entradas válidas, entradas
inválidas e valores nas fronteiras.

#### Critérios de aceite desta etapa

| Critério | Evidência observada | Situação |
|---|---|---|
| Pelo menos quatro testes unitários implementados | 133 casos automatizados em 12 arquivos | Aprovado |
| Função, método ou classe testada identificada | Unidade indicada na matriz e no arquivo de cada teste | Aprovado |
| Casos válidos e casos de erro | TU-01, TU-03, TU-06 e TU-08 válidos; TU-02, TU-04, TU-05, TU-07 e TU-09 de erro ou rejeição | Aprovado |
| Uso de ferramenta automatizada | `pytest` nos quatro serviços | Aprovado |
| Testes efetivamente executados | 133 aprovados e nenhuma falha na execução de 21/09/2026 | Aprovado |
| Código, comandos e evidências localizáveis | Caminhos, comandos e evidências registrados em Ambiente, ferramenta e localização, Resultado consolidado da execução e Instruções para reprodução | Aprovado |

### Ambiente, ferramenta e localização

#### Ambiente da execução

| Item | Valor observado |
|---|---|
| Data e hora | 21/09/2026, 16:56:50 (UTC-03:00) |
| Sistema | Linux |
| Linguagem | Python 3.12.3 |
| Ferramenta | pytest |
| Versão no backend | pytest 8.4.2 |
| Versão nos demais serviços | pytest 9.1.1 |
| Dependências externas | Nenhuma para os arquivos unitários selecionados |
| Evidência textual | [`evidencias/testes-unitarios.txt`](evidencias/testes-unitarios.txt) |

#### O que é uma unidade nos scripts pytest

&emsp; Neste documento, **unidade** é o menor elemento do código de produção exercitado
isoladamente: uma função, um método ou uma classe. Vale distingui-la da estrutura
que o pytest usa para organizar a suíte, porque as duas costumam ser confundidas
na hora de contar o que foi testado.

| Elemento encontrado no script | Significado |
|---|---|
| Função ou método importado do diretório `src/` | Unidade de produção sob teste |
| Função com nome iniciado por `test_` | Caso de teste automatizado, com entrada e resultado esperado |
| Classe com nome iniciado por `Test` | Agrupamento de casos relacionados; não é, por si só, a unidade testada |
| Fake, stub ou `monkeypatch` | Recurso para substituir uma dependência e manter a unidade isolada |
| `assert` ou `pytest.raises` | Verificação do resultado ou do erro esperado |

Exemplo real simplificado de `test_normalization.py`:

```python
class TestParseDatetime:  # agrupamento do pytest
    def test_deve_levantar_erro_para_formato_desconhecido(self):  # caso
        with pytest.raises(ValidationError, match="invalido"):  # resultado esperado
            parse_datetime("nao-e-uma-data")  # unidade testada: função de produção
```

&emsp; Nesse exemplo, `parse_datetime` é a unidade, `TestParseDatetime` organiza os
casos e `test_deve_levantar_erro_para_formato_desconhecido` é um caso automatizado.
Daí a leitura correta do número: os 133 contam casos executados, e as unidades
por trás deles são bem menos, já que uma mesma função costuma aparecer em vários
casos entre válidos, de erro e de fronteira.

#### Inventário do código executado

| Serviço | Arquivo de teste | Unidades principais | Tipo de unidade | Casos |
|---|---|---|---|---:|
| Backend | [`test_normalization.py`](../apps/fullstack/backend/tests/unit/test_normalization.py) | `parse_datetime`, `parse_json_object`, conversões, chaves e UUID | Funções | 20 |
| Backend | [`test_redaction.py`](../apps/fullstack/backend/tests/unit/test_redaction.py) | `hash_user_id`, `sanitize_url`, `redact_headers`, `redact_attributes` | Funções | 15 |
| Backend | [`test_signals.py`](../apps/fullstack/backend/tests/unit/test_signals.py) | `_severidade`, `_signal_id`, `GenerateSignals.execute` | Funções e método de caso de uso | 11 |
| Backend | [`test_timeline.py`](../apps/fullstack/backend/tests/unit/test_timeline.py) | `amostrar_raia` | Função | 6 |
| Backend | [`test_use_cases_logic.py`](../apps/fullstack/backend/tests/unit/test_use_cases_logic.py) | resumo, janelas, cursores e autenticação | Funções | 11 |
| Worker | [`test_changes.py`](../apps/fullstack/worker/tests/test_changes.py) | `ChangeEvent`, `parse_change` | Classe/modelo e função | 7 |
| Worker | [`test_check_size.py`](../apps/fullstack/worker/tests/test_check_size.py) | `check_size` | Função | 4 |
| Worker | [`test_config.py`](../apps/fullstack/worker/tests/test_config.py) | `_env_int`, `Config.from_env` | Função e método de classe | 8 |
| Worker | [`test_extract.py`](../apps/fullstack/worker/tests/test_extract.py) | `_extract`, `_registro_recusado`, `_serializavel` | Funções | 14 |
| Simulador | [`test_emitter.py`](../apps/fullstack/simulator/tests/test_emitter.py) | `_blocos` | Função | 5 |
| Simulador | [`test_faults.py`](../apps/fullstack/simulator/tests/test_faults.py) | `Falha.alcanca`, `Falha.aplicar`, `sortear`, `_params` | Métodos de instância e funções | 15 |
| Processamento | [`test_detector_logic.py`](../apps/fullstack/processing/tests/test_detector_logic.py) | transformações, materialidade, direção, qualidade e scoring | Funções | 17 |
| **Total** | **12 arquivos** | **conjunto de unidades isoladas** | **Funções, métodos e classe/modelo** | **133 casos** |

&emsp; Os arquivos-fonte exercitados ficam nos diretórios `src/telemetry`,
`src/argus_worker`, `src/argus_simulator` e `src/argus_processing` dos
respectivos serviços. As configurações do pytest estão nos arquivos
`pyproject.toml` de cada serviço.

### Planejamento e rastreabilidade

&emsp; Nove casos foram escolhidos para documentação detalhada, procurando cobrir
situações de naturezas diferentes: o comportamento nominal, a recusa de dado
inválido, a proteção de informação pessoal, a autenticação e a análise de sinais.
Os TU-06 e TU-07 são os lados opostos da fronteira de 4 MB, no limite exato e um
byte acima dele. O restante dos 12 arquivos continua valendo como suíte de regressão.

| ID | Unidade testada | Tipo de unidade | Natureza do caso | Requisito ou caso de uso relacionado | Arquivo automatizado |
|---|---|---|---|---|---|
| TU-01 | `hash_user_id` | Função | Válido | RNF10, proteção dos dados coletados | `backend/tests/unit/test_redaction.py` |
| TU-02 | `parse_datetime` | Função | Erro | RF01/RF03, receber telemetria sem aceitar data inválida | `backend/tests/unit/test_normalization.py` |
| TU-03 | `amostrar_raia` | Função | Fronteira válida | RF12, apresentar gráficos e indicadores | `backend/tests/unit/test_timeline.py` |
| TU-04 | `GenerateSignals.execute` | Método de caso de uso | Fluxo alternativo | RF13, destacar falhas de maior impacto | `backend/tests/unit/test_signals.py` |
| TU-05 | `_extract` | Função | Erro | RNF04/RNF11, isolar entrada inválida e identificar a falha | `worker/tests/test_extract.py` |
| TU-06 | `check_size` | Função | Limite aceito | RNF04, impedir que payload inválido comprometa o fluxo | `worker/tests/test_check_size.py` |
| TU-07 | `check_size` | Função | Imediatamente acima | RNF04, rejeitar payload irrecuperável | `worker/tests/test_check_size.py` |
| TU-08 | `_material` | Função | Válido | RF17/RNF08, hipóteses apoiadas por evidências relevantes | `processing/tests/test_detector_logic.py` |
| TU-09 | `_token_do_cabecalho` | Função | Erro | RNF09, acesso apenas com credencial autorizada | `backend/tests/unit/test_use_cases_logic.py` |

### Especificação e resultado dos casos

#### TU-01 - Gerar identificador desidentificado e determinístico

&emsp; Este caso verifica a desidentificação usada para impedir que o backend exponha
diretamente o identificador do usuário. A comparação não usa um valor copiado da
implementação: o próprio teste calcula o SHA-256 esperado e confronta o resultado.

| Campo | Conteúdo |
|---|---|
| Identificador | TU-01 |
| Objetivo | Verificar que `hash_user_id` transforma um identificador em um hash estável sem expor o valor original |
| Requisito | RNF10, proteção dos dados coletados |
| Unidade testada | Função `hash_user_id`, em [`redaction.py`](../apps/fullstack/backend/src/telemetry/application/redaction.py) |
| Pré-condições | Ambiente do backend instalado pelo `uv`; nenhuma conexão externa necessária |
| Dados de entrada | `user_id="usuario-123"` e `salt="meu-salt-secreto"` |
| Procedimento | Executar o nó pytest do caso; o teste calcula independentemente o SHA-256 de `salt:user_id`, recorta os 32 primeiros caracteres e compara valor, tamanho e alfabeto |
| Situação | Aprovado |
| Evidência | `test_redaction.py` aprovado no bloco da execução em [`evidencias/testes-unitarios.txt`](evidencias/testes-unitarios.txt) |

| Caso | Entrada | Resultado esperado | Resultado obtido | Situação |
|---|---|---|---|---|
| TU-01.1 | Identificador e salt válidos | Hash determinístico, hexadecimal e com 32 caracteres | Valor igual ao SHA-256 calculado de forma independente; tamanho e caracteres hexadecimais confirmados | Aprovado |

&emsp; Para reproduzir apenas este caso:

```bash
cd apps/fullstack/backend
uv run pytest tests/unit/test_redaction.py::TestHashUserId::test_deve_gerar_hash_deterministico_de_32_hex -v
```

#### TU-02 - Rejeitar data em formato desconhecido

&emsp; Este é o caso de erro da seleção. Ele protege a fronteira de normalização:
uma data incompreensível deve ser recusada de forma tipada, em vez de virar um
horário incorreto ou avançar silenciosamente pelo pipeline.

| Campo | Conteúdo |
|---|---|
| Identificador | TU-02 |
| Objetivo | Garantir que uma data não interpretável seja rejeitada durante a normalização da telemetria |
| Requisitos | RF01/RF03, receber telemetria sem aceitar data inválida |
| Unidade testada | Função `parse_datetime`, em [`normalization.py`](../apps/fullstack/backend/src/telemetry/application/normalization.py) |
| Pré-condições | Ambiente do backend instalado; nenhuma dependência externa |
| Dados de entrada | String `"nao-e-uma-data"` |
| Procedimento | Chamar `parse_datetime` dentro de `pytest.raises` e verificar a classe da exceção e a presença de `invalido` na mensagem |
| Situação | Aprovado |
| Evidência | `test_normalization.py` aprovado no bloco da execução em [`evidencias/testes-unitarios.txt`](evidencias/testes-unitarios.txt) |

| Caso | Entrada | Resultado esperado | Resultado obtido | Situação |
|---|---|---|---|---|
| TU-02.1 | Texto que não corresponde a nenhum formato de data aceito | `ValidationError` com indicação de valor inválido; nenhum `datetime` produzido | A exceção de domínio e a mensagem esperadas foram capturadas | Aprovado |

&emsp; Para reproduzir apenas este caso:

```bash
cd apps/fullstack/backend
uv run pytest tests/unit/test_normalization.py::TestParseDatetime::test_deve_levantar_erro_para_formato_desconhecido -v
```

#### TU-03 - Amostrar série um ponto acima do limite

&emsp; Este caso usa o primeiro valor acima da fronteira aceita. Além de confirmar a
redução, verifica que a amostragem preserva as duas extremidades temporais, necessárias
para que a Timeline não apresente uma janela diferente daquela consultada.

| Campo | Conteúdo |
|---|---|
| Identificador | TU-03 |
| Objetivo | Confirmar que `amostrar_raia` reduz uma série que ultrapassa o limite sem perder as extremidades temporais |
| Requisito | RF12, apresentar gráficos e indicadores |
| Unidade testada | Função `amostrar_raia`, em [`timeline.py`](../apps/fullstack/backend/src/telemetry/application/timeline.py) |
| Pré-condições | Lista ordenada criada em memória; nenhuma conexão externa |
| Dados de entrada | 101 pontos sequenciais e `limite=100` |
| Procedimento | Executar a função e verificar o indicador de truncamento, a quantidade retornada e a preservação do primeiro e do último ponto |
| Situação | Aprovado |
| Evidência | `test_timeline.py` aprovado no bloco da execução em [`evidencias/testes-unitarios.txt`](evidencias/testes-unitarios.txt) |

| Caso | Entrada | Resultado esperado | Resultado obtido | Situação |
|---|---|---|---|---|
| TU-03.1 | Série com 101 pontos para um limite de 100 | `truncated=True`, no máximo 100 pontos e extremos preservados | Truncamento ativado, quantidade dentro do limite e primeiro e último pontos mantidos | Aprovado |

&emsp; Para reproduzir apenas este caso:

```bash
cd apps/fullstack/backend
uv run pytest tests/unit/test_timeline.py::TestAmostrarRaia::test_serie_um_acima_do_limite_e_truncada -v
```

#### TU-04 - Ignorar sinal que deixou de exceder o limiar

&emsp; Este caso exercita um fluxo alternativo do caso de uso sem acessar banco. Um
repositório fake fornece os buckets necessários e mantém sob teste somente a decisão
de apresentar ou descartar o sinal.

| Campo | Conteúdo |
|---|---|
| Identificador | TU-04 |
| Objetivo | Verificar que o backend não apresenta como ativo um sinal cujo bucket mais recente voltou à faixa estável |
| Requisito | RF13, destacar falhas de maior impacto |
| Unidade testada | Método `GenerateSignals.execute`, em [`signals.py`](../apps/fullstack/backend/src/telemetry/application/signals.py) |
| Pré-condições | Repositório fake em memória retornando dois buckets; nenhuma conexão externa |
| Dados de entrada | Bucket anterior com `z=3.0` e bucket mais recente com `z=1.5`, abaixo do limiar de sinal `2.0` |
| Procedimento | Instanciar `GenerateSignals` com o fake, executar o caso de uso no intervalo dos buckets e inspecionar `count` e `items` |
| Situação | Aprovado |
| Evidência | `test_signals.py` aprovado no bloco da execução em [`evidencias/testes-unitarios.txt`](evidencias/testes-unitarios.txt) |

| Caso | Entrada | Resultado esperado | Resultado obtido | Situação |
|---|---|---|---|---|
| TU-04.1 | Dois buckets do mesmo sinal, sendo o último estável | `count=0` e `items=[]` | Nenhum sinal ativo foi produzido | Aprovado |

&emsp; Para reproduzir apenas este caso:

```bash
cd apps/fullstack/backend
uv run pytest tests/unit/test_signals.py::TestGenerateSignals::test_deve_ignorar_grupo_cujo_ultimo_bucket_esta_abaixo_do_limiar -v
```

#### TU-05 - Rejeitar JSON inválido recebido pelo worker

&emsp; Este caso verifica a primeira barreira do consumidor. Um corpo corrompido deve
ser identificado antes de qualquer tentativa de persistência e produzir um motivo
de falha reproduzível.

| Campo | Conteúdo |
|---|---|
| Identificador | TU-05 |
| Objetivo | Confirmar que o worker recusa um corpo JSON corrompido antes da persistência |
| Requisitos | RNF04/RNF11, isolar a entrada inválida e identificar a falha |
| Unidade testada | Função `_extract`, em [`consumer.py`](../apps/fullstack/worker/src/argus_worker/consumer.py) |
| Pré-condições | Ambiente do worker instalado; nenhuma fila SQS ou banco necessário |
| Dados de entrada | Corpo `"{ chave_sem_fechar: "` e chave `"events"` |
| Procedimento | Chamar `_extract` dentro de `pytest.raises` e comparar a mensagem da exceção com `JSON invalido` |
| Situação | Aprovado |
| Evidência | Nó TU-05 aprovado em [`evidencias/testes-unitarios.txt`](evidencias/testes-unitarios.txt) |

| Caso | Entrada | Resultado esperado | Resultado obtido | Situação |
|---|---|---|---|---|
| TU-05.1 | Corpo que não pode ser interpretado como JSON | `ValueError` identificando JSON inválido; nenhuma estrutura extraída | Exceção e mensagem esperadas observadas | Aprovado |

&emsp; Para reproduzir apenas este caso:

```bash
cd apps/fullstack/worker
uv run pytest tests/test_extract.py::TestConsumerExtract::test_deve_lancar_erro_quando_json_invalido -v
```

#### TU-06 - Aceitar payload exatamente no limite de 4 MB

&emsp; Este caso cobre o último valor válido da fronteira de tamanho. Ele comprova que
a guarda não rejeita um change event que ainda pertence ao contrato aceito.

| Campo | Conteúdo |
|---|---|
| Identificador | TU-06 |
| Objetivo | Verificar que a guarda de tamanho aceita um payload exatamente no limite |
| Requisito | RNF04, impedir que payload inválido comprometa o fluxo |
| Unidade testada | Função `check_size`, em [`repository.py`](../apps/fullstack/worker/src/argus_worker/repository.py) |
| Pré-condições | `MAX_CHANGE_BYTES=4.000.000`; uso da mesma serialização da implementação |
| Dados de entrada | Dicionário cujo JSON serializado possui exatamente `4.000.000` bytes |
| Procedimento | Confirmar o tamanho serializado e chamar `check_size` diretamente |
| Situação | Aprovado |
| Evidência | Nó TU-06 aprovado em [`evidencias/testes-unitarios.txt`](evidencias/testes-unitarios.txt) |

| Caso | Entrada | Resultado esperado | Resultado obtido | Situação |
|---|---|---|---|---|
| TU-06.1 | JSON com exatamente 4.000.000 bytes | Retorno sem exceção | Payload no limite aceito | Aprovado |

&emsp; Para reproduzir apenas este caso:

```bash
cd apps/fullstack/worker
uv run pytest tests/test_check_size.py::TestCheckSize::test_deve_permitir_payload_exatamente_no_limite -v
```

#### TU-07 - Rejeitar payload um byte acima do limite

&emsp; Este é o par negativo do TU-06. Ao usar o primeiro valor inválido depois da
fronteira, ele comprova que a comparação de tamanho não possui erro de inclusão.

| Campo | Conteúdo |
|---|---|
| Identificador | TU-07 |
| Objetivo | Comprovar que a guarda rejeita o primeiro valor acima do limite permitido |
| Requisito | RNF04, rejeitar payload irrecuperável sem comprometer os demais |
| Unidade testada | Função `check_size`, em [`repository.py`](../apps/fullstack/worker/src/argus_worker/repository.py) |
| Pré-condições | Iguais às do TU-06 |
| Dados de entrada | Dicionário cujo JSON serializado possui exatamente `4.000.001` bytes |
| Procedimento | Confirmar o tamanho e chamar `check_size` dentro de `pytest.raises` |
| Situação | Aprovado |
| Evidência | Nó TU-07 aprovado em [`evidencias/testes-unitarios.txt`](evidencias/testes-unitarios.txt) |

| Caso | Entrada | Resultado esperado | Resultado obtido | Situação |
|---|---|---|---|---|
| TU-07.1 | JSON com exatamente 4.000.001 bytes | Lançamento de `ChangeTooLarge` | Exceção `ChangeTooLarge` capturada | Aprovado |

&emsp; Para reproduzir apenas este caso:

```bash
cd apps/fullstack/worker
uv run pytest tests/test_check_size.py::TestCheckSize::test_deve_rejeitar_payload_um_byte_acima_do_limite -v
```

#### TU-08 - Aprovar desvio que atende aos dois critérios de materialidade

&emsp; Este caso verifica a conjunção das duas regras de materialidade. Um desvio só
deve seguir para a análise quando supera simultaneamente os limites absoluto e
relativo definidos pela política.

| Campo | Conteúdo |
|---|---|
| Identificador | TU-08 |
| Objetivo | Verificar que uma evidência é material quando atende simultaneamente aos limites absoluto e relativo |
| Requisitos | RF17/RNF08, hipóteses apoiadas por evidências relevantes |
| Unidade testada | Função `_material`, em [`detector.py`](../apps/fullstack/processing/src/argus_processing/detector.py) |
| Pré-condições | Política com limite absoluto `10.0` e relativo `0.20` |
| Dados de entrada | Valor observado `125.0` e esperado `100.0`, diferença absoluta `25.0` e relativa `25%` |
| Procedimento | Executar `_material` com os valores e a política indicados e comparar o retorno booleano |
| Situação | Aprovado |
| Evidência | Nó TU-08 aprovado em [`evidencias/testes-unitarios.txt`](evidencias/testes-unitarios.txt) |

| Caso | Entrada | Resultado esperado | Resultado obtido | Situação |
|---|---|---|---|---|
| TU-08.1 | Desvio acima dos dois limites da política | `True` | Retorno `True` | Aprovado |

&emsp; Para reproduzir apenas este caso:

```bash
cd apps/fullstack/processing
uv run pytest tests/test_detector_logic.py::TestDetectorMaterialAndDirection::test_material_aprova_quando_atende_ambos_limiares -v
```

#### TU-09 - Rejeitar cabeçalhos de autenticação inválidos

&emsp; Este caso cobre entradas ausentes, vazias e com esquema incorreto. A unidade
deve devolver ausência de credencial, impedindo que esses valores avancem como um
token Bearer válido.

| Campo | Conteúdo |
|---|---|
| Identificador | TU-09 |
| Objetivo | Garantir que cabeçalhos ausentes ou fora do formato Bearer não sejam interpretados como credenciais |
| Requisito | RNF09, acesso apenas com credencial autorizada |
| Unidade testada | Função `_token_do_cabecalho`, em [`auth.py`](../apps/fullstack/backend/src/telemetry/interfaces/auth.py) |
| Pré-condições | Nenhuma; função pura executada em memória |
| Dados de entrada | `None`, string vazia, `"Basic dXNlcjpwYXNz"`, `"Bearer"` e `"Bearer    "` |
| Procedimento | Executar a função para cada entrada e comparar todos os retornos com `None` |
| Situação | Aprovado |
| Evidência | Nó TU-09 aprovado em [`evidencias/testes-unitarios.txt`](evidencias/testes-unitarios.txt) |

| Caso | Entrada | Resultado esperado | Resultado obtido | Situação |
|---|---|---|---|---|
| TU-09.1 | Cinco formas ausentes ou inválidas de cabeçalho | `None` para todas as entradas | Todas as entradas rejeitadas com retorno `None` | Aprovado |

&emsp; Para reproduzir apenas este caso:

```bash
cd apps/fullstack/backend
uv run pytest tests/unit/test_use_cases_logic.py::TestAuthHelpers::test_token_do_cabecalho_rejeita_formatos_invalidos -v
```

### Resultado consolidado da execução

| Serviço | Coletados | Aprovados | Reprovados | Duração observada | Situação |
|---|---:|---:|---:|---:|---|
| Backend | 63 | 63 | 0 | 0,04 s | Aprovado |
| Worker | 33 | 33 | 0 | 0,23 s | Aprovado |
| Simulador | 20 | 20 | 0 | 0,04 s | Aprovado |
| Processamento | 17 | 17 | 0 | 0,02 s | Aprovado |
| **Total** | **133** | **133** | **0** | **0,33 s somados** | **Aprovado** |

&emsp; As durações saem do próprio pytest, em execuções locais e separadas. A soma vale
como registro desta rodada e nada afirma sobre desempenho, que é assunto dos
ensaios de carga. Os testes que dependem de PostgreSQL ficam fora desta contagem.

#### Conclusão

&emsp; A entrega cumpre o que a especificação pede e vai além em amplitude. O mínimo
eram quatro casos; a suíte executada reuniu 133, dos quais nove foram escolhidos e
descritos em detalhe, com a unidade identificada, entradas válidas, erro e
fronteira. Todos foram automatizados e possuem evidência reproduzível pelos
comandos registrados. Nesta rodada nenhum reprovou.

&emsp; O alcance dessa aprovação para no que foi exercitado: estas unidades, estas
entradas. As seções seguintes ampliam a verificação com os testes de integração
e de carga já executados. A cobertura completa de caso de uso e análise de valor
limite permanece no backlog, porque responde a uma pergunta que os testes
unitários isolados não alcançam.

### Instruções para reprodução

&emsp; Os comandos partem da raiz do repositório e usam os ambientes declarados em
cada `pyproject.toml`:

```bash
# Backend: 63 testes unitários
cd apps/fullstack/backend
uv run --quiet pytest tests/unit --tb=no

# Worker: 33 testes unitários selecionados
cd ../worker
uv run --quiet pytest \
  tests/test_changes.py \
  tests/test_check_size.py \
  tests/test_config.py \
  tests/test_extract.py \
  --tb=no

# Simulador: 20 testes unitários selecionados
cd ../simulator
uv run --quiet pytest tests/test_emitter.py tests/test_faults.py --tb=no

# Processamento: 17 testes unitários selecionados
cd ../processing
uv run --quiet pytest tests/test_detector_logic.py --tb=no
```

&emsp; Os comandos de cada um dos nove casos detalhados aparecem imediatamente após
sua tabela. A reprodução confere
quando o processo termina com código `0`, o caso aparece como `PASSED` e nenhuma
linha traz `FAILED`.

## Testes de integração

### O que esta seção verifica

&emsp; Os testes unitários da seção anterior olham para uma função de cada vez, com
tudo em volta substituído por um dublê, isto é, um objeto falso que responde o que
o teste mandar. Eles respondem a uma pergunta estreita e importante: esta unidade
calcula certo?

&emsp; Os testes desta seção respondem a outra pergunta. Não é se cada peça está
correta, e sim se duas camadas diferentes conseguem conversar. Cada um deles
percorre um caminho real entre componentes que rodam em processos, linguagens ou
tecnologias distintas, sem nenhum dublê no trecho que está sob teste. É por isso
que encontram uma classe de defeito que nenhum teste unitário alcança, por melhor
que ele seja: o campo que a origem grava com um nome e o destino lê com outro, o
filtro que a tela mostra ao operador mas nunca chega a enviar, o número que o banco
agrega corretamente e a interface arredonda errado na hora de desenhar.

### Panorama dos cinco testes

&emsp; Foram planejados, implementados e executados cinco testes de integração,
somando treze casos. Os quatro primeiros cobrem pares de camadas que rodam na
máquina de desenvolvimento. O quinto exercita a pilha publicada na AWS, e é o único
com um caso reprovado.

| Teste | Camadas que ele atravessa | Casos | Situação |
|---|---|---:|---|
| TI-01 | Dashboard Next.js, API Flask de leitura e PostgreSQL | 3 | Aprovado |
| TI-02 | Rota Flask, caso de uso, adaptador de repositório e PostgreSQL | 3 | Aprovado |
| TI-03 | Worker de ingestão, fila SQS e PostgreSQL | 2 | Aprovado |
| TI-04 | ETL incremental entre as camadas bronze, silver e gold | 3 | Aprovado |
| TI-05 | Pilha publicada na AWS, da borda HTTP até a API de leitura | 2 | 1 aprovado, 1 reprovado |

&emsp; No total, treze casos implementados e executados, doze aprovados e um
reprovado. O reprovado é o TI-05.2, cuja causa raiz está identificada: o evento
chegou ao banco, mas a ETL não o promoveu para a camada consultável dentro do prazo
do teste. A reprovação foi mantida como está, investigada até o fim e deu origem
a uma correção, em vez de ser contornada afrouxando o prazo. A correção foi
validada localmente pelo plano de execução, mas o fluxo completo na infraestrutura
publicada ainda não foi reexecutado. A execução original, com a saída bruta de
cada suíte, está em
[`evidencias/testes-integracao.txt`](evidencias/testes-integracao.txt).

&emsp; Este relatório usa os mesmos três estados adotados em
[`testes-carga-inicial.md`](testes-carga-inicial.md), para que uma afirmação forte e
uma fraca não pareçam iguais a quem lê rápido. Um teste preparado é aquele cujo
cenário e automação existem no repositório. Um teste executado foi de fato rodado, e
sua saída está registrada na evidência. Um teste aprovado é o que, além de
executado, satisfez todos os critérios de aceite do caso.

### Componentes envolvidos e resultado esperado da interação

&emsp; Convém deixar claro o que conta como
resultado esperado aqui: é sempre uma afirmação sobre a travessia, sobre o que
acontece no caminho entre duas peças, e nunca sobre o comportamento interno de
nenhuma das pontas isoladamente. Isso último já é assunto dos testes unitários.

| Teste | Componente de origem | Componente de destino | Mecanismo de comunicação | Resultado esperado da interação |
|---|---|---|---|---|
| TI-01 | Dashboard Next.js estático, no navegador Chromium | API Flask de leitura | HTTP com JSON, token de acesso na sessão do navegador | O filtro escolhido na tela aparece na query string enviada, e a tabela desenhada contém exatamente as linhas do JSON recebido |
| TI-01 | API Flask de leitura | PostgreSQL | Conexão TCP e SQL sobre `gold.feature_bucket` e `silver.session_event` | O recorte é aplicado no banco, e não no cliente: trocar o filtro muda o conjunto que volta pela rede |
| TI-02 | Rota Flask, caso de uso e porta de repositório | Adaptador `PostgresEventRepository` e a tabela `silver.session_event` | Chamada de método pela porta, depois SQL parametrizado | A linha gravada reaparece campo a campo na resposta HTTP, e o identificador do usuário é trocado pelo hash na travessia |
| TI-03 | Fila SQS `argus-events` | `EventConsumer`, `EventRepository` e a tabela `bronze.event` | Mensagem JSON na fila, escrita com `INSERT ... ON CONFLICT` | Mensagem válida vira linha, a inválida sai pela fila de descarte sem travar a válida seguinte, e a reentrega não duplica |
| TI-04 | `bronze.change_log` e a função `bronze.merge_todas()` | Módulo `argus_processing.etl`, `silver.signal_bucket` e `gold.feature_bucket` | Funções SQL coordenadas pelos marcadores `etl.watermark_*` | O valor atravessa as três camadas sem se deformar, cada marcador avança na medida do que processou, e ciclo ocioso não reprocessa |
| TI-05 | Cliente HTTP externo | API Gateway e o Lambda authorizer das duas APIs publicadas | HTTPS com cabeçalho `Authorization: Bearer` | A borda recusa com 401 ou 403 a requisição sem token, com token desconhecido e com token da audiência errada, aceitando só o da própria audiência |
| TI-05 | Rota `POST /v1/events` no API Gateway | Fila SQS, event-worker no Fargate, RDS, ETL e a rota `GET /api/v1/events` | Integração direta entre API Gateway e SQS, sem Lambda no caminho de escrita | Um evento aceito na borda aparece na API de leitura dentro do prazo, com os campos preservados |

&emsp; A última linha merece um comentário, porque a espera que ela descreve é
proposital. A ingestão é assíncrona por projeto: a borda enfileira e responde de imediato, e quem
grava é o worker. O que o teste afirma é que essa espera termina, e termina dentro
de um prazo que faça sentido para quem opera o sistema.

### Vocabulário usado nesta seção

&emsp; Alguns termos aparecem com frequência e não são óbvios para quem chega de fora
do projeto.

&emsp; **Fila de descarte, ou DLQ, de dead-letter queue**, é uma fila separada para onde
vai a mensagem que o consumidor não conseguiu processar. Ela existe para que um dado
ruim saia de circulação de forma registrada, com o motivo da recusa anexado, em vez
de ser reentregue indefinidamente ou descartado em silêncio.

&emsp; **Entrega ao menos uma vez, ou at-least-once**, é a garantia que o SQS oferece: a
fila promete que a mensagem chega, mas não promete que chega uma única vez. Se a
confirmação de processamento se perder no caminho, a mesma mensagem é entregue de
novo. Cabe ao destino ser idempotente, ou seja, produzir o mesmo resultado
processando duas vezes ou uma.

&emsp; **Marcador de progresso, ou watermark**, é uma linha no banco que registra até onde
uma etapa da ETL já processou. É o que torna o processamento incremental: cada
execução lê apenas o que entrou depois do marcador e o avança ao terminar. Cada linha
que entra na camada bronze recebe um número de ordem, o `lsn`, e é por ele que o
marcador se orienta.

&emsp; **Bronze, silver e gold** nomeiam os três estágios do armazenamento. A bronze
guarda o dado bruto como ele chegou, a silver guarda o dado normalizado no esquema
comum, e a gold guarda o dado agregado e pronto para as consultas do dashboard.

### Ambiente de execução

| Item | Valor |
|---|---|
| Data da execução | 17 de setembro de 2026 |
| Sistema | Linux 7.0.0-31-generic, x86_64 |
| Banco de dados | PostgreSQL 16.14 em contêiner Docker, o `argus-pg`, na porta 55432, base `argus_test` |
| Ferramentas | pytest 8.4.2 no backend com Python 3.13; pytest 9.1.1 no worker com Python 3.12 e no processamento com Python 3.13; Playwright 1.62.1 com Chromium 151.0.7922.34 |
| Dublês usados | Apenas o SQS, reproduzido em memória pelo `moto` versão 5 ou superior, no TI-03. Banco, API, navegador e site são reais em todos os testes |
| Ambiente do TI-05 | Pilha publicada no AWS Academy Learner Lab, região `us-east-1`: API Gateway HTTP, Lambda authorizer, Lambda da API de leitura, SQS, ECS Fargate e RDS PostgreSQL. Nenhum componente dublado |
| Caminho de leitura exercitado | A Lambda por trás do API Gateway. A pilha tem outras duas portas para a mesma API — o ALB do grupo de auto scaling e, desde a Sprint 4, o Ingress do cluster EKS — e nenhuma delas é exercitada pelo TI-05 (ver [Cobertura do caminho orquestrado por Kubernetes](#cobertura-do-caminho-orquestrado-por-kubernetes)) |

### Onde está cada coisa no repositório

| Caminho | Papel |
|---|---|
| [`apps/fullstack/frontend/tests/e2e/integracao-camadas.spec.ts`](../apps/fullstack/frontend/tests/e2e/integracao-camadas.spec.ts) | Código do TI-01 |
| [`apps/fullstack/frontend/tests/e2e/fixture.sql`](../apps/fullstack/frontend/tests/e2e/fixture.sql) | Dados de entrada do TI-01, carregados no PostgreSQL |
| [`apps/fullstack/frontend/playwright.config.ts`](../apps/fullstack/frontend/playwright.config.ts) | Sobe o Flask e o site estático que o TI-01 usa |
| [`apps/fullstack/backend/tests/integration/test_api_postgres.py`](../apps/fullstack/backend/tests/integration/test_api_postgres.py) | Código do TI-02 |
| [`apps/fullstack/backend/tests/conftest.py`](../apps/fullstack/backend/tests/conftest.py) | Fixtures do TI-02: banco migrado, relógio virtual congelado e aplicação Flask |
| [`apps/fullstack/worker/tests/integration/test_fila_banco.py`](../apps/fullstack/worker/tests/integration/test_fila_banco.py) | Código do TI-03 |
| [`apps/fullstack/worker/tests/conftest.py`](../apps/fullstack/worker/tests/conftest.py) | Fixtures do TI-03: filas SQS em memória e os dois consumidores |
| [`apps/fullstack/worker/tests/fixtures/*.json`](../apps/fullstack/worker/tests/fixtures/) | Dados de entrada do TI-03: os seis eventos reais exportados do BI |
| [`apps/fullstack/processing/tests/integration/test_camadas_medalhao.py`](../apps/fullstack/processing/tests/integration/test_camadas_medalhao.py) | Código do TI-04 |
| [`apps/fullstack/processing/tests/conftest.py`](../apps/fullstack/processing/tests/conftest.py) | Fixtures do TI-04: banco limpo, marcadores reiniciados e relógio virtual |
| [`apps/fullstack/backend/tests/integration/test_implantacao.py`](../apps/fullstack/backend/tests/integration/test_implantacao.py) | Código do TI-05 |
| [`apps/fullstack/.env.example`](../apps/fullstack/.env.example) | Nomes das variáveis que o TI-05 lê do ambiente; URLs e tokens reais ficam no `.env`, que não é versionado |
| [`apps/fullstack/db/migrations/030_indice_lsn_em_evento.sql`](../apps/fullstack/db/migrations/030_indice_lsn_em_evento.sql) | Correção de schema nascida do diagnóstico do TI-05 |
| [`apps/fullstack/processing/tests/test_plano_da_etl.py`](../apps/fullstack/processing/tests/test_plano_da_etl.py) | Teste que sustenta essa correção |
| [`apps/fullstack/Makefile`](../apps/fullstack/Makefile) | Alvos `db-local`, `env`, `auth-show-ingest`, `test-backend`, `test-worker`, `test-processing`, `test-frontend-e2e` e `k8s-validate` |
| [`apps/fullstack/k8s/`](../apps/fullstack/k8s/) | Manifests do caminho síncrono, renderizados pelo `k8s-validate` |
| [`evidencias/testes-integracao.txt`](evidencias/testes-integracao.txt) | Saída bruta da execução dos cinco testes |
| [`evidencias/k8s-validate.txt`](evidencias/k8s-validate.txt) | Saída da renderização dos cinco conjuntos de manifests |

### Pré-condição comum

&emsp; Os quatro testes locais exigem o PostgreSQL no ar, com as migrations aplicadas:

```bash
make -C apps/fullstack db-local
```

&emsp; O comando sobe o contêiner `argus-pg` na porta 55432, e não na 5432, para não
conflitar com um PostgreSQL já instalado na máquina; cria a base `argus_test`; e
aplica as 30 migrations em ordem.

### TI-01: dashboard, API de leitura e PostgreSQL

&emsp; Este teste verifica que o dashboard e a API cumprem o contrato nos dois
sentidos. Na ida, que a escolha do operador na tela chega ao backend como parâmetro
de consulta. Na volta, que o que a tela desenha é exatamente o que o backend leu do
banco. Os testes de contrato que já existiam em `tests/contracts/` cobrem a forma do
JSON contra um dublê; o que só este teste consegue mostrar é que essa forma é a
mesma que o backend real produz a partir do banco real.

&emsp; Uma decisão do cenário merece explicação. O relógio da simulação é congelado em
2026-07-14T12:00Z, e não deixado correndo. Sem isso, o resultado dependeria da data
em que o teste roda, e a suíte começaria a falhar sozinha semanas depois, sem
nenhuma mudança de código.

| Campo | Conteúdo |
|---|---|
| Identificador | TI-01 |
| Objetivo | Verificar o contrato nos dois sentidos entre o dashboard e a API de leitura, sobre dado real do banco |
| Requisitos | RF08, pesquisa por atributos; RF09, filtros cumulativos; RF11, agrupamento por critérios; RNF02, consulta simples em até cinco segundos; RNF09, acesso apenas a autorizados |
| Caso de uso | O operador investiga onde um sinal se concentra, trocando agrupamento e filtro na tela Explorar |
| Componentes envolvidos | Navegador Chromium, site estático Next.js em 127.0.0.1:3100, HTTP, API Flask em 127.0.0.1:5100 e PostgreSQL da base `argus_test` |
| Pré-condições | Banco no ar com migrations aplicadas e `fixture.sql` carregado; site construído com `NEXT_PUBLIC_API_URL` apontando para o Flask local; Chromium do Playwright instalado |
| Dados de entrada | [`fixture.sql`](../apps/fullstack/frontend/tests/e2e/fixture.sql): 21 linhas em `gold.feature_bucket` nas fontes `prometheus`, `youbora_device`, `npaw`, `newrelic` e `apollo`, mais 3 eventos de sessão em `silver.session_event` |
| Procedimento | `make -C apps/fullstack test-frontend-e2e`, que recarrega o `fixture.sql`, constrói o site, sobe o Flask e o servidor do site, e executa o Playwright |
| Situação | Aprovado nos 3 casos |
| Evidência | Bloco TI-01 de [`evidencias/testes-integracao.txt`](evidencias/testes-integracao.txt) |

| Caso | Entrada | Resultado esperado | Resultado obtido | Situação |
|---|---|---|---|---|
| TI-01.1 | Abrir `/explorar/` com sessão aberta, no agrupamento padrão por dispositivo | A requisição sai para a origem do Flask levando `dimension=entity` e `source=youbora_device`; a tabela exibe exatamente o mesmo conjunto de rótulos do JSON; a linha de maior valor mostra o número agregado pelo SQL; tudo em menos de 5 s | Requisição confirmada na origem do Flask; grupos `LG webOS 3.x` e `Samsung Tizen`; 2 rótulos na tabela para 2 grupos no JSON, conjuntos idênticos; valor 1.737,7 renderizado; resposta em 1,0 s | Aprovado |
| TI-01.2 | Trocar o agrupamento para Fonte e depois aplicar o filtro de métrica `request_count` | Cada escolha vira parâmetro na query string, de forma cumulativa; o recorte é aplicado no banco, e `npaw`, que só tem `bufferratio`, desaparece do resultado e da tabela | Ambas as requisições saíram com os parâmetros esperados; `npaw` presente no primeiro agrupamento e ausente após o filtro, no JSON e na tela; rótulos iguais aos do JSON nos dois momentos | Aprovado |
| TI-01.3 | Abrir `/explorar/` sem token na sessão, caso negativo | Nenhuma requisição a `/api/v1/` sai do navegador; a tela de acesso é exibida; nenhuma linha de dado é desenhada | Lista de chamadas à API vazia; título "Acesso ao painel" visível; zero linhas na tabela | Aprovado |

&emsp; O caso negativo importa mais do que parece: ele prova que a barreira do RNF09
vale para a comunicação, e não apenas para a pintura da tela. Um painel que
escondesse os dados mas ainda assim consultasse a API passaria numa inspeção visual
e falharia aqui.

&emsp; Uma ressalva de alcance, que vale para os três casos. O site é construído aqui
com `NEXT_PUBLIC_API_URL` apontando para o endereço absoluto do Flask, e o Playwright
sobe o backend com `CORS_ORIGINS` declarado: são duas origens, `127.0.0.1:3100` e
`127.0.0.1:5100`, conversando por CORS. Essa era a topologia da implantação até a
Sprint 3, quando o dashboard vinha do S3 e a API do balanceador. No caminho
orquestrado por Kubernetes ela deixou de existir: o Ingress serve `/` e `/api` no
mesmo endereço, a imagem é construída com `NEXT_PUBLIC_API_URL=/` e a requisição sai
relativa, sem verificação prévia. O contrato entre a tela e a API, nos dois
sentidos, que é o que o TI-01 verifica, não depende dessa topologia e continua
valendo. O que o teste deixou de reproduzir é o fio exato que vai para o ar.

&emsp; Para reproduzir:

```bash
make -C apps/fullstack db-local          # se o banco ainda não estiver no ar
make -C apps/fullstack test-frontend-e2e
```

&emsp; O alvo pula sozinho, sem falhar, quando o PostgreSQL ou o Chromium do
Playwright não estão disponíveis. Para instalar o navegador, o comando é
`cd apps/fullstack/frontend && npx playwright install chromium`.


### TI-02: aplicação Flask e PostgreSQL

&emsp; Este teste acompanha um registro atravessando as quatro camadas da aplicação
de leitura, da rota HTTP até o SQL, e verifica que ele reaparece intacto na resposta.
Verifica também a barreira de privacidade do RNF10, que só existe nessa travessia: o
banco guarda o identificador do usuário em claro, porque a ingestão não o transforma,
e a API só pode devolver o hash.

&emsp; O dado de entrada é gravado pela função `argus_worker.keys.build_row`, a mesma
que o worker de ingestão usa em produção, e não por um `INSERT` montado no teste.
A escolha é deliberada: é o que impede que a API de leitura e o worker de ingestão
divirjam em silêncio sobre o formato da linha. Um `INSERT` próprio testaria o
`INSERT` do teste.

| Campo | Conteúdo |
|---|---|
| Identificador | TI-02 |
| Objetivo | Verificar que a linha gravada no banco atravessa as quatro camadas da aplicação e reaparece intacta, e que a travessia aplica a barreira de privacidade |
| Requisitos | RF06, armazenar para consulta posterior; RF08, pesquisa por tipo e atributos; RF09, filtros cumulativos; RNF10, não expor dado pessoal desnecessário |
| Caso de uso | O operador busca eventos de erro de um sistema operacional específico |
| Componentes envolvidos | `telemetry.interfaces`, `telemetry.application.use_cases`, `telemetry.ports`, `telemetry.infrastructure.postgres.PostgresEventRepository` e a tabela `silver.session_event` |
| Pré-condições | Banco no ar com migrations aplicadas; tabelas truncadas antes de cada caso; relógio da simulação congelado em 2026-07-14T12:00Z |
| Dados de entrada | Um evento de erro sintético na sessão `sessao-ti02`, dispositivo `device-ti02`, usuário `usuario-ti02`, sistema `NetRange`, fabricante `Philco`, gravado por `argus_worker.keys.build_row` |
| Procedimento | `cd apps/fullstack/backend && TEST_DATABASE_URL=... uv run pytest tests/integration -v` |
| Situação | Aprovado nos 3 casos, em 4,64 s |
| Evidência | Bloco TI-02 de [`evidencias/testes-integracao.txt`](evidencias/testes-integracao.txt) |

| Caso | Entrada | Resultado esperado | Resultado obtido | Situação |
|---|---|---|---|---|
| TI-02.1 | `GET /api/v1/events?event_name=error&device_os=NetRange&limit=10`, com dois filtros cumulativos | HTTP 200 com exatamente esse evento; cada campo igual ao que uma consulta SQL direta lê da tabela; o bloco `query` reporta o custo real, com `scanned` maior ou igual a `returned` | 200 com 1 item; `event_name`, `session_id`, `device_id`, `app_bucket`, `device_os` e `route_path` idênticos à leitura SQL independente; relação entre `scanned` e `returned` confirmada | Aprovado |
| TI-02.2 | `GET /api/v1/events?session_id=sessao-ti02` | A resposta não contém a cadeia `usuario-ti02` em lugar nenhum; traz `user_id_hash` com os 16 hexadecimais previstos para o salt de teste; não traz a chave `user_id` | Identificador cru confirmado no banco e ausente da resposta; hash igual ao valor calculado de forma independente pelo teste; chave `user_id` ausente do item | Aprovado |
| TI-02.3 | Filtro por um sistema operacional que não existe em linha nenhuma, caso negativo | HTTP 200 com `items` vazio e `returned` igual a zero, ou seja, ausência de dado, e não falha | 200 com lista vazia e `returned` igual a zero | Aprovado |

&emsp; O caso negativo existe porque um erro 500 ali indicaria que as camadas só
conversam no caminho feliz, o que é uma forma comum de integração frágil passar
despercebida.

&emsp; Para reproduzir:

```bash
make -C apps/fullstack db-local
cd apps/fullstack/backend
TEST_DATABASE_URL=postgresql://argus:argus@localhost:55432/argus_test \
  uv run pytest tests/integration -v
```

&emsp; O alvo `make -C apps/fullstack test-backend` executa esta suíte junto com as
demais do backend.


### TI-03: worker de ingestão, fila SQS e PostgreSQL

&emsp; Este teste verifica três propriedades que não pertencem nem à fila nem ao
banco isoladamente, e sim à combinação dos dois. A mensagem válida vira linha
gravada. A mensagem inválida no mesmo lote não impede isso e termina na fila de
descarte com o motivo registrado. E a reentrega, que o SQS faz sempre que a
confirmação de processamento não chega a tempo, não duplica a linha.

&emsp; A ordem das mensagens no primeiro caso foi escolhida com cuidado. A inválida
vem antes da válida porque é a ordem que mais machuca: se o consumidor abortasse o lote ao
encontrar o erro, o evento válido seguinte nunca chegaria ao banco, e o teste com a
ordem inversa não perceberia.

| Campo | Conteúdo |
|---|---|
| Identificador | TI-03 |
| Objetivo | Verificar que a fila e o banco, juntos, gravam o válido, isolam o inválido e não duplicam na reentrega |
| Requisitos | RF01, ingestão por uma API única; RF04, rejeição rastreável do inválido; RNF04, evento inválido não impede os válidos seguintes; RNF05, não perder silenciosamente o que já foi aceito |
| Caso de uso | Um lote de eventos chega da borda com um payload malformado no meio |
| Componentes envolvidos | Fila `argus-events`, `argus_worker.consumer.EventConsumer`, `argus_worker.repository.EventRepository`, tabela `bronze.event` e a fila de descarte `argus-events-dlq` |
| Pré-condições | Banco no ar com migrations aplicadas; tabelas da camada bronze truncadas; filas SQS criadas em memória pelo `moto`; credenciais AWS falsas injetadas, para que nenhum teste alcance a nuvem real |
| Dados de entrada | Evento válido: a fixture `error.json`, exportada do BI do parceiro. Evento inválido: `{"event_name": "request"}`, sem `timestamp`, `session_id` nem `device_id` |
| Procedimento | `cd apps/fullstack/worker && TEST_DATABASE_URL=... uv run pytest tests/integration -v` |
| Situação | Aprovado nos 2 casos, em 2,57 s |
| Evidência | Bloco TI-03 de [`evidencias/testes-integracao.txt`](evidencias/testes-integracao.txt) |

| Caso | Entrada | Resultado esperado | Resultado obtido | Situação |
|---|---|---|---|---|
| TI-03.1 | Duas mensagens na fila, a inválida primeiro e a válida depois | `bronze.event` com exatamente a linha do evento válido, com `event_name`, `session_id` e `device_id` iguais ao que entrou pela fila; fila de descarte com uma mensagem, carregando o motivo da recusa; fila de entrada drenada a zero | 1 linha no banco com os três campos conferidos; 1 mensagem na fila de descarte com o atributo `FailureReason` preenchido; nenhuma mensagem restante na fila de entrada | Aprovado |
| TI-03.2 | O mesmo evento válido postado duas vezes, em ciclos separados | Uma única linha em `bronze.event` depois das duas entregas, e nada na fila de descarte | 1 linha após a primeira entrega, 1 linha após a segunda; fila de descarte vazia | Aprovado |

&emsp; Para reproduzir:

```bash
make -C apps/fullstack db-local
cd apps/fullstack/worker
TEST_DATABASE_URL=postgresql://argus:argus@localhost:55432/argus_test \
  uv run pytest tests/integration -v
```

&emsp; O alvo `make -C apps/fullstack test-worker` executa esta suíte junto com as demais
do worker.


### TI-04: ETL incremental entre bronze, silver e gold

&emsp; Este teste acompanha um valor atravessando os três estágios de armazenamento e
verifica que ele não se perde nem se deforma no caminho. Verifica também os dois
marcadores de progresso, que são o que torna a ETL incremental, e o comportamento do
pipeline em repouso.

&emsp; O valor escolhido, 412,5, é improvável de aparecer por acaso. Encontrá-lo na
camada gold prova que ele veio da linha que o teste inseriu, descartando qualquer
outra origem, o que
uma asserção sobre um valor comum como zero ou cem não conseguiria garantir.

| Campo | Conteúdo |
|---|---|
| Identificador | TI-04 |
| Objetivo | Verificar que o valor sobrevive às três camadas, que cada marcador avança na medida do que processou, e que ciclo sem dado novo não reprocessa |
| Requisitos | RF05, converter os eventos para um esquema comum; RF06, armazenar para consulta e análise posteriores |
| Caso de uso | O ciclo periódico da ETL promove o que chegou desde a última execução |
| Componentes envolvidos | `bronze.change_log`, a função `bronze.merge_todas()`, `etl.executar_bronze_silver`, `etl.executar_silver_gold`, `silver.signal_bucket`, `gold.feature_bucket` e os marcadores `etl.watermark_bronze_silver` e `etl.watermark_silver_gold` |
| Pré-condições | Banco no ar com migrations aplicadas; camadas bronze, silver, gold e etl truncadas; marcadores reiniciados para o estado semeado pela migration 015; relógio da simulação em 2026-07-12T12:00Z |
| Dados de entrada | Uma mudança em `bronze.change_log` descrevendo a inserção de um bucket de sinal da fonte `prometheus`, entidade `cdn-ti04`, métrica `p95_ms` e valor 412,5 |
| Procedimento | `cd apps/fullstack/processing && TEST_DATABASE_URL=... uv run pytest tests/integration -v` |
| Situação | Aprovado nos 3 casos, em 7,63 s |
| Evidência | Bloco TI-04 de [`evidencias/testes-integracao.txt`](evidencias/testes-integracao.txt) |

| Caso | Entrada | Resultado esperado | Resultado obtido | Situação |
|---|---|---|---|---|
| TI-04.1 | A mudança bruta em `bronze.change_log`, seguida das duas etapas da ETL | O valor 412,5 aparece em `bronze.signal_bucket`, depois em `silver.signal_bucket` e depois em `gold.feature_bucket`, com `source`, `entity` e `metric` preservados em cada salto | Valor e atributos conferidos nas três camadas, uma a uma; a etapa bronze para silver reportou sucesso e leitura até o `lsn` esperado | Aprovado |
| TI-04.2 | A mesma mudança, com inspeção dos dois marcadores antes e depois | O marcador bronze para silver passa a valer exatamente o `lsn` da última mudança lida; o marcador silver para gold para uma margem de segurança atrás do fim da janela | Marcador bronze para silver avançou para exatamente o `lsn` da mudança; marcador silver para gold igual ao fim da janela menos a margem | Aprovado |
| TI-04.3 | Um ciclo completo já executado e nenhuma mudança nova depois dele, caso negativo | A segunda execução responde `sem_pendencia` com zero linhas, e a camada gold continua com uma única linha da entidade | `sem_pendencia` com zero linhas; 1 linha em `gold.feature_bucket` para a entidade | Aprovado |

&emsp; As asserções intermediárias do primeiro caso existem para localizar em qual
travessia o dado se perderia, caso se perdesse; sem elas, um teste que falha diz
apenas que algo deu errado em algum lugar. No segundo caso, o marcador não pode
avançar nem menos, o que faria reprocessar, nem mais, o que faria pular dado; e o
marcador silver para gold deixa a margem reaberta de propósito, porque dado atrasado
ainda pode chegar nela. O terceiro caso protege contra o erro mais caro de todos num
pipeline incremental: sem ele, um ciclo ocioso somaria o mesmo evento outra vez e o
dashboard mostraria o dobro do que aconteceu.

&emsp; Para reproduzir:

```bash
make -C apps/fullstack db-local
cd apps/fullstack/processing
TEST_DATABASE_URL=postgresql://argus:argus@localhost:55432/argus_test \
  uv run pytest tests/integration -v
```

&emsp; O alvo `make -C apps/fullstack test-processing` executa esta suíte junto com as
demais do processamento.


### TI-05: a pilha publicada na AWS

&emsp; Os quatro testes anteriores rodam na máquina, e é isso que os torna
repetíveis. A contrapartida é que existem costuras do sistema que eles não alcançam
por construção, porque só existem na nuvem: a integração direta entre o API Gateway
e o SQS, sem Lambda no caminho de escrita; o Lambda authorizer, que valida o Bearer
antes de qualquer integração; a separação de audiência entre os dois tokens; e o
comportamento do pipeline assíncrono inteiro. O TI-05 existe para cobrir essas
quatro.

&emsp; O carimbo de tempo do evento merece explicação, porque contraria a intuição.
Ele é o instante virtual lido em `GET /api/v1/clock` menos um minuto, em vez da hora
da máquina. A API de leitura só mostra linha cujo `available_at` seja menor ou igual ao
instante da simulação, e no grão de sessão o `available_at` é o próprio `ts` do
evento. Um evento carimbado com a hora real ficaria invisível, e o teste falharia sem
que nada estivesse errado no sistema.

| Campo | Conteúdo |
|---|---|
| Identificador | TI-05 |
| Objetivo | Cobrir as quatro costuras que só existem na nuvem: integração direta com o SQS, Lambda authorizer, separação de audiência entre os tokens e o pipeline assíncrono completo |
| Requisitos | RF01, ingestão por uma API única; RF06, armazenar para consulta; RNF05, não perder o que já foi aceito; RNF09, acesso apenas a autorizados; RNF10, não expor dado pessoal |
| Caso de uso | Um dispositivo publica um evento na API e o operador o encontra no painel |
| Componentes envolvidos | Rota `POST /v1/events` no API Gateway, Lambda authorizer, fila SQS `argus-events`, event-worker no ECS Fargate, tabela `bronze.event` no RDS, ETL de bronze para silver, tabela `silver.session_event` e a rota `GET /api/v1/events` em Lambda |
| Pré-condições | Pilha publicada e no ar; `ARGUS_INGEST_URL`, `ARGUS_API_URL`, `ARGUS_INGEST_TOKEN` e `ARGUS_READ_TOKEN` no ambiente; event-worker e ETL em execução. Faltando qualquer uma, o teste é pulado, e não quebrado |
| Dados de entrada | Um evento de erro único por execução, na sessão `ti05-` seguida de identificador aleatório, carimbado um minuto atrás do instante virtual lido em `GET /api/v1/clock` |
| Procedimento | `cd apps/fullstack/backend && uv run pytest tests/integration/test_implantacao.py -v -rs`, com o `.env` carregado no ambiente |
| Situação | 1 caso aprovado e 1 reprovado, em 310 s |
| Evidência | Bloco TI-05 de [`evidencias/testes-integracao.txt`](evidencias/testes-integracao.txt), com a saída do pytest e as medições de cada fronteira |

| Caso | Entrada | Resultado esperado | Resultado obtido | Situação |
|---|---|---|---|---|
| TI-05.1 | Quatro requisições à mesma rota de leitura: sem token; com token de forma válida e valor desconhecido; com o token da audiência errada, o de ingestão; e com o token correto | As três primeiras recusadas com 401 ou 403 pelo authorizer, antes de alcançarem a Lambda da aplicação; a quarta responde 200 com o corpo do relógio | As três recusadas; a quarta com 200 e o campo `sim_now` presente | Aprovado |
| TI-05.2 | Evento enviado por `POST /v1/events` com o token de ingestão, seguido de consulta repetida a `GET /api/v1/events?session_id=...` até aparecer ou esgotar o prazo de 300 s | A borda aceita com 2xx e o evento aparece na leitura dentro do prazo, com `event_name` e `device_id` preservados e sem `user_id` na resposta | A borda aceitou e o evento foi gravado no banco, mas não apareceu na leitura em 300 s, ao longo de 29 tentativas | Reprovado |

&emsp; O primeiro caso é o tipo de asserção que nenhum teste local consegue fazer,
porque o authorizer só existe na borda do API Gateway e o Flask local roda sem ele.
O segundo reprovou, e a subseção a seguir explica por quê.

&emsp; Uma observação sobre o alcance do TI-05.2, porque um evento só costuma ser
amostra fraca demais para sustentar conclusão. Aqui ele não sustenta nenhuma sozinho:
o que o caso prova é que aquele evento não atravessou em 300 s. A afirmação geral
sobre frescor, a de que hoje ele se mede em horas, vem do acúmulo medido no
diagnóstico: 115.971.059 linhas na bronze contra uma vazão de cerca de 185.000 por
hora, observada em cinco ciclos consecutivos. Isso é um limite calculado, que independe de quantos
eventos o teste envie. O evento único serve para localizar em que ponto o pipeline parou,
não para estimar quanto ele demora.

#### Diagnóstico do caso reprovado

&emsp; A reprovação foi investigada instrumentando cada fronteira do pipeline, em vez
de se supor uma causa. O resultado é que o evento não se perdeu em lugar nenhum: ele
atravessou quatro das cinco fronteiras e parou na quinta.

| Fronteira | Como foi medida | Resultado |
|---|---|---|
| Cliente, API Gateway e authorizer | O próprio caso TI-05.1 | Atravessou |
| API Gateway e fila SQS | Código de resposta do `POST` | Atravessou, com 2xx |
| Fila SQS e event-worker | Métrica `MessagesReceived` no CloudWatch e profundidade das quatro filas | Atravessou: 1 mensagem recebida, filas e fila de descarte vazias |
| event-worker e `bronze.event` | Métrica `ItemsWritten` no CloudWatch | Atravessou: 1 item gravado no mesmo minuto do `POST` |
| `bronze.event` e `silver.session_event` | Log do serviço `processing` e avanço do marcador | Parou aqui |
| `silver.session_event` e `GET /api/v1/events` | Consulta direta com janela ampla e explícita | Não alcançado: zero itens, `scanned` igual a zero |

&emsp; A explicação está em como a ETL é incremental. Cada linha que entra na camada
bronze recebe um número de ordem, o `lsn`. A ETL guarda um marcador dizendo até que
`lsn` já processou, lê um lote a partir dali em cada ciclo e avança o marcador ao
terminar. É isso que impede reprocessar o que já foi feito, e é isso que coloca um
evento recém-chegado numa fila atrás de tudo que ainda não foi processado.

| Grandeza | Valor |
|---|---:|
| Linhas gravadas na bronze pelo serviço de carga em 14 de setembro | 115.971.059 |
| Marcador da ETL no momento do diagnóstico | `lsn` 28.404.255 |
| Linhas ainda por processar | cerca de 87.500.000 |
| Ritmo medido em cinco ciclos consecutivos | 50.000 linhas a cada 16,2 min |
| Vazão equivalente | cerca de 185.000 linhas por hora |
| Estimativa para o marcador alcançar o evento | cerca de 470 h, perto de 20 dias de execução contínua |

&emsp; O evento do teste recebeu um `lsn` na ponta da sequência, atrás de 87 milhões
de linhas. O prazo de 300 s, portanto, errou por um fator de aproximadamente 5.700, e
nenhum prazo razoável funcionaria. Aumentá-lo para horas produziria um teste que
ninguém roda, o que equivale a desligar o alarme em vez de atender ao chamado. O
prazo ficou como está. Como o laboratório encerra as tarefas do ECS ao fim da sessão,
o tempo de calendário seria ainda maior que a estimativa.

#### A correção que o diagnóstico produziu

&emsp; Investigar por que cada ciclo leva dezesseis minutos para processar cinquenta
mil linhas levou a um defeito de schema, e não apenas a uma lentidão operacional.
Duas funções da ETL filtram a tabela `bronze.event` pela coluna `_lsn`: a
`etl.proxima_faixa_lsn`, que decide a faixa de cada ciclo, e a
`silver.build_session_event`, que faz a promoção. A tabela é particionada por `ts` e
não tinha índice algum em `_lsn`, de modo que não há poda de partição possível, por
ser outra a chave de particionamento, nem índice a usar. O plano resultante é uma
varredura sequencial de todas as partições, duas vezes por ciclo, com custo
proporcional ao tamanho da tabela em vez de proporcional ao tamanho do lote.

&emsp; Vale a comparação com `bronze.change_log`, que nasceu certa: ela tem
`PRIMARY KEY (lsn)` e é particionada por `lsn`, de modo que a mesma consulta ali é
poda de partição seguida de leitura por índice.

| Situação | Plano de execução | Tempo, com 300 mil linhas |
|---|---|---:|
| Sem índice em `_lsn` | Varredura sequencial de todas as partições, com 250.000 linhas descartadas pelo filtro | 48,7 ms |
| Com índice em `_lsn` | Leitura por índice sem acesso à tabela, com `Heap Fetches` igual a zero | 12,6 ms |

&emsp; Mais importante que o ganho de quatro vezes nesse volume é o que acontece com
a forma do custo: a varredura cresce com a tabela, e a leitura por índice
cresce com o que se pede. A correção está na migration
[`030_indice_lsn_em_evento.sql`](../apps/fullstack/db/migrations/030_indice_lsn_em_evento.sql).

&emsp; Ela vem acompanhada do teste
[`test_plano_da_etl.py`](../apps/fullstack/processing/tests/test_plano_da_etl.py), que
verifica o plano de execução, deixando o tempo de relógio de fora. Medir tempo em
teste produz
um portão instável, que reprova consulta correta em máquina carregada e acaba
ignorado por todos. O teste popula a tabela com `_lsn` descorrelacionado de `ts`, que
é o caso real, e exige que nenhuma partição seja varrida sequencialmente. Foi
verificado nos dois sentidos: falha nos três casos quando o índice não existe e passa
quando ele existe.

&emsp; Uma ressalva de honestidade: não é possível afirmar que esse índice explica os
dezesseis minutos inteiros. O `EXPLAIN` contra a tabela real exigiria acesso ao RDS,
que não é acessível de fora, e as agregações das outras duas funções de construção
também podem pesar. O que está demonstrado é o defeito estrutural e a direção da
correção.

#### O que este resultado diz sobre o sistema

&emsp; O primeiro achado é que o frescor de ponta a ponta da implantação se mede hoje
em horas, e que o limite está na ETL. A fila não tem responsabilidade nisso. A ingestão faz
sua parte em segundos: aceita, enfileira, consome e grava. O relatório de carga
registra uma amostra de frescor de 38 minutos e 32 segundos, e a situação medida aqui
é pior que aquela amostra.

&emsp; O segundo é que a tabela `silver.session_event` está vazia na implantação,
conforme mostra o `scanned` igual a zero mesmo com janela ampla. O serviço `simulator`
está com zero tarefas, de modo que não há quem publique evento de sessão, e o evento
do teste é o único do sistema. As telas continuam funcionando porque consomem as
tabelas da camada gold, alimentadas pela carga histórica do parceiro.

&emsp; Sobre o acúmulo já existente, cabe registrar o que a documentação do projeto
não diz. Existe o alvo `make etl`, que executa `gold.rebuild_tudo()`, um recompute
completo e idempotente da silver e da gold a partir da bronze, numa chamada só em vez
de lotes de cinquenta mil. Ele exige `DATABASE_URL` e, como o RDS não é acessível de
fora, roda de dentro da VPC ou por túnel. Nenhum artefato do repositório estabelece
qual dos dois caminhos é o previsto depois de uma carga em massa; pelo contrário, o
[`plano-argus-v3.md`](plano-argus-v3.md) descreve o recompute completo como o que
existia até a migration 015, que introduziu a ETL incremental por marcador. Qual usar
é uma decisão operacional em aberto, e este relatório apenas a aponta. Nenhuma ação
foi tomada sobre a infraestrutura durante este trabalho.

&emsp; Por fim, vale notar o que falta de instrumentação. Não existe métrica de
distância entre o marcador e a ponta da sequência. Se existisse, o acúmulo teria
aparecido em 14 de setembro, no dia da carga, em vez de esperar um teste de
integração três dias depois.

#### Segredo e evidência

&emsp; Nenhum endpoint, identificador de conta ou token aparece neste artefato nem na
evidência. O teste lê todos eles do
ambiente, sua função `_falha_sem_vazar` impede que uma mensagem de falha os imprima,
e a saída capturada passou por filtro de redação antes de ser versionada. O token de
leitura não é recuperável da AWS, que guarda apenas o seu SHA-256; o de ingestão
volta com `make auth-show-ingest`.

&emsp; Para reproduzir:

```bash
# 1. renovar a sessão do Learner Lab e atualizar ~/.aws/credentials (profile g4)
make -C apps/fullstack env               # reescreve as URLs a partir do Terraform
make -C apps/fullstack auth-show-ingest  # recupera o token de ingestão

# 2. exportar os dois tokens (o de leitura é o que se cola no painel)
export ARGUS_INGEST_TOKEN=...
export ARGUS_READ_TOKEN=...

# 3. rodar
cd apps/fullstack/backend
set -a && . ../.env && set +a
uv run pytest tests/integration/test_implantacao.py -v -rs
```

### Execução das suítes

&emsp; Para confirmar que os testes novos não quebraram nada, e que a migration do
índice não alterou comportamento, todas as suítes do repositório foram executadas na
mesma sessão de trabalho.

| Suíte | Comando | Resultado |
|---|---|---|
| Worker de ingestão | `make -C apps/fullstack test-worker` | 77 aprovados |
| Simulador | `make -C apps/fullstack test-simulator` | 2 aprovados |
| Processamento e ETL | `make -C apps/fullstack test-processing` | 72 aprovados |
| API de leitura | `make -C apps/fullstack test-backend` | 227 aprovados, 2 pulados |
| Autorizador | `make -C apps/fullstack test-authorizer` | 18 aprovados |
| Frontend, contratos e componentes | `make -C apps/fullstack test-frontend` | 24 aprovados |
| Frontend integrado, com Playwright | `make -C apps/fullstack test-frontend-e2e` | 12 aprovados |
| Pilha publicada, o TI-05 | `uv run pytest tests/integration/test_implantacao.py` | 1 aprovado, 1 reprovado |
| Manifests do Kubernetes | `make -C apps/fullstack k8s-validate` | 5 conjuntos renderizados sem erro |

&emsp; São 432 testes aprovados nas suítes que rodam sem credencial de nuvem, mais o
TI-05, que executado com credencial aprovou um caso e reprovou outro. Os 227 do
backend incluem os 63 testes unitários do backend e os 3 casos do TI-02. Os 2
pulados naquela linha são justamente os casos do TI-05, que ficam de fora quando
`make test-backend` roda sem os tokens da pilha publicada, e por isso o TI-05 tem
linha própria na tabela.

&emsp; A última linha não entra nessas contagens, porque não é uma suíte de casos: o
alvo `k8s-validate` renderiza os cinco conjuntos de manifests (`base`, `migrate`,
`overlays/aws`, `overlays/kind` e `overlays/kind/migrate`) sem contactar cluster
nenhum, e existe para que um erro de YAML não chegue à entrega. Ele entrou no
`make check` junto com os manifests e é, hoje, a única verificação automatizada que
toca no caminho do Kubernetes. Execução registrada em
[`evidencias/k8s-validate.txt`](evidencias/k8s-validate.txt).

&emsp; Uma observação de ambiente, registrada por honestidade de relatório: o alvo
`test-authorizer` interrompe a coleta com `NoRegionError` quando a variável
`AWS_REGION` não está definida no terminal. Não é defeito do código nem efeito dos
testes de integração, e com `AWS_REGION=us-east-1` no ambiente os 18 testes passam,
como registrado na tabela. O valor sai do `.env` na operação normal do projeto.

&emsp; Uma segunda observação da mesma natureza: numa cópia recém-clonada do
repositório o `k8s-validate` falha, e a falha não é de manifesto.
O overlay `kind` gera o seu Secret a partir de `k8s/overlays/kind/secret.env`, que
está no `.gitignore` por ser credencial, ainda que de um banco descartável, e
precisa ser criado antes:

```bash
cp apps/fullstack/k8s/overlays/kind/secret.env.example \
   apps/fullstack/k8s/overlays/kind/secret.env
```

&emsp; Com o arquivo no lugar, os cinco conjuntos renderizam. Sem ele, o alvo para no
terceiro com `evalsymlink failure`. Como o `k8s-validate` é portão do `make check`, e
como esse passo não está no runbook de nenhum artefato, fica registrado aqui: é o
tipo de detalhe que transforma um portão de qualidade em falha de CI no primeiro
ambiente limpo em que ele rodar.

### Cobertura do caminho orquestrado por Kubernetes

&emsp; Os testes iniciais deste artefato foram executados em 17 e 18 de setembro de
2026, na mesma janela em que o caminho síncrono, com dashboard, API de leitura e
migrations, passou a ser orquestrado por Kubernetes, conforme
[`conteineres-final.md`](conteineres-final.md). Em 21 de setembro, os testes
alcançaram também o Ingress do EKS, permitindo separar o que foi medido no grupo
de auto scaling, no cluster local e no cluster publicado.

&emsp; O caminho assíncrono segue intacto. Ingestão, ETL, simulação e carga inicial
continuam em ECS Fargate porque assim foi decidido, e a razão está documentada: o
Learner Lab nega `iam:CreateOpenIDConnectProvider` e `eks-auth:AssumeRoleForPodIdentity`,
o que torna IRSA e Pod Identity impossíveis e tira do cluster a única vantagem que ele
teria ali. O TI-03 e o TI-04 medem a pilha que está no ar. O TI-05.2 também foi
executado na pilha publicada, mas reprovou; sua correção ainda não foi reconfirmada
remotamente.

&emsp; O caminho síncrono é onde a cobertura ficou para trás. A tabela separa o
que foi medido do que não foi, nos três estados usados no restante do artefato.

| Afirmação | Plataforma em que foi medida | Estado quanto ao EKS |
|---|---|---|
| Carga da API de leitura nos três níveis | ALB e grupo de auto scaling, 2 instâncias `t4g.small` | Executado também no cluster em 21/09; ver [Rodada no cluster](#rodada-no-cluster-kubernetes) |
| Elasticidade sob carga | Target tracking em 60 requisições por instância por minuto | Tentado no cluster e impossível de medir: o HPA ficou sem métrica de CPU durante toda a rodada |
| Contrato entre dashboard e API, o TI-01 | Duas origens, com CORS | Executado em origem única no cluster local, 3 casos aprovados |
| Autorização na borda, o TI-05.1 | API Gateway e Lambda authorizer | Não se aplica: o Ingress não passa pelo authorizer |
| Manifests do cluster | `kubectl kustomize`, sem cluster | Executado, sem erro |
| Sondas, implantação sem queda e autocura | Cluster `kind` local | Executado, e registrado na seção 5 de [`conteineres-final.md`](conteineres-final.md), não aqui |

&emsp; A última linha pede duas notas, porque é a que mais facilmente seria lida com
força maior do que tem. A separação das três sondas foi mesmo observada em operação:
a de vida passava enquanto a de prontidão reprovava, com o pod fora do balanceamento
e sem reinício, até o `Job` de migrations concluir. Já as duas medições citadas ali,
as 547 respostas sem falha durante um `rollout restart` e a recuperação de um pod em
4 s, saíram do cluster local. O overlay `kind` aplica os mesmos manifests do overlay
da AWS, mudando apenas o banco e a classe do Ingress, de modo que os números seguem
valendo como demonstração do mecanismo. Ainda assim, o valor de 4 s nunca foi medido
contra o Auto Mode, e a comparação com os 300 s do `health_check_grace_period` do
grupo de auto scaling carrega essa ressalva.

&emsp; Nada disso torna a rodada original obsoleta. O `create_eks` é `false` por padrão
no [`variables.tf`](../apps/fullstack/infra/variables.tf), porque o cluster cobra por
hora existindo, e o `terraform.tfvars` do repositório mantém o grupo de auto scaling
em duas instâncias: esse continua sendo o caminho que sobe por padrão. A rodada de
21 de setembro fechou a comparação de desempenho contra o Ingress. O que permanece
pendente é repetir o ensaio com o `metrics-server` instalado, para medir a
elasticidade do HPA em vez do limite das duas réplicas iniciais.

## Testes de carga

### O que esta seção verifica

&emsp; As duas seções anteriores perguntam se o sistema responde certo. Esta
pergunta se ele continua respondendo certo, e em quanto tempo, quando muita gente
usa o dashboard ao mesmo tempo. O alvo são as operações disponíveis pela interface:
cada uma das seis telas operacionais, ao abrir, dispara um conjunto de consultas à
API de leitura, e é exatamente esse conjunto, com os mesmos parâmetros que o
frontend envia, que o teste reproduz. Não se testa a ingestão de eventos aqui, que
já foi coberta pelos ensaios de RNF01 e RNF03 em
[`testes-carga-inicial.md`](testes-carga-inicial.md); testa-se o caminho que o
operador sente.

&emsp; Foram executados três níveis progressivos de carga, com 5, 25 e 100 usuários
simultâneos, contra a pilha publicada na AWS. Houve duas rodadas. A primeira, gerada
da máquina de desenvolvimento, encontrou um defeito de configuração entre o
balanceador e o servidor de aplicação, que produzia um erro a cada poucas dezenas de
segundos em qualquer nível de carga. O defeito foi corrigido e implantado, e a segunda
rodada, gerada de dentro da própria AWS, é a oficial: 25.501 requisições de carga,
mais uma requisição de setup para obter o relógio virtual (25.502 no total), nenhuma
falha, e o percentil 95 abaixo de 1 s mesmo com 100 usuários.

### Vocabulário usado nesta seção

&emsp; **Usuário virtual, ou VU**, é a unidade de carga do k6: um laço que abre uma
tela, espera um pouco e abre a próxima, como faria uma pessoa. Cem VUs são cem
pessoas navegando ao mesmo tempo, não cem requisições por segundo.

&emsp; **Tempo de pensar**, do inglês think time, é a pausa entre uma tela e a
seguinte. Sem ela, cada VU seria um laço apertado contra a API e a medida deixaria de
representar uso humano. Aqui são 2 s, e o valor está registrado porque muda o
volume: quanto menor a pausa, mais requisições por usuário.

&emsp; **p50, p95 e p99** são percentis do tempo de resposta. Um p95 de 802 ms
significa que 95% das requisições foram respondidas em até 802 ms; o p99 olha para o
1% mais lento. O percentil diz mais do que a média, porque a média esconde a cauda
que o usuário percebe.

&emsp; **ALB**, de Application Load Balancer, é o balanceador da AWS que recebe a
requisição do dashboard e a distribui entre as instâncias EC2 que rodam a API. O
**grupo de auto scaling**, ou ASG, é o conjunto dessas instâncias, com uma política
de **target tracking**: uma meta de requisições por instância por minuto, acima da
qual o grupo cresce e abaixo da qual encolhe.

&emsp; **HTTP 502**, ou bad gateway, é a resposta que um intermediário dá quando não
consegue uma resposta válida de quem está atrás dele. Quando quem emite o 502 é o
próprio balanceador, e não a aplicação, o problema está na conversa entre os dois.

&emsp; **Keep-alive** é a reutilização de uma conexão TCP para várias requisições
seguidas. Balanceador e servidor precisam concordar sobre quanto tempo uma conexão
ociosa fica aberta; se o servidor a fecha antes do balanceador, a próxima requisição
que o balanceador tenta enviar por ela falha com 502.

### Ferramenta e método

| Item | Valor |
|---|---|
| Ferramenta | k6 0.54.0. Na rodada oficial, o binário Linux arm64 instalado numa EC2 descartável; na primeira rodada, a imagem `grafana/k6:0.54.0` em Docker na máquina de desenvolvimento |
| Roteiro | [`apps/fullstack/tests/carga/carga_ui.js`](../apps/fullstack/tests/carga/carga_ui.js) |
| Modelo de usuário | Cada iteração abre uma tela: dispara em paralelo, como o navegador, as rotas que aquela tela consome, espera todas, registra o tempo total da tela, e pausa 2 s. As seis telas se alternam em rodízio |
| Janelas de tempo | Relativas ao relógio virtual `sim_now`, lido em `GET /api/v1/clock` no início do teste, como o frontend faz; janelas de 3 h para Timeline, Comparar e Hipóteses e de 24 h para Explorar, que são os períodos padrão das telas |
| Gerador de carga | EC2 `t4g.small` na sub-rede pública da VPC do projeto, criada por [`gerador_ec2.sh`](../apps/fullstack/tests/carga/gerador_ec2.sh) só para a rodada e encerrada ao fim dela |
| Data da rodada oficial | 18 de setembro de 2026, das 17:50 às 17:57 UTC |
| Identificador | `carga-ui-ec2-20260918T174857Z` |

&emsp; O gerador roda dentro da AWS por uma razão prática: carga sustentada saindo de
um endereço residencial contra um endpoint da AWS tem a assinatura de um ataque de
negação de serviço, e contas de laboratório já foram suspensas por isso. Saindo de
uma instância da própria conta, o tráfego é interno à nuvem e a origem é
identificável. O script cria a instância sem nenhuma porta de entrada, entrega a ela
os roteiros por um bucket privado e o token por um parâmetro criptografado do
Systems Manager, espera o resultado voltar ao bucket e apaga tudo o que criou,
inclusive a instância. Um efeito colateral bem-vindo é que a medida deixa de conter
a latência da internet entre a casa do operador e a AWS.

&emsp; As rotas de cada tela foram levantadas no código do frontend, em vez de
escolhidas à mão, para que o teste meça o que o dashboard realmente pede. A tabela abaixo é o
que uma abertura de tela custa à API.

| Tela | Rotas disparadas ao abrir | Requisições |
|---|---|---|
| Agora | `clock`, `series/facets` com os quatro campos de escopo, `signals` | 3 |
| Timeline | `clock`, `timeline` na janela de 3 h | 2 |
| Comparar | `clock`, `series/timeseries` da janela atual e da mesma janela uma semana antes, `changes` | 4 |
| Explorar | `clock`, `series/facets`, `series/breakdown` por métrica, `series/timeseries` de 24 h em passos de 5 min, `series/breakdown` por dispositivo em sessões e em taxa de erro | 6 |
| Recorte | `clock`, `series/facets`, `series/crosstab` entidade por hora com duas métricas, `events` filtrado por erro | 4 |
| Hipóteses | `clock`, `hypotheses` na janela de 3 h | 2 |

&emsp; Uma tela conta como completa apenas se todas as suas rotas responderem 200. É
uma medida mais dura do que a taxa de erro por requisição, e é a que importa para o
operador: uma consulta em quatro que falha é uma tela quebrada, não 25% de sucesso.

### Ambiente

&emsp; A URL de leitura que o dashboard consome, e que `make env` grava no `.env`, é
a do ALB, e por isso o caminho testado é o do grupo de auto scaling, não o da Lambda
descrita no TI-05. Os dois existem na pilha; o ALB é o preferido quando está no ar.

&emsp; Desde a Sprint 4 existe um terceiro caminho para a mesma API, o Ingress do
cluster EKS, e ele não foi exercitado nesta rodada. A distinção não é formal, e é
por isso que ela aparece aqui e não numa nota de rodapé: no grupo de auto scaling a
escala é disparada por requisições por instância por minuto, medida que o ALB publica;
no cluster, pelo HPA por uso de CPU. São gatilhos diferentes, com tempos de reação
diferentes, e os números desta seção descrevem o primeiro. O `make env` também não
conhece o Ingress: ele lê o `api_url_alb` do Terraform e, na falta dele, cai para a
Lambda. Rodar a carga contra o cluster exige apontar `ARGUS_API_URL` à mão para a
saída de `make k8s-url`. A [tabela de cobertura](#cobertura-do-caminho-orquestrado-por-kubernetes)
na seção de integração reúne o que ficou de fora.

| Componente | Configuração durante a rodada oficial |
|---|---|
| Balanceador | ALB com `idle_timeout` de 60 s e health check a cada 30 s |
| Aplicação | 2 instâncias EC2 `t4g.small`, imagem `08a827b72de8`, cada uma com o Flask servido por gunicorn com 2 workers de 4 threads e `--keep-alive 75` |
| Auto scaling | Mínimo 2, máximo 6, target tracking em 60 requisições por instância por minuto, aquecimento de 300 s |
| Banco | RDS PostgreSQL 16, `db.t3.medium`, lido pelo usuário `argus_api` através das views `v_*` |
| Gerador de carga | EC2 `t4g.small`, Amazon Linux 2023 arm64, na mesma VPC |

### Níveis de carga e critérios de sucesso

&emsp; Os três níveis rodam em sequência no mesmo processo, com 2 min cada e 30 s de
pausa entre eles, para que a API volte ao repouso antes do degrau seguinte. O
volume de requisições decorre do número de usuários e do tempo de pensar, em vez de
ser fixado de antemão. Por isso ele aparece na tabela como medida, com o valor que a
execução produziu.

| Nível | Usuários simultâneos | Duração | Telas abertas | Requisições | Vazão média |
|---|---:|---:|---:|---:|---:|
| 1 | 5 | 2 min | 295 | 1.040 | 8,7 req/s, 520 req/min |
| 2 | 25 | 2 min | 1.479 | 5.208 | 43,4 req/s, 2.604 req/min |
| 3 | 100 | 2 min | 5.536 | 19.253 | 160,4 req/s, 9.627 req/min |
| Total | | 7 min 20 s | 7.310 | 25.501 | |

&emsp; Os critérios de sucesso, declarados no roteiro como limiares que o k6 avalia
sozinho e reprova a execução se não forem atendidos, foram estes, por nível:

| Critério | Limite | Origem |
|---|---|---|
| Taxa de erro por requisição | Menor que 1% | Prática comum para leitura interna |
| p95 do tempo de resposta por requisição | Menor que 3 s | RNF02, com margem |
| p99 do tempo de resposta por requisição | Menor que 5 s | RNF02, o limite do requisito |
| p95 do tempo para abrir a tela inteira | Menor que 5 s | RNF02 aplicado ao que o operador vê |
| Telas completas | Mais de 99% | Toda rota da tela com 200 |

### Resultados

| Nível | Usuários | Erros | p50 | p95 | p99 | Máximo | Tela p95 | Telas completas | Situação | Ressalva |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| 1 | 5 | 0 de 1.040 | 9 ms | 94 ms | 278 ms | 889 ms | 157 ms | 100% | Aprovado | O p95 inclui o aquecimento das instâncias e é maior que o do nível 2 |
| 2 | 25 | 0 de 5.208 | 9 ms | 96 ms | 309 ms | 548 ms | 148 ms | 100% | Aprovado | — |
| 3 | 100 | 0 de 19.253 | 23 ms | 802 ms | 1.302 ms | 1.656 ms | 964 ms | 100% | Aprovado | O auto scaling disparou, mas não entrou em serviço dentro da janela: os 100 usuários foram atendidos pelas duas instâncias originais |

&emsp; A coluna de ressalva cumpre uma função. Um "Aprovado" sozinho sugeriria que
o sistema absorveu 100 usuários com a elasticidade funcionando, quando o que se
mediu foi outra coisa: as duas instâncias originais deram conta por conta própria.
A afirmação fica mais fraca e, ao mesmo tempo, mais interessante. A análise adiante
desenvolve as duas ressalvas.

&emsp; Nenhum dos três níveis chegou perto de reprovar, e é por isso que eles não
dizem onde fica o teto. O maior p95 observado, 802 ms, está a um sexto do limite de
5 s do RNF02, e a CPU da aplicação não passou de 12%. Saber que o sistema aguenta
muito mais do que precisa ainda deixa em aberto quanto ele aguenta, e para responder
isso é
preciso um degrau que reprove, e a conclusão desta seção registra isso como lacuna.

&emsp; Por tela, o p95 do tempo de abertura em cada nível mostra onde a carga pesa:

| Tela | Nível 1, 5 usuários | Nível 2, 25 usuários | Nível 3, 100 usuários |
|---|---:|---:|---:|
| Agora | 859 ms | 470 ms | 662 ms |
| Timeline | 56 ms | 16 ms | 46 ms |
| Comparar | 14 ms | 25 ms | 187 ms |
| Explorar | 111 ms | 108 ms | 977 ms |
| Recorte | 168 ms | 276 ms | 1.372 ms |
| Hipóteses | 63 ms | 21 ms | 899 ms |

&emsp; Do lado do servidor, o CloudWatch registrou na mesma janela: nenhuma resposta
5xx, nem do balanceador nem das instâncias; nenhum erro de conexão com os alvos;
duas respostas 4xx das instâncias às 17:55 UTC que o k6 não viu, já que registrou
zero respostas fora de 200, e que portanto vieram de outro cliente; tempo de
resposta dos alvos com p95 entre 56 e 888 ms; 14 conexões constantes no RDS; CPU do
banco de 33% em repouso ao pico de 73% no nível 3; CPU média das instâncias EC2 de
3% nos dois primeiros níveis e 8% no terceiro, com máximo de 12%.

### Análise

&emsp; Até 25 usuários a carga é invisível. O p50 é de 9 ms nos dois primeiros
níveis e o p95 fica abaixo de 100 ms; a CPU das instâncias não sai de 3%. Para o
tamanho de equipe que um dashboard interno atende, este é o regime de operação, e
ele tem duas ordens de grandeza de folga.

&emsp; Com 100 usuários o banco passa a ser o gargalo. O p95 sobe para 802 ms e
as telas que mais agregam, Recorte, Explorar e Hipóteses, são as que mais sentem: um
crosstab de mil células, breakdowns de 24 h e o relatório de hipóteses. A CPU do RDS
vai a 73% enquanto a das instâncias EC2 fica em 8%, o que diz que o próximo recurso a
esgotar é o banco, não a aplicação, e que mais instâncias no grupo não ajudariam
neste ponto: ajudaria índice, cache ou uma classe maior de RDS. Os tempos continuam
dentro do critério, com o p99 em 1,3 s contra um limite de 5 s.

&emsp; A tela Agora tem uma cauda que não vem da carga. Seu p95 de 859 ms no
nível 1 é maior que nos níveis 2 e 3. O nível 1 é o primeiro do teste e captura o
aquecimento das duas instâncias, recém-substituídas pelo rollout, com o plano das
consultas ainda por entrar em cache. O máximo do nível 1, 889 ms, é essa mesma
primeira abertura. Um degrau de aquecimento antes do primeiro nível removeria o
efeito.

&emsp; O auto scaling disparou, mas chegou depois do teste. Com 9.627
requisições por minuto sobre duas instâncias, a média passou de 4.800 por alvo, oitenta
vezes a meta de 60. O alarme entrou em estado de alerta às 17:55:56 UTC, e a
capacidade desejada foi de 2 para 6; as quatro instâncias novas ainda estavam em
aquecimento quando o nível 3 terminou. Os 100 usuários foram atendidos pelas duas
instâncias originais, o que reforça que a aplicação tinha folga. Para um degrau de
2 min a elasticidade não tem tempo de agir; para um turno de operação, teria.

#### A primeira rodada e o defeito que ela encontrou

&emsp; A rodada de 17 de setembro, gerada da máquina de desenvolvimento contra a
mesma pilha e com o mesmo roteiro, terminou com 24.614 requisições e 23 falhas,
0,09%. Os tempos já cumpriam o critério, com p95 de 248, 365 e 528 ms nos três
níveis, mas as falhas tinham uma distribuição estranha: 9 no nível 1, 9 no nível 2 e
5 no nível 3. Uma falha causada por carga faria o inverso.

&emsp; O CloudWatch explicou. O contador `HTTPCode_ELB_502_Count` do balanceador
marcou exatamente 23 na janela, entre 1 e 5 por minuto do início ao fim, enquanto o
contador de 5xx originados pelas instâncias ficou vazio: a aplicação nunca respondeu
erro. O mecanismo estava na configuração: o gunicorn com threads fechava uma conexão
ociosa depois de 2 s, o seu padrão de keep-alive, e o ALB mantinha a sua por 60 s.
Quando o balanceador reutilizava uma conexão que o servidor acabara de fechar, a
requisição morria em 502 antes de chegar ao Flask. A própria AWS documenta esse
cenário e recomenda que o servidor mantenha a conexão por mais tempo que o
balanceador.

&emsp; A correção é uma linha no comando do gunicorn, `--keep-alive 75`, no
[`Dockerfile`](../apps/fullstack/backend/Dockerfile) do backend. Ela foi publicada como a
imagem `08a827b72de8` e implantada no grupo de auto scaling substituindo as
instâncias, sempre com duas saudáveis no balanceador. A substituição foi manual,
subindo a capacidade desejada para quatro e encerrando as duas antigas depois, e
isso revela um ponto do `asg.tf` a corrigir: o grupo aponta o launch template para
`$Latest`, e com esse valor o provider do Terraform não dispara o instance refresh
quando uma versão nova é publicada, ao contrário do que o comentário do arquivo
supõe; o refresh manual, por sua vez, é negado por política no Learner Lab. A rodada
oficial é a prova de que a correção funcionou: mesma carga, zero 502.

&emsp; Comparando as duas rodadas, os tempos da segunda são menores nos níveis 1 e 2,
com p95 de 94 e 96 ms contra 248 e 365 ms, porque o gerador dentro da VPC não paga a
latência da internet. No nível 3 a segunda é mais lenta, com p95 de 802 ms contra
528 ms, e o banco estava mais ocupado desde antes do teste, com 33% de CPU em
repouso contra 24% na véspera, provavelmente porque o processamento recém-reimplantado
estava a recuperar o atraso da ETL. A comparação direta entre as rodadas é
portanto indicativa; a medida que vale é a da rodada oficial.

### Conclusão

&emsp; A API de leitura atende, com margem, ao RNF02 nos três níveis testados: o
tempo de resposta ficou abaixo de 1,7 s em todas as 25.501 requisições de carga, contra um
limite de 5 s; nenhuma requisição falhou; e o p95 para abrir uma tela inteira ficou em
964 ms com 100 usuários simultâneos. A carga do nível 3, 9.627 requisições por
minuto, é várias vezes maior que a expectativa de uso de um dashboard interno, e o
sistema a absorveu com duas instâncias pequenas e CPU ociosa.

&emsp; O único defeito encontrado foi de configuração, e foi corrigido e comprovado
dentro do mesmo trabalho: o desencontro de keep-alive entre o gunicorn e o ALB, que
custava de um a cinco 502 por minuto em qualquer nível de carga. O próximo ensaio deve
incluir um degrau de aquecimento antes do primeiro nível e um nível 3 mais longo, de
10 min, para que o auto scaling entre em serviço dentro da janela medida e a
elasticidade chegue a ser observada em operação, e não apenas disparada. Deve,
também, ser repetido
contra o Ingress do cluster: é a única forma de comparar as duas maneiras de escalar
a mesma API, já que uma reage a requisições por instância e a outra a uso de CPU. Se
a carga real um dia se aproximar de 100 usuários simultâneos, o recurso a dimensionar
é o banco.

&emsp; Duas lacunas desta rodada ficam registradas, e nenhuma delas é achado: são
coisas que não foram feitas.

&emsp; O teto não foi procurado nesta rodada. Os três níveis foram escolhidos por
parecerem representativos do uso, e todos passaram com folga larga. Um ensaio que
quer afirmar capacidade precisa de pelo menos um degrau que reprove algum critério.
Sem isso o relatório afirma "aguenta 100 usuários", o que é verdade, e deixa quem lê
imaginando se o número seguinte seria 120 ou 12.000. A lacuna foi fechada em 21 de
setembro, contra o cluster, e o resultado está na seção
[Rodada no cluster Kubernetes](#rodada-no-cluster-kubernetes).

&emsp; Não há captura de painel. Todos os números desta seção vêm do resumo do k6
e de leituras do CloudWatch transcritas em texto. O repositório versiona um painel
feito exatamente para esta medição,
[`observability/grafana/dashboards/argus-k6.json`](../apps/fullstack/observability/grafana/dashboards/argus-k6.json),
servido por `make observabilidade-up`, e ele não foi usado. As duas formas de
evidência cumprem papéis distintos: o número transcrito pode ser conferido contra a
saída bruta, enquanto a imagem do painel mostra a forma da curva, que é o que
denuncia degrau, serrilha e saturação. Uma não substitui a outra.

### Rodada no cluster Kubernetes

&emsp; Em 21 de setembro de 2026 as duas lacunas apontadas acima foram atacadas numa
sessão só, com o cluster EKS no ar e a carga entrando pelo Ingress. Foram duas
rodadas, ambas geradas de uma EC2 dentro da VPC, pelo mesmo roteiro e com o mesmo
gerador da rodada de 18 de setembro. A primeira repete os três níveis originais, para
que a comparação entre plataformas seja de igual para igual. A segunda sobe a carga
até algum critério reprovar.

&emsp; A comparação de igual para igual, com o mesmo roteiro nos dois caminhos:

| Nível | Usuários | Requisições | p95 no Ingress | p95 no ALB | Tela p95 no Ingress | Tela p95 no ALB |
|---|---:|---:|---:|---:|---:|---:|
| 1 | 5 | 1.020 | 90 ms | 94 ms | 121 ms | 157 ms |
| 2 | 25 | 5.144 | 149 ms | 96 ms | 230 ms | 148 ms |
| 3 | 100 | 19.411 | 662 ms | 802 ms | 772 ms | 964 ms |

&emsp; Zero erros em 25.576 requisições, como na rodada do balanceador. O cluster sai
à frente no degrau mais pesado e atrás no do meio, com diferenças pequenas demais
para sustentar preferência por uma plataforma. O que o número diz é que a troca de
plataforma não custou desempenho.

&emsp; A segunda rodada procurou o teto, com 200, 450 e 900 usuários simultâneos. O k6
terminou com código de saída 99, que é como ele sinaliza limiar ultrapassado:

| Nível | Usuários | Requisições | Erros | p95 | Telas completas | Situação |
|---|---:|---:|---:|---:|---:|---|
| 1 | 200 | 29.448 | 0% | 2.766 ms | 100% | Reprovado: viola limiares por tela |
| 2 | 450 | 37.254 | 15,21% | 9.486 ms | 78,77% | Reprovado |
| 3 | 900 | 31.171 | 24,80% | 30.001 ms | 69,51% | Reprovado por esgotamento do prazo |

&emsp; O maior nível aprovado observado foi o de 100 usuários, e o primeiro nível
reprovado foi o de 200. Portanto, o intervalo experimental do limite está entre
100 e 200 usuários simultâneos; não há evidência suficiente para afirmar o teto
exato. O resultado de 200 não pode ser aprovado pelos critérios completos, apesar
do p95 agregado de 2.766 ms: a tela Agora excedeu 5 s na abertura e 3 s nas requisições, e Recorte excedeu 3 s nas
requisições.

&emsp; A ressalva é grande, porém, e precisa vir junto do número. O teto medido é o de
duas réplicas, porque o autoescalador nunca entrou em ação. O autoescalador passou os 36 minutos de cluster no ar reportando `FailedGetResourceMetric`,
141 vezes, e o motivo apareceu em uma linha: o `APIService v1beta1.metrics.k8s.io`
não existe naquele cluster. Sem servidor de métricas não há métrica de CPU, sem
métrica de CPU o HPA não calcula réplica, e as duas réplicas iniciais atenderam
sozinhas os 900 usuários do último degrau.

&emsp; Isso contradiz o que o runbook afirma. O [`k8s/README.md`](../apps/fullstack/k8s/README.md)
diz que o `metrics-server` já vem no Auto Mode, diferente do `kind`, que precisa
instalá-lo. A observação em cluster mostra o contrário: o Auto Mode gerencia a
capacidade de nós, e não instala o servidor de métricas, que continua sendo um
complemento à parte. A decisão de escalar por CPU, registrada no artefato de
conteinerização, portanto nunca chegou a funcionar na AWS. No `kind` funciona, porque
o `make kind-up` instala o `metrics-server` explicitamente.

&emsp; Dois efeitos colaterais apareceram junto. Os dois pods do backend reiniciaram
duas vezes cada durante a saturação, derrubados pela própria sonda de vida quando ela
deixou de responder a tempo, o que retira capacidade justamente no momento de maior
demanda. E o RDS chegou a 86% de CPU sem saturar, o que situa o gargalo desta rodada
na camada de aplicação. Com o autoescalador funcionando, o teto subiria até encontrar
o banco, e é essa segunda medição que fica pendente.

&emsp; A evidência bruta das duas rodadas está versionada em
[`evidencias/carga-kubernetes/`](evidencias/carga-kubernetes/), com o resumo do k6 em
JSON, a saída de texto e o log de cada instância geradora. Para conferir quais
critérios passaram, a saída de texto é a leitura confiável: ela marca cada linha com
`✓` para limiar atendido e `✗` para limiar ultrapassado. Nos arquivos
`*-summary-k6.json` a convenção é a oposta e engana quem lê depressa — ali o booleano
sob `thresholds` indica que o limiar *foi ultrapassado*, de modo que `true` significa
reprovado. O diagnóstico do
autoescalador está em
[`evidencias/carga-kubernetes.txt`](evidencias/carga-kubernetes.txt). Endereços,
identificador de conta e token foram substituídos antes de versionar.

### Onde está cada coisa e como reproduzir

| Caminho | Papel |
|---|---|
| [`apps/fullstack/tests/carga/carga_ui.js`](../apps/fullstack/tests/carga/carga_ui.js) | Roteiro do k6: rotas por tela, três níveis, limiares e resumo por nível |
| [`apps/fullstack/tests/carga/gerador_ec2.sh`](../apps/fullstack/tests/carga/gerador_ec2.sh) | Cria a EC2 geradora, roda o cenário nela, traz os resultados e apaga o que criou |
| [`apps/fullstack/tests/carga/executar_testes.sh`](../apps/fullstack/tests/carga/executar_testes.sh) | Executor local da suíte, com o cenário `carga-ui`; usa o k6 local ou a imagem Docker |
| [`apps/fullstack/backend/Dockerfile`](../apps/fullstack/backend/Dockerfile) | A correção do keep-alive |
| [`apps/fullstack/Makefile`](../apps/fullstack/Makefile) | Alvos `teste-carga-ui` e `teste-carga-ui-ec2` |
| [`evidencias/testes-carga.txt`](evidencias/testes-carga.txt) | Saída completa do k6 das duas rodadas, sem as linhas de progresso, e as leituras do CloudWatch de cada janela |

```bash
# 1. renovar a sessão do Learner Lab e garantir o .env (make -C apps/fullstack env)
# 2. exportar o token de leitura no terminal e chamar o gerador direto: o Makefile
#    lê o .env e sobrescreve o que estiver exportado, então o alvo do make só
#    funciona com o token preenchido no .env
export ARGUS_READ_TOKEN=...
apps/fullstack/tests/carga/gerador_ec2.sh carga-ui

# níveis, duração e pausa são ajustáveis por variável de ambiente:
CARGA_UI_VUS_3=200 CARGA_UI_DURACAO=10m apps/fullstack/tests/carga/gerador_ec2.sh carga-ui

# a variante local, para preflight sem criar instância:
apps/fullstack/tests/carga/executar_testes.sh carga-ui
```

&emsp; Como nas seções anteriores, nenhum endpoint, identificador de conta ou token
aparece neste artefato nem na evidência: as URLs e o id da conta na saída do k6 e
do gerador foram substituídos por `<url>` e `<conta>` antes de serem versionados.

## Cobertura de requisitos

&emsp; As tabelas deste artefato dizem, teste a teste, quais requisitos cada um
exercita. O que elas não permitem ler é a ausência: quantos requisitos não são
alcançados por teste nenhum. Esta seção existe para tornar isso legível, porque uma
lista só de presenças deixa o leitor sem saber se o silêncio sobre um requisito
significa cobertura implícita ou esquecimento.

&emsp; O projeto declara 28 requisitos em [`requisitos.md`](requisitos.md), 17
funcionais e 11 não funcionais. Varrendo todo o código de teste do repositório, e
não apenas os casos descritos aqui, chega-se a 19 requisitos nomeados por pelo menos
um teste e 9 nomeados por nenhum.

| Requisito | Assunto | Existe teste que o toque? |
|---|---|---|
| RF02 | Receber eventos de plataformas diferentes (TV, móvel, web) | Não identificado. A ingestão é testada por conteúdo de mensagem, não por plataforma de origem |
| RF07 | Coletar os seis tipos de evento | Provavelmente sim, sem declarar: os fixtures do TI-03 são os seis eventos reais exportados do BI |
| RF13 | Consultas simples das falhas de maior impacto | Provavelmente sim, sem declarar: a tela Explorar, exercitada pelo E2E-03, traz "Erros mais frequentes" |
| RF15 | Destacar aumentos relevantes, como picos de erro | Provavelmente sim, sem declarar: os sinais da tela Agora, exercitados pelo E2E-02 e pelos unitários de `signals` |
| RF17 | Apresentar hipóteses ordenadas por relevância | Provavelmente sim, sem declarar: o E2E-05 abre a tela e confere score e evidência |
| RNF06 | Compatibilidade com os protocolos do MVP | Não identificado |
| RNF07 | Usar sem orientação técnica detalhada | Fora do alcance de teste automatizado; exige teste com usuário |
| RNF08 | Reconhecer a que problema cada hipótese se refere | Fora do alcance de teste automatizado; exige teste com usuário |
| RNF11 | Registrar o suficiente sobre falhas para investigá-las | Provavelmente sim, sem declarar: o TI-03 verifica que a mensagem inválida vai para a fila de descarte com o motivo anexado |

&emsp; A coluna da direita separa três situações que não deveriam ser confundidas.
Dois requisitos, o RNF07 e o RNF08, são de usabilidade, e nenhuma suíte
automatizada os resolve. Afirmar o contrário seria falso: o caminho deles é teste
com usuário.
Cinco são exercitados na prática, mas por testes que não os nomeiam: a cobertura
existe e não é auditável, o que na hora de uma revisão vale quase o mesmo que não
existir. Dois, o RF02 e o RNF06, não têm teste que se possa apontar.

&emsp; A correção barata é a segunda coluna de cinco linhas: declarar o requisito no
cabeçalho do teste que já o exercita, como o TI-01 faz. Isso não escreve teste novo e
transforma cinco ausências aparentes em cobertura verificável.

## Conclusão

&emsp; Este artefato percorreu três perguntas em ordem crescente de alcance. Os 133
testes unitários selecionados nos quatro serviços responderam se cada unidade
calcula certo, com tudo em volta substituído por dublê, e todos aprovaram. Desse
conjunto, 63 pertencem ao backend. Os cinco testes de integração, com treze
casos, responderam se as camadas conversam entre si sem dublê no trecho sob teste:
doze casos aprovaram e um reprovou, o TI-05.2, na pilha publicada. Os testes de carga
responderam se o sistema continua respondendo, e em quanto tempo, com 5, 25 e 100
pessoas usando o dashboard ao mesmo tempo: 25.501 requisições de carga sem nenhuma falha,
mais uma requisição de setup, com
o percentil 95 abaixo de 100 ms até 25 usuários e de 802 ms com 100.

&emsp; O valor deste conjunto está menos no número de aprovações do que nos dois
defeitos que ele encontrou, e que nenhuma leitura de código encontraria. O primeiro
veio da integração: o evento aceito pela borda levava horas para aparecer na leitura, porque a ETL varria a tabela `bronze.event` sem índice pelo
número de ordem `_lsn`. O diagnóstico virou a migration 030 e um teste que a
sustenta. O segundo veio da carga: um em cada mil pedidos ao dashboard morria com
502 no balanceador, em qualquer nível de uso, porque o gunicorn fechava conexões
ociosas em 2 s e o ALB as reaproveitava por 60 s. O diagnóstico virou uma linha no
Dockerfile, uma nova imagem em produção e uma segunda rodada que provou o efeito.
Nos dois casos a reprovação foi mantida no relatório e investigada até a causa, em
vez de contornada afrouxando prazo ou critério.

&emsp; Três coisas ficam apontadas para a próxima iteração, e nenhuma invalida as
execuções registradas. A ETL precisa de uma métrica de distância entre o marcador e
a ponta da sequência, para que um acúmulo apareça no dia em que começa e não num
teste dias depois. A carga no grupo de auto scaling ainda se beneficia de um degrau
de aquecimento e de um nível longo o bastante para observar a entrada das novas
instâncias. E a elasticidade do Kubernetes deve ser medida novamente depois da
instalação do `metrics-server`, pois a rodada no Ingress já comparou o desempenho
das plataformas e localizou o intervalo de reprovação entre 100 e 200 usuários,
mas o HPA permaneceu sem métrica e as duas réplicas iniciais atenderam sozinhas.

&emsp; Assim, integração entre camadas, carga pelo ALB e carga pelo Ingress do EKS
foram efetivamente executadas. O item ainda fora deste artefato é a seção específica
de testes de caso de uso e análise do valor limite, registrada no backlog para a
próxima inclusão.

## Referências

&emsp; Fontes consultadas na escrita deste artefato, agrupadas pelo assunto em que
foram usadas.

**Ferramentas de teste**

1. PYTEST-DEV. *pytest documentation*. Disponível em: <https://docs.pytest.org/en/stable/>. Acesso em: 18 set. 2026.
2. MICROSOFT. *Playwright: Installation and getting started*. Disponível em: <https://playwright.dev/docs/intro>. Acesso em: 18 set. 2026.
3. GETMOTO. *Moto: Mock AWS Services*. Disponível em: <https://docs.getmoto.org/en/latest/>. Acesso em: 18 set. 2026.
4. GRAFANA LABS. *k6 documentation: Constant VUs executor*. Disponível em: <https://grafana.com/docs/k6/latest/using-k6/scenarios/executors/constant-vus/>. Acesso em: 18 set. 2026.
5. GRAFANA LABS. *k6 documentation: Thresholds*. Disponível em: <https://grafana.com/docs/k6/latest/using-k6/thresholds/>. Acesso em: 18 set. 2026.
6. GRAFANA LABS. *k6 documentation: http.batch()*. Disponível em: <https://grafana.com/docs/k6/latest/javascript-api/k6-http/batch/>. Acesso em: 18 set. 2026.

**Componentes da AWS exercitados pelos testes**

7. AMAZON WEB SERVICES. *Amazon SQS standard queues* (entrega ao menos uma vez e ordenação de melhor esforço). Disponível em: <https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/standard-queues.html>. Acesso em: 18 set. 2026.
8. AMAZON WEB SERVICES. *Integrating HTTP APIs with AWS services* (integração direta do API Gateway com o SQS, usada no TI-05). Disponível em: <https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-develop-integrations-aws-services.html>. Acesso em: 18 set. 2026.
9. AMAZON WEB SERVICES. *Working with AWS Lambda authorizers for HTTP APIs*. Disponível em: <https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-lambda-authorizer.html>. Acesso em: 18 set. 2026.
10. AMAZON WEB SERVICES. *Edit attributes for your Application Load Balancer*, seção "Connection idle timeout", que recomenda que a aplicação mantenha a conexão por mais tempo que o balanceador e descreve o 502 resultante. Disponível em: <https://docs.aws.amazon.com/elasticloadbalancing/latest/application/edit-load-balancer-attributes.html>. Acesso em: 18 set. 2026.
11. AMAZON WEB SERVICES. *CloudWatch metrics for your Application Load Balancer* (`HTTPCode_ELB_502_Count`, `HTTPCode_Target_5XX_Count`, `TargetResponseTime`, `HealthyHostCount`). Disponível em: <https://docs.aws.amazon.com/elasticloadbalancing/latest/application/load-balancer-cloudwatch-metrics.html>. Acesso em: 18 set. 2026.
12. AMAZON WEB SERVICES. *Target tracking scaling policies for Amazon EC2 Auto Scaling* (métrica `ALBRequestCountPerTarget`). Disponível em: <https://docs.aws.amazon.com/autoscaling/ec2/userguide/as-scaling-target-tracking.html>. Acesso em: 18 set. 2026.
13. AMAZON WEB SERVICES. *Use an instance refresh to update instances in an Auto Scaling group*. Disponível em: <https://docs.aws.amazon.com/autoscaling/ec2/userguide/asg-instance-refresh.html>. Acesso em: 18 set. 2026.
14. HASHICORP. *Terraform AWS provider: aws_autoscaling_group*, bloco `instance_refresh` e a nota sobre `version = "$Latest"` não disparar o refresh. Disponível em: <https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/autoscaling_group>. Acesso em: 18 set. 2026.
15. AMAZON WEB SERVICES. *Amazon EC2 testing policy* (testes de estresse de rede a partir de recursos da própria conta). Disponível em: <https://aws.amazon.com/ec2/testing/>. Acesso em: 18 set. 2026.
16. AMAZON WEB SERVICES. *Penetration testing* (política de eventos simulados, incluindo testes de carga). Disponível em: <https://aws.amazon.com/security/penetration-testing/>. Acesso em: 18 set. 2026.

**Servidor de aplicação e banco**

17. GUNICORN. *Settings: keepalive* (padrão de 2 s e a recomendação de valor maior atrás de um balanceador). Disponível em: <https://gunicorn.org/reference/settings/>. Acesso em: 18 set. 2026.
18. POSTGRESQL GLOBAL DEVELOPMENT GROUP. *PostgreSQL 16 Documentation: Indexes* (base da migration 030). Disponível em: <https://www.postgresql.org/docs/16/indexes.html>. Acesso em: 18 set. 2026.

**Conceitos**

19. DEAN, J.; BARROSO, L. A. The Tail at Scale. *Communications of the ACM*, v. 56, n. 2, p. 74–80, 2013. Disponível em: <https://doi.org/10.1145/2408776.2408794>. Acesso em: 18 set. 2026. Base para a escolha de percentis, e não médias, como medida de tempo de resposta.
20. DATABRICKS. *Medallion architecture* (as camadas bronze, silver e gold). Disponível em: <https://www.databricks.com/glossary/medallion-architecture>. Acesso em: 18 set. 2026.
