# Benchmark local exploratório — Python × Go

Rodada: **2026-10-05**. Paridade aprovada antes da medição em 49 cenários de regras, um ciclo base e quatro cargas (54 saídas completas).

## Ambiente e protocolo

- Sistema: Windows 11 (10.0.26200), AMD64.
- CPU: 13th Gen Intel(R) Core(TM) i5-13500H; 16 CPUs lógicas; memória física: 15.74 GiB.
- Ambos os filhos restritos à CPU lógica 0; um processo medido por vez; Go com GOMAXPROCS=1.
- 5 aquecimentos e 50 amostras por etapa e por linguagem. p95: nearest rank.
- Ordem das linguagens alternada entre cargas. Etapas na ordem: qualidade, detector, candidatos, score, total.
- JSON, catálogos e entradas tipadas carregados antes do cronômetro. Compilação, comparação, serialização e I/O fora dos tempos.
- GC padrão habilitado: CPython; Go GOGC=100 e GOMEMLIMIT=off. Sem limite adicional de memória.
- Uma execução por perfil em uma máquina de desenvolvimento; frequência da CPU, energia e processos externos não foram controlados.

## Cálculo completo

A razão é mediana Python / mediana Go; maior que 1 favorece Go. O total é cronometrado separadamente e não é a soma das medianas.

| Carga | Fatos | Python mediana (ms) | Python p95 (ms) | Go mediana (ms) | Go p95 (ms) | Razão | RSS Python (MiB) | RSS Go (MiB) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| ciclo_misto_v1 | 16 | 1.1875 | 1.3461 | 0.1978 | 0.3623 | 6.00× | 23.92 | 14.08 |
| disperso_256 | 256 | 8.1002 | 10.4934 | 2.2885 | 3.1594 | 3.54× | 24.43 | 14.38 |
| disperso_1024 | 1024 | 30.1981 | 32.7981 | 9.3047 | 10.8855 | 3.25× | 26.00 | 14.42 |
| denso_128 | 128 | 58.0029 | 59.6376 | 24.7604 | 26.8585 | 2.34× | 24.64 | 16.62 |
| denso_512 | 512 | 963.9268 | 993.0105 | 430.6092 | 436.4850 | 2.24× | 26.39 | 57.32 |

## Por etapa

### ciclo_misto_v1

Runtimes: CPython 3.14.4 e go1.27.1.
Relógios: QueryPerformanceCounter() (Python), Windows QueryPerformanceCounter (Go). Resoluções declaradas: 100 ns / 100 ns. Overhead do cronômetro não subtraído.

| Etapa | Python mediana (ms) | Python p95 (ms) | Go mediana (ms) | Go p95 (ms) | Razão |
| --- | ---: | ---: | ---: | ---: | ---: |
| quality | 0.0897 | 0.1118 | 0.0155 | 0.0212 | 5.77× |
| detector | 0.0564 | 0.0643 | 0.0073 | 0.0124 | 7.78× |
| candidates | 0.4386 | 0.4801 | 0.0958 | 0.1221 | 4.58× |
| scoring | 0.5107 | 0.5805 | 0.0888 | 0.2798 | 5.75× |
| total | 1.1875 | 1.3461 | 0.1978 | 0.3623 | 6.00× |

### disperso_256

Runtimes: CPython 3.14.4 e go1.27.1.
Relógios: QueryPerformanceCounter() (Python), Windows QueryPerformanceCounter (Go). Resoluções declaradas: 100 ns / 100 ns. Overhead do cronômetro não subtraído.

| Etapa | Python mediana (ms) | Python p95 (ms) | Go mediana (ms) | Go p95 (ms) | Razão |
| --- | ---: | ---: | ---: | ---: | ---: |
| quality | 0.1757 | 0.1877 | 0.0330 | 0.0636 | 5.33× |
| detector | 0.6419 | 0.6903 | 0.1042 | 0.4207 | 6.16× |
| candidates | 6.5485 | 7.1161 | 1.9459 | 3.0968 | 3.37× |
| scoring | 0.4969 | 0.5723 | 0.0895 | 0.2792 | 5.55× |
| total | 8.1002 | 10.4934 | 2.2885 | 3.1594 | 3.54× |

### disperso_1024

Runtimes: CPython 3.14.4 e go1.27.1.
Relógios: QueryPerformanceCounter() (Python), Windows QueryPerformanceCounter (Go). Resoluções declaradas: 100 ns / 100 ns. Overhead do cronômetro não subtraído.

| Etapa | Python mediana (ms) | Python p95 (ms) | Go mediana (ms) | Go p95 (ms) | Razão |
| --- | ---: | ---: | ---: | ---: | ---: |
| quality | 0.3866 | 0.3966 | 0.0609 | 0.2454 | 6.34× |
| detector | 2.5996 | 2.8081 | 0.3556 | 0.8555 | 7.31× |
| candidates | 26.4228 | 28.4065 | 8.3523 | 9.9013 | 3.16× |
| scoring | 0.5004 | 0.6691 | 0.1044 | 0.2921 | 4.79× |
| total | 30.1981 | 32.7981 | 9.3047 | 10.8855 | 3.25× |

### denso_128

Runtimes: CPython 3.14.4 e go1.27.1.
Relógios: QueryPerformanceCounter() (Python), Windows QueryPerformanceCounter (Go). Resoluções declaradas: 100 ns / 100 ns. Overhead do cronômetro não subtraído.

| Etapa | Python mediana (ms) | Python p95 (ms) | Go mediana (ms) | Go p95 (ms) | Razão |
| --- | ---: | ---: | ---: | ---: | ---: |
| quality | 0.1368 | 0.1462 | 0.0374 | 0.0855 | 3.66× |
| detector | 0.5270 | 0.5655 | 0.0632 | 0.1797 | 8.34× |
| candidates | 51.8218 | 53.1514 | 20.3974 | 24.5646 | 2.54× |
| scoring | 5.5426 | 6.2018 | 3.6145 | 4.9405 | 1.53× |
| total | 58.0029 | 59.6376 | 24.7604 | 26.8585 | 2.34× |

### denso_512

Runtimes: CPython 3.14.4 e go1.27.1.
Relógios: QueryPerformanceCounter() (Python), Windows QueryPerformanceCounter (Go). Resoluções declaradas: 100 ns / 100 ns. Overhead do cronômetro não subtraído.

| Etapa | Python mediana (ms) | Python p95 (ms) | Go mediana (ms) | Go p95 (ms) | Razão |
| --- | ---: | ---: | ---: | ---: | ---: |
| quality | 0.2508 | 0.2670 | 0.0450 | 0.1356 | 5.57× |
| detector | 2.1557 | 2.3482 | 0.3547 | 0.8742 | 6.08× |
| candidates | 853.8802 | 917.6821 | 381.1245 | 515.4574 | 2.24× |
| scoring | 50.2000 | 53.8700 | 68.9062 | 75.3906 | 0.73× |
| total | 963.9268 | 993.0105 | 430.6092 | 436.4850 | 2.24× |

## Interpretação e limites

- Nesta rodada, Go teve mediana e p95 menores no cálculo completo das cinco cargas; a razão das medianas variou de 2.24× a 6.00×. Não foram medidas rodadas independentes para confirmar a estabilidade desses ganhos.
- Na carga `denso_512`, o score isolado foi 37.26% mais lento em Go (68.9062 ms contra 50.2000 ms de mediana), e o pico de RSS foi aproximadamente 2.17× maior (57.32 MiB contra 26.39 MiB). Essas diferenças precisam ser investigadas antes de uma decisão de migração.
- Construir candidatos foi a etapa mais lenta nas quatro cargas ampliadas. No ciclo base, a etapa mais lenta em Python foi o score. As medianas das etapas não devem ser somadas para reconstruir o total.
- A rodada mede estas implementações e estas cargas sintéticas. Não isola o efeito da linguagem de diferenças de implementação e runtime.
- O pico de RSS inclui inicialização, dados, runtime, aquecimentos e todas as etapas do processo. Não representa apenas alocações do motor nem memória incremental por chamada.
- No Windows foi usado [PeakWorkingSetSize](https://learn.microsoft.com/en-us/windows/win32/api/psapi/ns-psapi-process_memory_counters); no Linux, o contador VmHWM do processo.
- Banco, captura, claim/lease, persistência, rede e ETL estão fora. Estes números não estimam latência ou custo da arquitetura na AWS.
- A equipe ainda não definiu o ganho mínimo para justificar uma migração. Esta rodada exploratória não aprova uma mudança de produção.
- Uma decisão posterior requer critério prévio, rodadas independentes e medição do ciclo com banco em ambiente representativo.

## Evidências

O arquivo `resultados.json` ao lado contém todas as amostras em ns, estatísticas, versões, hardware, ordem de execução e hashes SHA-256 dos dados e do código. Os hashes permitem identificar também código sem commit.
