"""Gera notebooks/eda_argus.ipynb — analise exploratoria do dump do Argus.

O notebook e montado programaticamente para manter a numeracao das secoes, o
estilo dos graficos e o texto das conclusoes sob controle de versao. Rode:

    python tools/build_notebook.py && \
        jupyter nbconvert --execute --inplace notebooks/eda_argus.ipynb
"""

from __future__ import annotations

from pathlib import Path

import nbformat as nbf

CELLS: list[tuple[str, str]] = []


def md(text: str) -> None:
    CELLS.append(("md", text.strip("\n")))


def code(src: str) -> None:
    CELLS.append(("code", src.strip("\n")))


# =========================================================================== #
# Capa e setup
# =========================================================================== #

md(
    """
# Argus — Análise Exploratória de Dados

**Fonte:** `argus_dump.sql` (4,15 GB, 33 tabelas) — dump sanitizado cedido pela Globo
para a parceria acadêmica Globo × Inteli, extraído em 2026-08-06.

O Argus é a plataforma de observabilidade que instrumenta a cadeia de entrega do
Globoplay. O dump reúne, na mesma base, quatro camadas que hoje vivem em silos
distintos na operação:

| Camada | O que registra | Tabelas |
|---|---|---|
| **Telemetria de infraestrutura** | métricas de borda, APM, Prometheus, GraphQL, deploys | `signal_*`, `prom_*`, `rpaas_bucket`, `ca_point`, `service_overview`, `operation_metrics`, `field_metrics`, `tsuru_event` |
| **QoE do player** | experiência percebida pelo assinante (Youbora) | `player_hourly`, `device_hourly`, `geo_hourly`, `live_qoe_hourly`, `player_live_hourly`, `live_active_15min`, `live_error_attr_hourly`, `error_cat_hourly`, `live_event` |
| **Incidentes** | chamados do ITSM e rótulos de detector | `incidents`, `incidents_platform`, `incident_label`, `investigation_feedback` |
| **Operação da coleta** | execuções, custo e volume dos coletores | `collector_run`, `apollo_run`, `nr_run`, `prom_run`, `rpaas_run`, `ca_run`, `signal_meta`, `dashboard_artifact` |

Essa convergência é exatamente o insumo do problema do projeto: correlacionar
sintoma percebido (QoE) com causa provável (infraestrutura, deploy, incidente)
numa linha do tempo única.

## Como este notebook está organizado

1. Inventário e modelo de dados
2. Qualidade dos dados
3. Telemetria de infraestrutura
4. Qualidade de experiência (QoE)
5. Incidentes e rótulos
6. Operação da coleta
7. Análise cruzada entre camadas
8. Síntese: achados e implicações para os requisitos

## Pré-requisito

O dump é convertido uma única vez para Parquet (`data/parquet/`), e todas as
consultas rodam em DuckDB sobre esses arquivos. Isso mantém o notebook
reexecutável em segundos, sem carregar 4 GB de SQL na memória:

```bash
python tools/etl_dump.py --dump argus_dump.sql --out data/parquet
```
"""
)

code(
    '''
from __future__ import annotations

import json
import warnings
from pathlib import Path

import duckdb
import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

# --- localiza a raiz do projeto, funcione o notebook de onde for aberto ------
ROOT = Path.cwd()
while not (ROOT / "data" / "parquet").exists() and ROOT != ROOT.parent:
    ROOT = ROOT.parent
PQ = ROOT / "data" / "parquet"
assert PQ.exists(), f"rode tools/etl_dump.py antes: {PQ} nao existe"

MANIFEST = json.loads((PQ / "_manifest.json").read_text())
SCHEMA = json.loads((PQ / "_schema.json").read_text())

con = duckdb.connect()
con.execute("SET TimeZone='UTC'")

# cada parquet vira uma view com o nome da tabela original
TABLES = sorted(p.stem for p in PQ.glob("*.parquet"))
for t in TABLES:
    con.execute(f"CREATE OR REPLACE VIEW {t} AS SELECT * FROM '{PQ / f'{t}.parquet'}'")


def q(sql: str) -> pd.DataFrame:
    """Executa SQL no DuckDB e devolve um DataFrame."""
    return con.execute(sql).df()


pd.set_option("display.max_columns", 60)
pd.set_option("display.width", 200)
pd.set_option("display.float_format", lambda v: f"{v:,.4g}")

print(f"{len(TABLES)} tabelas | {MANIFEST['total_rows']:,} linhas | "
      f"dump de {MANIFEST['dump_bytes'] / 1e9:.2f} GB "
      f"convertido em {MANIFEST['elapsed_s'] / 60:.1f} min")
'''
)

md(
    """
### Convenções visuais

A paleta é fixa e ordenada: a mesma entidade recebe a mesma cor em todos os
gráficos, e a cor nunca segue o ranking (um filtro que muda a quantidade de
séries não repinta as sobreviventes). Escalas sequenciais usam um único tom
azul, claro→escuro; escalas divergentes usam azul↔vermelho com cinza neutro no
meio. Eixos e grade ficam recessivos para que a marca de dados seja o elemento
mais forte da figura.
"""
)

code(
    '''
# paleta categórica validada (ordem fixa — nunca ciclada)
CAT = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100",
       "#e87ba4", "#008300", "#4a3aa7", "#e34948"]
SEQ = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5",
       "#2a78d6", "#256abf", "#184f95", "#0d366b"]
INK, INK2, INK3 = "#0b0b0b", "#52514e", "#8a8983"
GRID, SURFACE = "#e8e7e3", "#fcfcfb"
STATUS = {"good": "#008300", "warning": "#eda100",
          "serious": "#eb6834", "critical": "#e34948"}

SEQ_CMAP = mpl.colors.LinearSegmentedColormap.from_list("argus_seq", SEQ)
# divergente vermelho↔azul com cinza neutro no meio. A polaridade acompanha a
# das barras de correlação (azul = mesma direção, vermelho = direção oposta).
DIV_CMAP = mpl.colors.LinearSegmentedColormap.from_list(
    "argus_div", ["#8f1f1e", "#e34948", "#f5a3a2", "#f0efec",
                  "#9ec5f4", "#2a78d6", "#0d366b"])

mpl.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE,
    "savefig.facecolor": SURFACE, "figure.dpi": 120,
    "font.size": 9.5, "axes.titlesize": 11, "axes.titleweight": "bold",
    "axes.titlelocation": "left", "axes.titlepad": 10,
    "axes.labelsize": 9, "axes.labelcolor": INK2,
    "text.color": INK, "axes.edgecolor": GRID, "axes.linewidth": 0.8,
    "axes.spines.top": False, "axes.spines.right": False,
    "xtick.color": INK2, "ytick.color": INK2,
    "xtick.labelsize": 8.5, "ytick.labelsize": 8.5,
    "xtick.major.size": 0, "ytick.major.size": 0,
    "grid.color": GRID, "grid.linewidth": 0.8, "axes.grid": True,
    "axes.grid.axis": "y", "grid.alpha": 1.0,
    # a grade fica sempre atrás da marca de dados, nunca por cima dela
    "axes.axisbelow": True,
    "legend.frameon": False, "legend.fontsize": 8.5,
    "lines.linewidth": 2.0, "lines.markersize": 4,
    "axes.prop_cycle": mpl.cycler(color=CAT),
    # eixos de data com menos marcas e rótulos hierárquicos, sem sobreposição
    "date.converter": "concise",
})


def fig(w=9.5, h=4.0, **kw):
    f, ax = plt.subplots(figsize=(w, h), **kw)
    return f, ax


def titulo(ax, titulo_txt, subtitulo=None):
    """Título curto + subtítulo explicativo em tinta secundária.

    O deslocamento é em pontos (não em fração do eixo) para que o espaçamento
    não mude conforme a altura da figura.
    """
    if subtitulo:
        ax.set_title(titulo_txt, color=INK, pad=26)
        ax.annotate(subtitulo, xy=(0, 1), xycoords="axes fraction",
                    xytext=(0, 7), textcoords="offset points",
                    fontsize=8.5, color=INK3, va="bottom", ha="left")
    else:
        ax.set_title(titulo_txt, color=INK, pad=10)
    return ax


def sem_grade(ax):
    ax.grid(False)
    return ax


def barras_h(ax, labels, values, color=CAT[0], fmt="{:,.0f}", pad=0.01):
    """Barras horizontais com rótulo direto — dispensa eixo x e grade."""
    y = np.arange(len(labels))
    ax.barh(y, values, color=color, height=0.62)
    ax.set_yticks(y, labels)
    ax.invert_yaxis()
    sem_grade(ax)
    ax.set_xticks([])
    ax.spines["bottom"].set_visible(False)
    ax.spines["left"].set_visible(False)
    span = max(values) if len(values) else 1
    for yi, v in zip(y, values):
        ax.text(v + span * pad, yi, fmt.format(v), va="center",
                fontsize=8.5, color=INK2)
    ax.set_xlim(0, span * 1.16)
    return ax


def ts(ms):
    """epoch em milissegundos -> expressão SQL de timestamp UTC."""
    return f"to_timestamp({ms} / 1000)"


print("estilo carregado")
'''
)

# =========================================================================== #
# 1. Inventario e modelo de dados
# =========================================================================== #

md(
    """
---
# 1. Inventário e modelo de dados

Antes de qualquer análise, é preciso saber o que existe: quantas linhas cada
tabela traz, qual coluna carrega o tempo, e que janela cada uma cobre. Sem esse
mapa, cruzamentos entre camadas correm o risco de comparar períodos diferentes.
"""
)

md("## 1.1. Volumetria por tabela")

code(
    '''
# domínio de cada tabela — usado para agrupar a leitura ao longo do notebook
DOMINIO = {
    "signal_point": "Infra", "signal_bucket": "Infra", "signal_meta": "Coleta",
    "cdn_entity_tier": "Infra", "service_overview": "Infra",
    "operation_metrics": "Infra", "field_metrics": "Infra",
    "prom_query": "Infra", "prom_series": "Infra", "prom_point": "Infra",
    "rpaas_bucket": "Infra", "ca_point": "Infra", "tsuru_event": "Infra",
    "player_hourly": "QoE", "device_hourly": "QoE", "geo_hourly": "QoE",
    "live_qoe_hourly": "QoE", "player_live_hourly": "QoE",
    "live_active_15min": "QoE", "live_error_attr_hourly": "QoE",
    "error_cat_hourly": "QoE", "live_event": "QoE",
    "incidents": "Incidentes", "incidents_platform": "Incidentes",
    "incident_label": "Incidentes", "investigation_feedback": "Incidentes",
    "dashboard_artifact": "Coleta", "collector_run": "Coleta",
    "apollo_run": "Coleta", "nr_run": "Coleta", "prom_run": "Coleta",
    "rpaas_run": "Coleta", "ca_run": "Coleta",
}

# coluna que carrega o tempo do evento em cada tabela (epoch ms), quando existe
COL_TEMPO = {
    "signal_point": "ts", "signal_bucket": "bts", "service_overview": "timestamp",
    "operation_metrics": "start_ts", "field_metrics": "start_ts",
    "prom_point": "epoch_ms", "rpaas_bucket": "bucket_ts_ms", "ca_point": "ts_ms",
    "tsuru_event": "start_time_ms", "player_hourly": "hour_ts",
    "device_hourly": "hour_ts", "geo_hourly": "hour_ts",
    "live_qoe_hourly": "hour_ts", "player_live_hourly": "hour_ts",
    "live_active_15min": "bucket_ts", "live_error_attr_hourly": "hour_ts",
    "error_cat_hourly": "hour_ts", "live_event": "start_ts",
    "incidents": "opened_at", "incidents_platform": "opened_at",
    "incident_label": "ts_start", "collector_run": "started_at",
}

inv = []
for t in TABLES:
    n = q(f"SELECT count(*) n FROM {t}").n.iloc[0]
    cols = len(SCHEMA.get(t, {}))
    mb = (PQ / f"{t}.parquet").stat().st_size / 1e6
    ini = fim = None
    if (c := COL_TEMPO.get(t)) and n:
        r = q(f"SELECT {ts(f'min({c})')} a, {ts(f'max({c})')} b FROM {t}").iloc[0]
        ini, fim = r.a, r.b
    inv.append({"tabela": t, "dominio": DOMINIO.get(t, "?"), "linhas": n,
                "colunas": cols, "parquet_mb": round(mb, 1),
                "inicio": ini, "fim": fim})

inv = pd.DataFrame(inv).sort_values("linhas", ascending=False).reset_index(drop=True)
print(f"total: {inv.linhas.sum():,} linhas em {len(inv)} tabelas | "
      f"{inv.parquet_mb.sum() / 1000:.2f} GB em Parquet "
      f"(dump SQL original: {MANIFEST['dump_bytes'] / 1e9:.2f} GB)")
inv
'''
)

code(
    '''
# A escala entre tabelas é de várias ordens de grandeza: eixo logarítmico, e o
# rótulo direto em cada barra dispensa a leitura do eixo.
d = inv[inv.linhas > 0]
f, ax = fig(9.5, 8.0)
cores = {"Infra": CAT[0], "QoE": CAT[2], "Incidentes": CAT[1], "Coleta": CAT[6]}
y = np.arange(len(d))
ax.barh(y, d.linhas, color=[cores[x] for x in d.dominio], height=0.66)
ax.set_yticks(y, d.tabela)
ax.set_xscale("log")
ax.invert_yaxis()
sem_grade(ax)
ax.grid(True, axis="x")
ax.set_axisbelow(True)
for yi, v in zip(y, d.linhas):
    ax.text(v * 1.25, yi, f"{v:,.0f}", va="center", fontsize=8, color=INK2)
ax.set_xlim(right=d.linhas.max() * 12)
ax.spines["left"].set_visible(False)
ax.set_xlabel("linhas (escala log)")
handles = [mpl.patches.Patch(color=c, label=k) for k, c in cores.items()]
ax.legend(handles=handles, ncol=4, loc="lower right", bbox_to_anchor=(1, -0.09))
titulo(ax, "Volumetria por tabela",
       "prom_point e signal_point concentram a maior parte das linhas do dump")
plt.tight_layout()
plt.show()
'''
)

md(
    """
Duas tabelas de séries temporais concentram quase todo o volume. Isso importa
para o desenho da solução: o custo de armazenamento e de varredura é dominado
pela telemetria bruta, enquanto as tabelas que carregam **significado de
negócio** — incidentes, rótulos, eventos ao vivo — são pequenas o bastante para
caber em memória. Um sistema de correlação pode manter o lado semântico quente e
tratar a telemetria sob demanda.
"""
)

md("## 1.2. Cobertura temporal")

code(
    '''
d = inv.dropna(subset=["inicio"]).sort_values("inicio")
f, ax = fig(9.5, 7.0)
y = np.arange(len(d))
ini = mpl.dates.date2num(pd.to_datetime(d.inicio))
fim = mpl.dates.date2num(pd.to_datetime(d.fim))
ax.barh(y, fim - ini, left=ini, height=0.6,
        color=[cores[x] for x in d.dominio])
ax.set_yticks(y, d.tabela)
ax.invert_yaxis()
ax.xaxis_date()
sem_grade(ax)
ax.grid(True, axis="x")
ax.set_axisbelow(True)
ax.spines["left"].set_visible(False)
for yi, a, b in zip(y, ini, fim):
    ax.text(b + (fim.max() - ini.min()) * 0.008, yi,
            f"{b - a:.0f}d", va="center", fontsize=8, color=INK3)
titulo(ax, "Janela coberta por tabela",
       "cada barra vai do primeiro ao último registro da tabela")
plt.tight_layout()
plt.show()

nucleo = d[d.linhas > 1000]
print(f"janela comum às tabelas com >1k linhas: "
      f"{nucleo.inicio.max():%Y-%m-%d} a {nucleo.fim.min():%Y-%m-%d}")
'''
)

md(
    """
As janelas **não coincidem**. Qualquer cruzamento entre camadas precisa ser
recortado pela interseção, sob pena de ler como "queda" o que é apenas ausência
de coleta. A janela comum impressa acima é a régua usada na seção 7.
"""
)

md("## 1.3. Granularidade temporal")

code(
    '''
# Passos "canônicos" de coleta em segundos — a grade real de cada fonte é
# aproximada pelo canônico mais próximo do intervalo mediano observado.
CANONICOS = [1, 5, 10, 15, 30, 60, 120, 300, 600, 900, 1800, 3600, 86400]


def formata_passo(seg: float) -> str:
    if seg < 60:
        return f"{seg:,.0f} s"
    if seg < 3600:
        return f"{seg / 60:,.0f} min"
    if seg < 86400:
        return f"{seg / 3600:,.1f} h"
    return f"{seg / 86400:,.1f} d"


EVENTOS = {"tsuru_event", "incidents", "incidents_platform", "live_event",
           "incident_label", "collector_run"}

linhas = []
for t, c in COL_TEMPO.items():
    if t not in TABLES or inv.loc[inv.tabela == t, "linhas"].iloc[0] < 10:
        continue
    r = q(f"""
        WITH d AS (SELECT DISTINCT {c} v FROM {t}),
             g AS (SELECT v, v - lag(v) OVER (ORDER BY v) delta FROM d)
        SELECT count(*) instantes, median(delta) mediana, max(delta) maior
        FROM g
    """).iloc[0]
    med_s = (r.mediana or 0) / 1000
    passo = min(CANONICOS, key=lambda k: abs(np.log(k / max(med_s, 1e-9))))
    # quanto dos instantes cai exatamente sobre a grade canônica?
    alin = q(f"""
        SELECT 100.0 * count(*) FILTER (WHERE {c} % {passo * 1000} = 0)
             / count(*) pct FROM (SELECT DISTINCT {c} FROM {t})
    """).pct.iloc[0]
    linhas.append({
        "tabela": t, "coluna": c, "instantes": int(r.instantes),
        "tipo": "evento" if t in EVENTOS else "série",
        "gap_mediano": formata_passo(med_s),
        "grade_estimada": formata_passo(passo) if t not in EVENTOS else "—",
        "alinhado_pct": round(alin, 1) if t not in EVENTOS else np.nan,
        "maior_gap": formata_passo((r.maior or 0) / 1000),
    })

gran = pd.DataFrame(linhas).sort_values(["tipo", "tabela"]).reset_index(drop=True)
gran
'''
)

md(
    """
Duas leituras importam aqui.

**As grades são heterogêneas.** As fontes agregadas (`*_hourly`, `rpaas_bucket`,
`signal_bucket`) vivem em grades limpas de 15 minutos ou 1 hora, com 100% dos
instantes alinhados. Já a telemetria bruta (`signal_point`, `prom_point`,
`ca_point`, `service_overview`) tem **quase nenhum instante alinhado** a uma
grade: os timestamps carregam o jitter do momento em que o coletor rodou.

**Consequência prática:** essas fontes não podem ser unidas por igualdade de
timestamp. Qualquer cruzamento entre elas exige reamostragem para uma grade
comum — e a mais grossa entre todas as fontes é a de 1 hora, que é a régua usada
na seção 7. Um `JOIN ... USING (timestamp)` ingênuo entre `signal_point` e
`prom_point` retornaria quase nada, apesar de ambas cobrirem o mesmo período.
"""
)

# =========================================================================== #
# 2. Qualidade dos dados
# =========================================================================== #

md(
    """
---
# 2. Qualidade dos dados

Um dado de observabilidade herda os defeitos do caminho que percorreu: coletor
que falhou, série que sumiu, campo que o fornecedor parou de preencher. Esta
seção mede quatro coisas — preenchimento, cardinalidade, integridade e
continuidade — porque cada uma invalida um tipo diferente de conclusão adiante.
"""
)

md("## 2.1. Preenchimento das colunas")

code(
    '''
nulos = []
for t in TABLES:
    n = inv.loc[inv.tabela == t, "linhas"].iloc[0]
    if n == 0:
        continue
    cols = q(f"SELECT * FROM {t} LIMIT 0").columns
    expr = ", ".join(f'count("{c}") AS "{c}"' for c in cols)
    preenchidos = q(f"SELECT {expr} FROM {t}").iloc[0]
    for c in cols:
        nulos.append({"tabela": t, "coluna": c, "linhas": n,
                      "pct_nulo": 100 * (1 - preenchidos[c] / n)})

nulos = pd.DataFrame(nulos)
vazias = nulos[nulos.pct_nulo == 100]
print(f"{len(nulos)} colunas analisadas em {nulos.tabela.nunique()} tabelas")
print(f"{len(vazias)} colunas 100% nulas | "
      f"{len(nulos[nulos.pct_nulo.between(0.001, 100, inclusive='left')])} parcialmente nulas")
vazias[["tabela", "coluna"]].reset_index(drop=True)
'''
)

code(
    '''
# Só as colunas que de fato têm nulos entram no gráfico — listar as completas
# não informa nada.
d = nulos[nulos.pct_nulo > 0].sort_values("pct_nulo", ascending=False).head(30)
f, ax = fig(9.5, 8.0)
rot = [f"{r.tabela}.{r.coluna}" for r in d.itertuples()]
cor = [STATUS["critical"] if v == 100 else
       STATUS["serious"] if v >= 50 else STATUS["warning"]
       for v in d.pct_nulo]
y = np.arange(len(d))
ax.barh(y, d.pct_nulo, color=cor, height=0.66)
ax.set_yticks(y, rot)
ax.invert_yaxis()
sem_grade(ax)
ax.set_xticks([])
ax.spines["left"].set_visible(False)
ax.spines["bottom"].set_visible(False)
for yi, v in zip(y, d.pct_nulo):
    ax.text(v + 1.2, yi, f"{v:.1f}%", va="center", fontsize=8, color=INK2)
ax.set_xlim(0, 116)
handles = [mpl.patches.Patch(color=STATUS[k], label=lab) for k, lab in
           [("critical", "vazia (100%)"), ("serious", "≥50% nula"),
            ("warning", "<50% nula")]]
ax.legend(handles=handles, ncol=3, loc="lower right", bbox_to_anchor=(1, -0.07))
titulo(ax, "Colunas com valores ausentes — 30 maiores",
       "percentual de linhas sem valor na coluna")
plt.tight_layout()
plt.show()
'''
)

md("## 2.2. Cardinalidade e colunas constantes")

code(
    '''
# Coluna constante não separa nada: ou o campo foi zerado na sanitização, ou o
# recorte cedido tem um valor só. Em ambos os casos ela não serve de dimensão.
card = []
for t in TABLES:
    n = inv.loc[inv.tabela == t, "linhas"].iloc[0]
    if n == 0:
        continue
    cols = q(f"SELECT * FROM {t} LIMIT 0").columns
    expr = ", ".join(f'count(DISTINCT "{c}") AS "{c}"' for c in cols)
    distintos = q(f"SELECT {expr} FROM {t}").iloc[0]
    for c in cols:
        card.append({"tabela": t, "coluna": c, "distintos": int(distintos[c]),
                     "linhas": n, "razao": distintos[c] / n})

card = pd.DataFrame(card)
const = card[(card.distintos <= 1) & (card.linhas > 100)]
print(f"{len(const)} colunas constantes ou vazias em tabelas com >100 linhas:")
const.merge(nulos.drop(columns="linhas"), on=["tabela", "coluna"])[
    ["tabela", "coluna", "distintos", "pct_nulo", "linhas"]
].reset_index(drop=True)
'''
)

code(
    '''
# Dimensões de alta cardinalidade são as candidatas naturais a recorte de
# investigação — e as que mais pesam no custo de uma suíte comercial cobrada
# por cardinalidade.
d = card[(card.distintos > 1) & (~card.coluna.isin(COL_TEMPO.values()))]
d = d.sort_values("distintos", ascending=False).head(22)
f, ax = fig(9.5, 6.4)
barras_h(ax, [f"{r.tabela}.{r.coluna}" for r in d.itertuples()],
         d.distintos.values, color=CAT[0])
titulo(ax, "Dimensões de maior cardinalidade",
       "valores distintos por coluna, excluindo colunas de tempo")
plt.tight_layout()
plt.show()
'''
)

md("## 2.3. Integridade: chaves e referências")

code(
    '''
# Chaves primárias declaradas no DDL. Duplicata aqui indicaria falha do dump.
PK = {
    "signal_point": ["ts", "source", "entity", "metric"],
    "signal_bucket": ["source", "entity", "metric", "bts"],
    "prom_point": ["epoch_ms", "series_id"],
    "rpaas_bucket": ["bucket_ts_ms", "region", "vhost"],
    "ca_point": ["ts_ms", "app", "blocked"],
    "service_overview": ["timestamp", "app_name"],
    "operation_metrics": ["start_ts", "operation_name"],
    "field_metrics": ["start_ts", "coordinate"],
    "tsuru_event": ["start_time_ms", "uniqueid"],
    "player_hourly": ["hour_ts", "player"],
    "device_hourly": ["hour_ts", "device"],
    "geo_hourly": ["hour_ts", "state_province", "isp"],
    "live_qoe_hourly": ["hour_ts", "sinal"],
    "player_live_hourly": ["hour_ts", "player"],
    "live_active_15min": ["bucket_ts", "sinal"],
    "live_error_attr_hourly": ["hour_ts", "sinal", "cdn", "tier",
                               "http_code", "error_name"],
    "error_cat_hourly": ["hour_ts", "kind", "category"],
    "incidents": ["opened_at", "sys_id"],
    "incidents_platform": ["opened_at", "sys_id"],
    "incident_label": ["id"],
    "live_event": ["tid", "start_ts"],
    "prom_series": ["series_id"], "prom_query": ["query_id"],
}

res = []
for t, k in PK.items():
    if t not in TABLES:
        continue
    cols = ", ".join(k)
    r = q(f"SELECT count(*) n, count(DISTINCT ({cols})) d FROM {t}").iloc[0]
    res.append({"tabela": t, "pk": " + ".join(k), "linhas": int(r.n),
                "pk_distintas": int(r.d), "duplicatas": int(r.n - r.d)})

pk = pd.DataFrame(res)
print("PKs com duplicata:", (pk.duplicatas > 0).sum(), "de", len(pk))
pk.sort_values("duplicatas", ascending=False).reset_index(drop=True)
'''
)

code(
    '''
# Integridade referencial do subsistema Prometheus, o único com FK declarada:
# prom_point -> prom_series -> prom_query.
print(q("""
    SELECT 'pontos sem série'  AS verificacao,
           count(*)            AS violacoes
    FROM prom_point p LEFT JOIN prom_series s USING (series_id)
    WHERE s.series_id IS NULL
    UNION ALL
    SELECT 'séries sem query',  count(*)
    FROM prom_series s LEFT JOIN prom_query qy USING (query_id)
    WHERE qy.query_id IS NULL
    UNION ALL
    SELECT 'séries sem ponto',  count(*)
    FROM prom_series s LEFT JOIN (SELECT DISTINCT series_id FROM prom_point) p
      USING (series_id)
    WHERE p.series_id IS NULL
    UNION ALL
    SELECT 'queries sem série', count(*)
    FROM prom_query qy LEFT JOIN (SELECT DISTINCT query_id FROM prom_series) s
      USING (query_id)
    WHERE s.query_id IS NULL
""").to_string(index=False))

# signal_bucket deveria ser a reamostragem de signal_point: as chaves batem?
print()
print(q("""
    SELECT count(*) FILTER (WHERE p.source IS NULL) AS so_em_bucket,
           count(*) FILTER (WHERE b.source IS NULL) AS so_em_point,
           count(*) FILTER (WHERE p.source IS NOT NULL
                              AND b.source IS NOT NULL) AS em_ambos
    FROM (SELECT DISTINCT source, metric FROM signal_bucket) b
    FULL OUTER JOIN (SELECT DISTINCT source, metric FROM signal_point) p
      USING (source, metric)
""").to_string(index=False))
'''
)

md("## 2.4. Continuidade das séries temporais")

code(
    '''
# Um buraco na série é indistinguível de "métrica zerada" para quem lê o
# gráfico. Como os timestamps brutos têm jitter (seção 1.3), a continuidade é
# medida por ocupação da grade horária: toda hora do intervalo coberto pela
# tabela deveria ter ao menos uma linha.
res = []
for t, c in COL_TEMPO.items():
    if t not in TABLES or t in EVENTOS:
        continue
    n = inv.loc[inv.tabela == t, "linhas"].iloc[0]
    if n < 1000:
        continue
    r = q(f"""
        WITH h AS (
            SELECT ({c} // 3600000) * 3600000 AS hora, count(*) linhas
            FROM {t} GROUP BY 1
        )
        SELECT count(*) horas_obs, min(hora) a, max(hora) b,
               median(linhas) linhas_medianas,
               count(*) FILTER (WHERE linhas < 0.5 * (SELECT median(linhas) FROM h))
                   AS horas_rarefeitas
        FROM h
    """).iloc[0]
    esperadas = int((r.b - r.a) / 3600000) + 1
    res.append({"tabela": t, "horas_obs": int(r.horas_obs),
                "horas_esp": esperadas,
                "cobertura_pct": 100 * r.horas_obs / esperadas,
                "horas_vazias": esperadas - int(r.horas_obs),
                "linhas_por_hora": int(r.linhas_medianas),
                "horas_rarefeitas": int(r.horas_rarefeitas)})

cont = pd.DataFrame(res).sort_values("cobertura_pct").reset_index(drop=True)
cont
'''
)

code(
    '''
d = cont.sort_values("cobertura_pct")
f, ax = fig(9.5, 4.2)
y = np.arange(len(d))
cor = [STATUS["good"] if v >= 99 else STATUS["warning"] if v >= 90
       else STATUS["critical"] for v in d.cobertura_pct]
ax.barh(y, d.cobertura_pct, color=cor, height=0.62)
ax.set_yticks(y, d.tabela)
ax.invert_yaxis()
ax.axvline(100, color=INK3, lw=1, ls=(0, (3, 3)))
sem_grade(ax)
ax.set_xticks([])
ax.spines["left"].set_visible(False)
ax.spines["bottom"].set_visible(False)
for yi, v, fal, rar in zip(y, d.cobertura_pct, d.horas_vazias, d.horas_rarefeitas):
    partes = [f"{v:.1f}%"]
    if fal:
        partes.append(f"{fal:,} h sem dado")
    if rar:
        partes.append(f"{rar:,} h rarefeitas")
    ax.text(v + 0.6, yi, "  ·  ".join(partes), va="center", fontsize=8, color=INK2)
ax.set_xlim(0, 132)
titulo(ax, "Continuidade da coleta, hora a hora",
       "horas com ao menos uma linha sobre o total de horas do intervalo coberto")
plt.tight_layout()
plt.show()
'''
)

md(
    """
"Horas rarefeitas" são horas presentes na base, mas com menos da metade do
volume mediano de linhas — degradação parcial da coleta, que não aparece como
buraco e por isso é o modo de falha mais traiçoeiro: a série continua desenhando,
só que sobre menos amostras.
"""
)

md("## 2.5. Valores fora do domínio esperado")

code(
    '''
# Regras de sanidade derivadas do significado de cada campo: contagem não é
# negativa, percentual vive em [0,100], Apdex em [0,1], percentis são monótonos.
checagens = [
    ("signal_bucket", "taxa de erro % fora de [0,100]",
     "metric LIKE '%rate_pct' AND (value < 0 OR value > 100)"),
    ("service_overview", "apdex fora de [0,1]",
     "apdex_score < 0 OR apdex_score > 1"),
    ("service_overview", "error_rate_pct fora de [0,100]",
     "error_rate_pct < 0 OR error_rate_pct > 100"),
    ("service_overview", "throughput negativo", "throughput_rpm < 0"),
    ("service_overview", "tempo de resposta negativo", "response_time_avg_ms < 0"),
    ("operation_metrics", "erros > requisições", "error_count > request_count"),
    ("operation_metrics", "percentis não monótonos (p50>p90 ou p90>p99)",
     "p50_ms > p90_ms OR p90_ms > p99_ms"),
    ("field_metrics", "erros > requisições", "error_count > request_count"),
    ("rpaas_bucket", "soma de status ≠ total",
     "requests_2xx + requests_3xx + requests_4xx + requests_5xx <> requests_total"),
    ("rpaas_bucket", "percentis não monótonos",
     "p50_ms > p90_ms OR p90_ms > p95_ms OR p95_ms > p99_ms"),
    ("rpaas_bucket", "contagem negativa", "requests_total < 0"),
    ("ca_point", "rps negativo", "rps < 0"),
    ("player_hourly", "erros > sessões", "errors > sessions"),
    ("device_hourly", "erros > sessões", "errors > sessions"),
    ("geo_hourly", "erros > sessões", "errors > sessions"),
    ("live_qoe_hourly", "erros > sessões", "errors > sessions"),
    ("live_qoe_hourly", "erros de startup > erros", "startup_errors > errors"),
    ("live_qoe_hourly", "bufferratio fora de [0,100]",
     "bufferratio_avg < 0 OR bufferratio_avg > 100"),
    ("live_qoe_hourly", "latência p50 > p95", "latency_ms_p50 > latency_ms_p95"),
    ("player_live_hourly", "erros > sessões", "errors > sessions"),
    ("live_active_15min", "sessões com erro > ativas",
     "active_with_error > active_sessions"),
    ("live_active_15min", "latência p50 > p95", "latency_ms_p50 > latency_ms_p95"),
    ("incidents", "resolvido antes de aberto", "resolved_at < opened_at"),
    ("incidents", "fechado antes de resolvido", "closed_at < resolved_at"),
    ("incidents_platform", "resolvido antes de aberto", "resolved_at < opened_at"),
    ("live_event", "fim antes do início", "end_ts < start_ts"),
    ("tsuru_event", "duração negativa", "duration_ms < 0"),
    ("incident_label", "fim antes do início", "ts_end < ts_start"),
]

res = []
for t, nome, cond in checagens:
    if t not in TABLES:
        continue
    n = q(f"SELECT count(*) n FROM {t} WHERE {cond}").n.iloc[0]
    tot = inv.loc[inv.tabela == t, "linhas"].iloc[0]
    res.append({"tabela": t, "regra": nome, "violacoes": int(n),
                "pct": 100 * n / tot if tot else 0})

san = pd.DataFrame(res)
print(f"{(san.violacoes > 0).sum()} de {len(san)} regras violadas")
san[san.violacoes > 0].sort_values("violacoes", ascending=False).reset_index(drop=True)
'''
)

code(
    '''
ok = san[san.violacoes == 0]
print(f"regras sem nenhuma violação ({len(ok)}):")
for r in ok.itertuples():
    print(f"  ✓ {r.tabela:<22} {r.regra}")
'''
)

# =========================================================================== #
# 3. Telemetria de infraestrutura
# =========================================================================== #

md(
    """
---
# 3. Telemetria de infraestrutura

Sete fontes distintas descrevem a mesma cadeia de entrega por ângulos
diferentes: borda (RPaaS), proteção (Cloud Armor), plataforma (Prometheus,
Tsuru), aplicação (New Relic) e API (Apollo/GraphQL). O interesse aqui é duplo —
entender o que cada fonte mede e verificar se elas contam a mesma história sobre
os mesmos instantes.
"""
)

md("## 3.1. Sinais normalizados: `signal_point` e `signal_bucket`")

md(
    """
`signal_point` é o barramento normalizado do Argus: toda fonte deságua nele com
o mesmo formato `(ts, source, entity, metric, value, tags)`. `signal_bucket` é a
reamostragem desse barramento em janelas fixas. É a estrutura mais próxima do
"vocabulário comum" que o projeto propõe, e por isso vale entender sua forma.
"""
)

code(
    '''
sp = q("""
    SELECT source,
           count(*)                 linhas,
           count(DISTINCT entity)   entidades,
           count(DISTINCT metric)   metricas,
           count(DISTINCT ts)       instantes,
           to_timestamp(min(ts)/1000) inicio,
           to_timestamp(max(ts)/1000) fim,
           100.0 * count(tags) / count(*) pct_com_tags
    FROM signal_point GROUP BY 1 ORDER BY 2 DESC
""")
sp
'''
)

code(
    '''
f, (a1, a2) = plt.subplots(1, 2, figsize=(9.5, 3.6))
barras_h(a1, sp.source, sp.linhas.values, color=CAT[0])
titulo(a1, "Volume por fonte", "linhas em signal_point")
barras_h(a2, sp.source, sp.entidades.values, color=CAT[2])
titulo(a2, "Entidades distintas por fonte", "cardinalidade do campo entity")
plt.tight_layout()
plt.show()
'''
)

code(
    '''
# Matriz fonte × métrica: mostra o vocabulário real de cada coletor e onde há
# sobreposição semântica entre fontes.
m = q("""
    SELECT source, metric, count(*) n FROM signal_point GROUP BY 1, 2
""").pivot(index="metric", columns="source", values="n").fillna(0)
m = m.loc[m.sum(axis=1).sort_values(ascending=False).index]

f, ax = fig(max(6.5, 0.85 * len(m.columns) + 4), max(3.5, 0.26 * len(m)))
# ausência de par fonte×métrica é vazio, não "valor baixo": células zeradas
# recebem a cor da superfície em vez do passo mais claro da rampa.
dados = np.ma.masked_where(m.values == 0, np.log10(m.values + 1))
cmap = SEQ_CMAP.copy()
cmap.set_bad(SURFACE)
im = ax.imshow(dados, cmap=cmap, aspect="auto")
ax.set_xticks(range(len(m.columns)), m.columns, rotation=30, ha="right")
ax.set_yticks(range(len(m)), m.index)
sem_grade(ax)
for s in ax.spines.values():
    s.set_visible(False)
for i in range(len(m)):
    for j in range(len(m.columns)):
        v = m.values[i, j]
        if v:
            ax.text(j, i, f"{v:,.0f}", ha="center", va="center", fontsize=7,
                    color="#ffffff" if dados[i, j] > dados.max() * 0.6 else INK)
titulo(ax, "Métricas por fonte em signal_point",
       "contagem de pontos; cor em escala log")
plt.tight_layout()
plt.show()
'''
)

code(
    '''
# signal_bucket cobre mais fontes que signal_point — vale ver as duas lado a lado.
sb = q("""
    SELECT source, count(*) linhas, count(DISTINCT entity) entidades,
           count(DISTINCT metric) metricas, count(DISTINCT bts) instantes,
           to_timestamp(min(bts)/1000) inicio, to_timestamp(max(bts)/1000) fim
    FROM signal_bucket GROUP BY 1 ORDER BY 2 DESC
""")
sb
'''
)

code(
    '''
d = q("""
    SELECT source, metric, count(*) n, avg(value) media, median(value) mediana,
           min(value) minimo, max(value) maximo, stddev(value) desvio
    FROM signal_bucket GROUP BY 1, 2 HAVING count(*) > 200
    ORDER BY n DESC LIMIT 25
""")
d
'''
)

md("## 3.2. Borda: `rpaas_bucket`")

md(
    """
O RPaaS é o proxy reverso na frente das APIs. Cada linha agrega, por região e
por vhost, o volume por classe de status HTTP e — em tese — os percentis de
latência. É o ponto da cadeia onde um erro de backend vira erro visível para o
cliente.
"""
)

code(
    '''
# Antes de usar a tabela, verificar quais colunas de fato chegaram preenchidas.
q("""
    SELECT count(*) linhas,
           count(requests_total) tem_total, count(requests_5xx) tem_5xx,
           count(p50_ms) tem_p50, count(p90_ms) tem_p90,
           count(p95_ms) tem_p95, count(p99_ms) tem_p99,
           count(latency_samples) tem_amostras
    FROM rpaas_bucket
""")
'''
)

md(
    """
> **Toda a dimensão de latência da borda está ausente.** As quatro colunas de
> percentil e o campo `latency_samples` são integralmente nulos nas 52.560
> linhas. O que sobra de `rpaas_bucket` é contagem por classe de status HTTP.
>
> Isso remove da análise justamente o sinal que distinguiria "a borda está
> lenta" de "a borda está falhando" — e lentidão sem erro é o modo de
> degradação que o projeto se propõe a detectar. Os gráficos de latência desta
> subseção estão, por isso, omitidos, e a correlação da seção 7.2 não inclui
> percentis de borda.
"""
)

code(
    '''
r = q("""
    SELECT count(*) linhas, count(DISTINCT vhost) vhosts,
           count(DISTINCT region) regioes, count(DISTINCT bucket_ts_ms) instantes,
           to_timestamp(min(bucket_ts_ms)/1000) inicio,
           to_timestamp(max(bucket_ts_ms)/1000) fim,
           sum(requests_total) requisicoes,
           100.0 * sum(requests_5xx) / nullif(sum(requests_total), 0) pct_5xx,
           100.0 * sum(requests_4xx) / nullif(sum(requests_total), 0) pct_4xx
    FROM rpaas_bucket
""").iloc[0]
for k, v in r.items():
    print(f"  {k:<14} {v:,.4g}" if isinstance(v, (int, float)) else f"  {k:<14} {v}")

q("""
    SELECT region, count(DISTINCT vhost) vhosts, sum(requests_total) requisicoes,
           100.0*sum(requests_2xx)/nullif(sum(requests_total),0) pct_2xx,
           100.0*sum(requests_3xx)/nullif(sum(requests_total),0) pct_3xx,
           100.0*sum(requests_4xx)/nullif(sum(requests_total),0) pct_4xx,
           100.0*sum(requests_5xx)/nullif(sum(requests_total),0) pct_5xx
    FROM rpaas_bucket GROUP BY 1 ORDER BY requisicoes DESC
""")
'''
)

code(
    '''
d = q("""
    SELECT vhost, sum(requests_total) req,
           100.0*sum(requests_4xx)/nullif(sum(requests_total),0) pct_4xx,
           100.0*sum(requests_5xx)/nullif(sum(requests_total),0) pct_5xx
    FROM rpaas_bucket GROUP BY 1 ORDER BY req DESC LIMIT 15
""")

f, (a1, a2) = plt.subplots(1, 2, figsize=(10.5, 5.0))
barras_h(a1, d.vhost, d.req.values, color=CAT[0], fmt="{:,.0f}")
titulo(a1, "Volume por vhost", "requisições totais no período")

# taxa de erro: 4xx e 5xx são categorias diferentes, não uma pilha de magnitude
y = np.arange(len(d))
a2.barh(y - 0.19, d.pct_4xx, height=0.34, color=CAT[3], label="4xx (cliente)")
a2.barh(y + 0.19, d.pct_5xx, height=0.34, color=CAT[7], label="5xx (servidor)")
a2.set_yticks(y, ["" for _ in y])
a2.invert_yaxis()
sem_grade(a2)
a2.grid(True, axis="x")
a2.set_axisbelow(True)
a2.spines["left"].set_visible(False)
a2.set_xlabel("% das requisições do vhost")
a2.legend(ncol=1, loc="lower right")
titulo(a2, "Taxa de erro por vhost", "mesma ordem do gráfico à esquerda")
plt.tight_layout()
plt.show()
'''
)

code(
    '''
# Série temporal do tráfego e do erro na borda. Duas grandezas de escala
# diferente pedem dois painéis, nunca dois eixos y no mesmo painel.
d = q("""
    SELECT to_timestamp(bucket_ts_ms/1000) t, region,
           sum(requests_total) req,
           100.0*sum(requests_5xx)/nullif(sum(requests_total),0) pct_5xx
    FROM rpaas_bucket GROUP BY 1, 2 ORDER BY 1
""")

f, (a1, a2) = plt.subplots(2, 1, figsize=(9.5, 5.6), sharex=True)
for i, (reg, g) in enumerate(d.groupby("region")):
    a1.plot(g.t, g.req, color=CAT[i % len(CAT)], label=reg, lw=1.6)
    a2.plot(g.t, g.pct_5xx, color=CAT[i % len(CAT)], lw=1.6)
a1.legend(ncol=6, loc="upper left", bbox_to_anchor=(0, 1.30))
a1.set_ylabel("requisições / bucket")
a2.set_ylabel("% 5xx")
titulo(a1, "Tráfego e erro na borda, por região")
titulo(a2, "")
plt.tight_layout()
plt.show()
'''
)

code(
    '''
# Vhosts em que o 4xx deixa de ser exceção e vira o comportamento dominante.
q("""
    SELECT vhost, sum(requests_total) req,
           100.0*sum(requests_4xx)/nullif(sum(requests_total),0) pct_4xx,
           100.0*sum(requests_5xx)/nullif(sum(requests_total),0) pct_5xx
    FROM rpaas_bucket GROUP BY 1
    HAVING sum(requests_total) > 1e6 AND pct_4xx > 10
    ORDER BY pct_4xx DESC
""")
'''
)

md(
    """
Vários vhosts operam com **taxa de 4xx na casa das dezenas de por cento** —
`preferences`, `ratings`, `epg-api`, `download`, `affiliates`. Um 4xx é erro de
cliente, não de servidor, e por isso costuma ser filtrado dos alarmes; a
operação olha 5xx. Mas uma taxa dessa magnitude quase nunca significa "os
clientes estão errando": significa contrato de API mal ajustado, autenticação
expirando, ou o app pedindo recurso que não existe.

Para este projeto isso importa por dois motivos. Primeiro, é ruído de fundo
altíssimo — qualquer detector que use 4xx como sinal precisa de uma linha de
base **por vhost**, nunca de um limiar global. Segundo, parte desse volume pode
ser degradação real de experiência que hoje ninguém investiga porque não é 5xx.
"""
)

md("## 3.3. Prometheus: `prom_query`, `prom_series`, `prom_point`")

code(
    '''
print(q("""
    SELECT (SELECT count(*) FROM prom_query)  AS queries,
           (SELECT count(*) FROM prom_series) AS series,
           (SELECT count(*) FROM prom_point)  AS pontos,
           (SELECT count(DISTINCT epoch_ms) FROM prom_point) AS instantes,
           (SELECT count(DISTINCT service_label) FROM prom_series) AS servicos,
           (SELECT count(DISTINCT panel_title) FROM prom_query) AS paineis
""").to_string(index=False))

q("""
    SELECT qy.section, count(DISTINCT qy.query_id) queries,
           count(DISTINCT s.series_id) series,
           sum(qy.enabled) queries_ativas
    FROM prom_query qy LEFT JOIN prom_series s USING (query_id)
    GROUP BY 1 ORDER BY series DESC NULLS LAST LIMIT 20
""")
'''
)

code(
    '''
# Quantas séries cada query gera é a medida direta da cardinalidade que o
# Prometheus impõe — e do custo que ela representaria numa suíte cobrada por série.
d = q("""
    SELECT qy.panel_title, qy.query_id, count(s.series_id) series,
           count(p.epoch_ms) pontos
    FROM prom_query qy
    LEFT JOIN prom_series s USING (query_id)
    LEFT JOIN prom_point p ON p.series_id = s.series_id
    GROUP BY 1, 2 ORDER BY pontos DESC LIMIT 15
""")
f, ax = fig(9.5, 5.2)
rot = [f"{(t or '(sem título)')[:52]}" for t in d.panel_title]
barras_h(ax, rot, d.pontos.values, color=CAT[0])
titulo(ax, "Painéis que mais geram pontos",
       "total de amostras coletadas por painel do Grafana")
plt.tight_layout()
plt.show()

q("""
    SELECT count(*) series,
           min(cnt) minimo, median(cnt) mediana,
           quantile_cont(cnt, 0.9) p90, max(cnt) maximo
    FROM (SELECT series_id, count(*) cnt FROM prom_point GROUP BY 1)
""")
'''
)

code(
    '''
d = q("""
    SELECT coalesce(nullif(s.service_label, ''), '(sem rótulo)') servico,
           count(DISTINCT s.series_id) series, count(p.epoch_ms) pontos
    FROM prom_series s LEFT JOIN prom_point p USING (series_id)
    GROUP BY 1 ORDER BY pontos DESC LIMIT 18
""")
f, ax = fig(9.5, 5.6)
barras_h(ax, d.servico, d.pontos.values, color=CAT[0])
titulo(ax, "Serviços mais instrumentados no Prometheus",
       "pontos coletados por service_label")
plt.tight_layout()
plt.show()
'''
)

md("## 3.4. APM de aplicação: `service_overview`")

code(
    '''
d = q("""
    SELECT app_name,
           count(*) amostras,
           avg(response_time_avg_ms) tempo_ms,
           avg(throughput_rpm) rpm,
           avg(error_rate_pct) erro_pct,
           max(error_rate_pct) erro_max_pct,
           avg(apdex_score) apdex,
           min(apdex_score) apdex_min
    FROM service_overview GROUP BY 1 ORDER BY rpm DESC
""")
print(f"{len(d)} aplicações monitoradas | "
      f"{q('SELECT count(*) n FROM service_overview').n.iloc[0]:,} amostras")
d
'''
)

code(
    '''
# Apdex resume a satisfação do usuário; taxa de erro resume a falha dura. Um
# scatter mostra que as duas não são redundantes.
f, ax = fig(9.5, 4.6)
sem_grade(ax)
ax.grid(True, axis="both")
ax.set_axisbelow(True)
tam = 40 + 260 * (d.rpm / d.rpm.max())
ax.scatter(d.erro_pct, d.apdex, s=tam, color=CAT[0], alpha=0.75,
           edgecolor=SURFACE, linewidth=2, zorder=3)
for r in d.itertuples():
    if r.erro_pct > d.erro_pct.quantile(0.75) or r.apdex < d.apdex.quantile(0.25):
        ax.annotate(r.app_name[:26], (r.erro_pct, r.apdex), fontsize=7.5,
                    color=INK2, xytext=(6, 4), textcoords="offset points")
ax.axhline(0.94, color=STATUS["warning"], lw=1, ls=(0, (3, 3)))
ax.text(ax.get_xlim()[1], 0.94, " apdex 0,94 ", fontsize=7.5,
        color=STATUS["warning"], va="center", ha="right")
ax.set_xlabel("taxa de erro média (%)")
ax.set_ylabel("Apdex médio")
titulo(ax, "Apdex × taxa de erro por aplicação",
       "área do círculo proporcional ao throughput médio (rpm)")
plt.tight_layout()
plt.show()
'''
)

code(
    '''
# Série temporal das aplicações de maior volume.
top = d.nlargest(6, "rpm").app_name.tolist()
lista = ", ".join(f"'{a}'" for a in top)
s = q(f"""
    SELECT to_timestamp(timestamp/1000) t, app_name, error_rate_pct, apdex_score
    FROM service_overview WHERE app_name IN ({lista}) ORDER BY 1
""")
f, (a1, a2) = plt.subplots(2, 1, figsize=(9.5, 5.8), sharex=True)
for i, app in enumerate(top):
    g = s[s.app_name == app]
    a1.plot(g.t, g.error_rate_pct, color=CAT[i], label=app[:30], lw=1.4)
    a2.plot(g.t, g.apdex_score, color=CAT[i], lw=1.4)
a1.legend(ncol=3, loc="upper left", bbox_to_anchor=(0, 1.42), fontsize=8)
a1.set_ylabel("taxa de erro (%)")
a2.set_ylabel("Apdex")
titulo(a1, "Erro e Apdex das seis aplicações de maior throughput")
plt.tight_layout()
plt.show()
'''
)

md("## 3.5. GraphQL: `operation_metrics` e `field_metrics`")

code(
    '''
print(q("""
    SELECT count(*) linhas, count(DISTINCT operation_name) operacoes,
           to_timestamp(min(start_ts)/1000) inicio,
           to_timestamp(max(start_ts)/1000) fim,
           sum(request_count) requisicoes, sum(error_count) erros,
           100.0*sum(error_count)/nullif(sum(request_count),0) pct_erro
    FROM operation_metrics
""").to_string(index=False))

d = q("""
    SELECT operation_name, sum(request_count) req, sum(error_count) err,
           100.0*sum(error_count)/nullif(sum(request_count),0) pct_erro,
           median(p50_ms) p50, median(p90_ms) p90, median(p99_ms) p99
    FROM operation_metrics GROUP BY 1 ORDER BY req DESC LIMIT 20
""")
d
'''
)

code(
    '''
f, (a1, a2) = plt.subplots(1, 2, figsize=(11.0, 5.4))
top = d.head(12)
barras_h(a1, [o[:34] for o in top.operation_name], top.req.values, color=CAT[0])
titulo(a1, "Operações GraphQL por volume", "requisições no período")

# Percentis são um perfil ordenado da mesma grandeza: escala sequencial de um tom.
y = np.arange(len(top))
for j, (col, cor, lab) in enumerate([("p50", SEQ[2], "p50"), ("p90", SEQ[4], "p90"),
                                     ("p99", SEQ[6], "p99")]):
    a2.barh(y + (j - 1) * 0.26, top[col], height=0.24, color=cor, label=lab)
a2.set_yticks(y, ["" for _ in y])
a2.invert_yaxis()
sem_grade(a2)
a2.grid(True, axis="x")
a2.set_axisbelow(True)
a2.set_xscale("log")
a2.spines["left"].set_visible(False)
a2.set_xlabel("latência (ms, escala log)")
a2.legend(ncol=3, loc="lower right", bbox_to_anchor=(1, -0.16))
titulo(a2, "Latência por operação", "mediana de cada percentil; mesma ordem")
plt.tight_layout()
plt.show()
'''
)

code(
    '''
print(q("""
    SELECT count(*) linhas, count(DISTINCT coordinate) coordenadas,
           sum(request_count) req, sum(error_count) err,
           sum(observed_exec) execucoes
    FROM field_metrics
""").to_string(index=False))

q("""
    SELECT coordinate, sum(request_count) req, sum(error_count) err,
           100.0*sum(error_count)/nullif(sum(request_count),0) pct_erro,
           sum(observed_exec) execucoes
    FROM field_metrics GROUP BY 1 ORDER BY req DESC LIMIT 15
""")
'''
)

md("## 3.6. Proteção de borda: `ca_point`")

code(
    '''
print(q("""
    SELECT count(*) linhas, count(DISTINCT app) apps,
           count(DISTINCT backend_target) alvos,
           to_timestamp(min(ts_ms)/1000) inicio, to_timestamp(max(ts_ms)/1000) fim,
           sum(rps) FILTER (WHERE blocked = 1) rps_bloqueado,
           sum(rps) FILTER (WHERE blocked = 0) rps_permitido
    FROM ca_point
""").to_string(index=False))

d = q("""
    SELECT app,
           sum(rps) FILTER (WHERE blocked = 0) permitido,
           sum(rps) FILTER (WHERE blocked = 1) bloqueado,
           100.0 * sum(rps) FILTER (WHERE blocked = 1)
                 / nullif(sum(rps), 0) pct_bloqueado
    FROM ca_point GROUP BY 1 ORDER BY permitido DESC NULLS LAST LIMIT 15
""")
d
'''
)

code(
    '''
ativos = d.dropna(subset=["permitido"]).head(10)
f, ax = fig(9.5, 4.4)
y = np.arange(len(ativos))
ax.barh(y - 0.19, ativos.permitido, height=0.34, color=CAT[0], label="permitido")
ax.barh(y + 0.19, ativos.bloqueado.fillna(0), height=0.34, color=CAT[7],
        label="bloqueado")
ax.set_yticks(y, [a[:34] for a in ativos.app])
ax.invert_yaxis()
ax.set_xscale("log")
sem_grade(ax)
ax.grid(True, axis="x")
ax.set_axisbelow(True)
ax.spines["left"].set_visible(False)
ax.set_xlabel("soma de rps no período (escala log)")
ax.legend(ncol=2, loc="lower right", bbox_to_anchor=(1, -0.14))
titulo(ax, "Tráfego permitido e bloqueado por aplicação",
       "Cloud Armor — ca_point")
plt.tight_layout()
plt.show()
'''
)

md("## 3.7. Mudanças na plataforma: `tsuru_event`")

md(
    """
Deploys e alterações de escala são a hipótese de causa mais frequente em
incidentes de plataforma. O campo `kind` diz o que aconteceu; `error`, se deu
errado.
"""
)

code(
    '''
print(q("""
    SELECT count(*) eventos, count(DISTINCT target_value) alvos,
           count(DISTINCT kind) tipos,
           to_timestamp(min(start_time_ms)/1000) inicio,
           to_timestamp(max(start_time_ms)/1000) fim,
           count(*) FILTER (WHERE error IS NOT NULL AND error <> '') com_erro,
           median(duration_ms)/1000 duracao_mediana_s
    FROM tsuru_event
""").to_string(index=False))

d = q("""
    SELECT kind, count(*) n,
           count(*) FILTER (WHERE error IS NOT NULL AND error <> '') erros,
           100.0*count(*) FILTER (WHERE error IS NOT NULL AND error <> '')
               / count(*) pct_erro,
           median(duration_ms)/1000 dur_mediana_s,
           quantile_cont(duration_ms, 0.95)/1000 dur_p95_s
    FROM tsuru_event GROUP BY 1 ORDER BY n DESC LIMIT 20
""")
d
'''
)

code(
    '''
f, (a1, a2) = plt.subplots(1, 2, figsize=(11.0, 5.0))
top = d.head(12)
barras_h(a1, [k[:36] for k in top.kind], top.n.values, color=CAT[0])
titulo(a1, "Tipos de evento na plataforma", "contagem no período")
barras_h(a2, [k[:36] for k in top.kind], top.pct_erro.values,
         color=CAT[7], fmt="{:.1f}%")
titulo(a2, "Falha por tipo de evento", "% dos eventos com campo error preenchido")
plt.tight_layout()
plt.show()
'''
)

code(
    '''
d = q("""
    SELECT target_value app, count(*) eventos,
           count(*) FILTER (WHERE kind LIKE '%deploy%') deploys,
           count(*) FILTER (WHERE error IS NOT NULL AND error <> '') com_erro
    FROM tsuru_event GROUP BY 1 ORDER BY eventos DESC LIMIT 15
""")
f, ax = fig(9.5, 5.0)
barras_h(ax, [a[:40] for a in d.app], d.eventos.values, color=CAT[0])
titulo(ax, "Aplicações com mais mudanças", "eventos de plataforma por alvo")
plt.tight_layout()
plt.show()

# distribuição temporal — mudanças se concentram em horário comercial?
h = q("""
    SELECT extract('hour' FROM to_timestamp(start_time_ms/1000)) hora, count(*) n
    FROM tsuru_event GROUP BY 1 ORDER BY 1
""")
f, ax = fig(9.5, 3.2)
ax.bar(h.hora, h.n, color=CAT[0], width=0.7)
ax.set_xticks(range(0, 24, 2))
ax.set_xlabel("hora do dia (UTC)")
ax.set_ylabel("eventos")
titulo(ax, "Quando as mudanças acontecem",
       "distribuição horária dos eventos de plataforma")
plt.tight_layout()
plt.show()
'''
)

# =========================================================================== #
# 4. QoE
# =========================================================================== #

md(
    """
---
# 4. Qualidade de experiência (QoE)

Esta é a camada que enxerga o assinante. Enquanto a seção 3 mede se a
infraestrutura respondeu, aqui se mede se o vídeo **tocou** — e com que
qualidade. É a distinção que o caso de negócio chama de "degradação que não gera
erro": buffer alto e tempo de início ruim não acendem nenhum alarme de 5xx.
"""
)

md("## 4.1. Sessões e erros por player")

code(
    '''
d = q("""
    SELECT nullif(player, '') player, sum(sessions) sessoes, sum(errors) erros,
           100.0 * sum(errors) / nullif(sum(sessions), 0) pct_erro
    FROM player_hourly GROUP BY 1 ORDER BY sessoes DESC
""")
print(f"{len(d)} players distintos | {d.sessoes.sum():,.0f} sessões | "
      f"taxa de erro global {100 * d.erros.sum() / d.sessoes.sum():.2f}%")
d.head(20)
'''
)

code(
    '''
# Volume e taxa de erro respondem perguntas diferentes: o player que mais falha
# raramente é o que mais roda. Dois painéis, mesma ordem de linhas.
top = d.head(16).copy()
top["rotulo"] = top.player.fillna("(vazio)")
f, (a1, a2) = plt.subplots(1, 2, figsize=(11.0, 6.0))
barras_h(a1, top.rotulo, top.sessoes.values, color=CAT[0])
titulo(a1, "Sessões por player", "16 maiores no período")

media = 100 * d.erros.sum() / d.sessoes.sum()
cor = [STATUS["critical"] if v >= 3 * media else
       STATUS["warning"] if v >= media else CAT[2] for v in top.pct_erro]
y = np.arange(len(top))
a2.barh(y, top.pct_erro, color=cor, height=0.62)
a2.set_yticks(y, ["" for _ in y])
a2.invert_yaxis()
a2.axvline(media, color=INK3, lw=1, ls=(0, (3, 3)))
a2.text(media, -0.9, f" média global {media:.2f}%", fontsize=7.5, color=INK3)
sem_grade(a2)
a2.set_xticks([])
a2.spines["left"].set_visible(False)
a2.spines["bottom"].set_visible(False)
for yi, v in zip(y, top.pct_erro):
    a2.text(v + top.pct_erro.max() * 0.02, yi, f"{v:.2f}%", va="center",
            fontsize=8, color=INK2)
a2.set_xlim(0, top.pct_erro.max() * 1.25)
titulo(a2, "Taxa de erro por player", "mesma ordem do gráfico à esquerda")
plt.tight_layout()
plt.show()
'''
)

md(
    """
Existe um player com identificador **vazio** concentrando um volume de sessões
comparável ao dos maiores players nomeados, e com taxa de erro uma ordem de
grandeza acima da média. Não é um player: é o balde onde caem as sessões cuja
origem não foi identificada. Como sua taxa de erro é atípica, ele não pode ser
descartado como ruído — enquanto essas sessões não forem atribuídas, uma fatia
relevante do erro do produto fica sem dono.
"""
)

md("## 4.2. Concentração por dispositivo")

code(
    '''
d = q("""
    SELECT device, sum(sessions) sessoes, sum(errors) erros,
           100.0*sum(errors)/nullif(sum(sessions),0) pct_erro
    FROM device_hourly GROUP BY 1 ORDER BY sessoes DESC
""")
print(f"{len(d):,} modelos de dispositivo distintos")

# Curva de Pareto: quanto do tráfego mora na cauda longa?
acum = d.sessoes.cumsum() / d.sessoes.sum() * 100
n80 = int((acum <= 80).sum()) + 1
n95 = int((acum <= 95).sum()) + 1
f, ax = fig(9.5, 3.8)
ax.plot(np.arange(1, len(d) + 1), acum, color=CAT[0], lw=2)
ax.set_xscale("log")
ax.set_ylim(0, 101)
for n, lab in [(n80, "80%"), (n95, "95%")]:
    ax.plot([n], [acum.iloc[n - 1]], "o", color=CAT[1], ms=7,
            markeredgecolor=SURFACE, markeredgewidth=2, zorder=3)
    ax.annotate(f"{lab} das sessões\\nem {n:,} modelos", (n, acum.iloc[n - 1]),
                xytext=(10, -22), textcoords="offset points",
                fontsize=8, color=INK2)
ax.set_xlabel("modelos ordenados por volume (escala log)")
ax.set_ylabel("% acumulado das sessões")
titulo(ax, "Concentração do tráfego por modelo de dispositivo",
       f"{len(d):,} modelos no parque — a cauda é longa, mas o topo é estreito")
plt.tight_layout()
plt.show()

d.head(15)
'''
)

code(
    '''
# Onde a falha se concentra: modelos com volume relevante e erro muito acima da
# média são exatamente o recorte que a média nacional esconde.
media = 100 * d.erros.sum() / d.sessoes.sum()
corte = d.sessoes.quantile(0.985)
risco = d[d.sessoes >= corte].nlargest(15, "pct_erro")
f, ax = fig(9.5, 5.2)
barras_h(ax, [x[:44] for x in risco.device], risco.pct_erro.values,
         color=STATUS["critical"], fmt="{:.2f}%")
ax.axvline(media, color=INK3, lw=1, ls=(0, (3, 3)))
ax.text(media, -0.85, f" média global {media:.2f}%", fontsize=7.5, color=INK3)
titulo(ax, "Modelos de maior taxa de erro entre os de alto volume",
       f"apenas modelos acima do percentil 98,5 de sessões ({corte:,.0f}+)")
plt.tight_layout()
plt.show()
'''
)

md("## 4.3. Geografia e operadora")

code(
    '''
# A tabela promete o cruzamento UF × operadora. Vale verificar se ele existe.
cruz = q("""
    SELECT CASE WHEN state_province = '?' THEN 'UF ausente'
                ELSE 'UF preenchida' END AS uf,
           CASE WHEN isp = '?' THEN 'ISP ausente'
                ELSE 'ISP preenchido' END AS isp,
           count(*) linhas, sum(sessions) sessoes
    FROM geo_hourly GROUP BY 1, 2 ORDER BY linhas DESC
""")
cruz
'''
)

md(
    """
> **Achado crítico.** As duas dimensões são **mutuamente exclusivas**: não existe
> uma única linha com UF e operadora preenchidas ao mesmo tempo. A tabela é, na
> prática, a união de dois recortes marginais — sessões por UF (com operadora
> anonimizada) e sessões por operadora (com UF anonimizada).
>
> Isso tem consequência direta para o projeto. O caso de negócio sustenta que o
> diferencial da solução está em enxergar "a combinação de plataforma, modelo,
> versão, UF e operadora" — e é justamente essa combinação que a sanitização
> removeu. Uma falha que atinja *uma operadora em um estado* é indetectável
> neste dataset. O protótipo pode demonstrar o recorte por UF **ou** por
> operadora, nunca o cruzamento; qualquer requisito que dependa dele precisa ser
> negociado com o parceiro ou movido para dados de produção.
"""
)

code(
    '''
uf = q("""
    SELECT state_province uf, sum(sessions) sessoes, sum(errors) erros,
           100.0*sum(errors)/nullif(sum(sessions),0) pct_erro
    FROM geo_hourly WHERE state_province <> '?'
    GROUP BY 1 ORDER BY sessoes DESC
""")
isp = q("""
    SELECT isp, sum(sessions) sessoes, sum(errors) erros,
           100.0*sum(errors)/nullif(sum(sessions),0) pct_erro
    FROM geo_hourly WHERE isp <> '?'
    GROUP BY 1 ORDER BY sessoes DESC LIMIT 15
""")

f, (a1, a2) = plt.subplots(1, 2, figsize=(11.0, 5.4))
barras_h(a1, uf.head(15).uf, uf.head(15).sessoes.values, color=CAT[0])
titulo(a1, "Sessões por UF", f"{len(uf)} unidades federativas")
barras_h(a2, [i[:26] for i in isp.isp], isp.sessoes.values, color=CAT[2])
titulo(a2, "Sessões por operadora", "15 maiores — recorte separado do de UF")
plt.tight_layout()
plt.show()
'''
)

code(
    '''
# Erro por UF e por operadora, ordenados pela taxa e não pelo volume.
f, (a1, a2) = plt.subplots(1, 2, figsize=(11.0, 5.4))
a = uf.nlargest(15, "pct_erro")
barras_h(a1, a.uf, a.pct_erro.values, color=STATUS["serious"], fmt="{:.3f}%")
titulo(a1, "Taxa de erro por UF", "unidades com maior erro relativo")
b = q("""
    SELECT isp, sum(sessions) sessoes,
           100.0*sum(errors)/nullif(sum(sessions),0) pct_erro
    FROM geo_hourly WHERE isp <> '?' GROUP BY 1
    HAVING sum(sessions) > 100000 ORDER BY pct_erro DESC LIMIT 15
""")
barras_h(a2, [i[:26] for i in b.isp], b.pct_erro.values,
         color=STATUS["serious"], fmt="{:.3f}%")
titulo(a2, "Taxa de erro por operadora", "apenas operadoras com >100 mil sessões")
plt.tight_layout()
plt.show()
'''
)

md("## 4.4. QoE do ao vivo por sinal")

code(
    '''
d = q("""
    SELECT sinal, sum(sessions) sessoes, sum(errors) erros,
           100.0*sum(errors)/nullif(sum(sessions),0) pct_erro,
           100.0*sum(startup_errors)/nullif(sum(errors),0) pct_startup,
           avg(bufferratio_avg) buffer_pct, avg(jointime_s_avg) jointime_s,
           avg(latency_ms_avg) latencia_ms, avg(stalls_avg) travamentos,
           avg(bitrate_mbps_avg) bitrate_mbps, avg(dropped_frames_avg) frames_perdidos
    FROM live_qoe_hourly GROUP BY 1 ORDER BY sessoes DESC
""")
print(f"{len(d)} sinais ao vivo | {d.sessoes.sum():,.0f} sessões")
d.head(20)
'''
)

code(
    '''
# Volume x erro para os sinais principais; sinais de alto volume e alto erro são
# o alvo prioritário.
top = d.head(20)
f, ax = fig(9.5, 4.8)
sem_grade(ax)
ax.grid(True)
ax.set_axisbelow(True)
ax.scatter(top.sessoes, top.pct_erro, s=60 + 300 * top.buffer_pct / top.buffer_pct.max(),
           color=CAT[0], alpha=0.75, edgecolor=SURFACE, linewidth=2, zorder=3)
for r in top.itertuples():
    ax.annotate(r.sinal, (r.sessoes, r.pct_erro), fontsize=7.5, color=INK2,
                xytext=(7, 3), textcoords="offset points")
ax.set_xscale("log")
ax.set_xlabel("sessões (escala log)")
ax.set_ylabel("taxa de erro (%)")
titulo(ax, "Sinais ao vivo: volume × erro",
       "área do círculo proporcional ao buffer ratio médio")
plt.tight_layout()
plt.show()
'''
)

code(
    '''
# As métricas de QoE medem coisas diferentes ou são redundantes? A matriz de
# correlação responde — e escala divergente é a forma certa para polaridade.
cols = ["pct_erro", "buffer_pct", "jointime_s", "latencia_ms", "travamentos",
        "bitrate_mbps", "frames_perdidos"]
rot = ["taxa de erro", "buffer ratio", "join time", "latência",
       "travamentos", "bitrate", "frames perdidos"]
corr = d[cols].corr(method="spearman")

f, ax = fig(6.6, 5.4)
im = ax.imshow(corr.values, cmap=DIV_CMAP, vmin=-1, vmax=1)
ax.set_xticks(range(len(rot)), rot, rotation=35, ha="right")
ax.set_yticks(range(len(rot)), rot)
sem_grade(ax)
for s in ax.spines.values():
    s.set_visible(False)
for i in range(len(rot)):
    for j in range(len(rot)):
        v = corr.values[i, j]
        ax.text(j, i, f"{v:.2f}", ha="center", va="center", fontsize=7.5,
                color="#ffffff" if abs(v) > 0.55 else INK)
cb = f.colorbar(im, ax=ax, fraction=0.045, pad=0.03)
cb.outline.set_visible(False)
cb.set_label("correlação de Spearman", color=INK2, fontsize=8.5)
titulo(ax, "Correlação entre métricas de QoE",
       "por sinal ao vivo — azul: mesma direção, vermelho: direções opostas")
plt.tight_layout()
plt.show()
'''
)

md("## 4.5. Sessões ativas em janela de 15 minutos")

code(
    '''
s = q("""
    SELECT to_timestamp(bucket_ts/1000) t, sum(active_sessions) ativas,
           sum(active_with_error) com_erro, sum(joins_in_bucket) entradas
    FROM live_active_15min GROUP BY 1 ORDER BY 1
""")
f, (a1, a2) = plt.subplots(2, 1, figsize=(9.5, 5.6), sharex=True)
a1.plot(s.t, s.ativas, color=CAT[0], lw=1.4)
a1.set_ylabel("sessões ativas")
a2.plot(s.t, 100 * s.com_erro / s.ativas.replace(0, np.nan), color=CAT[7], lw=1.4)
a2.set_ylabel("% com erro")
titulo(a1, "Audiência ao vivo e erro, em janelas de 15 minutos")
pico = s.loc[s.ativas.idxmax()]
a1.annotate(f"pico: {pico.ativas:,.0f}\\n{pico.t:%d/%m %H:%M}",
            (pico.t, pico.ativas), xytext=(-70, -30),
            textcoords="offset points", fontsize=8, color=INK2)
plt.tight_layout()
plt.show()

# Perfil semanal: a operação precisa saber quando o risco é maior.
h = q("""
    SELECT extract('dow' FROM to_timestamp(bucket_ts/1000)) dow,
           extract('hour' FROM to_timestamp(bucket_ts/1000)) hora,
           avg(active_sessions) ativas
    FROM live_active_15min GROUP BY 1, 2
""").pivot(index="dow", columns="hora", values="ativas")
dias = ["dom", "seg", "ter", "qua", "qui", "sex", "sáb"]
f, ax = fig(9.5, 2.9)
im = ax.imshow(h.values, cmap=SEQ_CMAP, aspect="auto")
ax.set_yticks(range(len(h)), [dias[int(i)] for i in h.index])
ax.set_xticks(range(0, 24, 2), [f"{i:02d}h" for i in range(0, 24, 2)])
sem_grade(ax)
for sp in ax.spines.values():
    sp.set_visible(False)
cb = f.colorbar(im, ax=ax, fraction=0.03, pad=0.02)
cb.outline.set_visible(False)
cb.set_label("sessões ativas médias", color=INK2, fontsize=8.5)
titulo(ax, "Perfil semanal da audiência ao vivo", "média por dia da semana e hora (UTC)")
plt.tight_layout()
plt.show()
'''
)

md("## 4.6. Atribuição dos erros: CDN, camada e código HTTP")

code(
    '''
d = q("""
    SELECT cdn, tier, sum(errors) erros FROM live_error_attr_hourly
    GROUP BY 1, 2 ORDER BY erros DESC
""")
m = d.pivot(index="cdn", columns="tier", values="erros").fillna(0)
m = m.loc[m.sum(axis=1).sort_values(ascending=False).index]

f, (a1, a2) = plt.subplots(1, 2, figsize=(11.0, 4.2))
esq = np.zeros(len(m))
for i, col in enumerate(m.columns):
    a1.barh(np.arange(len(m)), m[col], left=esq, height=0.6,
            color=CAT[i % len(CAT)], label=col, edgecolor=SURFACE, linewidth=2)
    esq += m[col].values
a1.set_yticks(range(len(m)), m.index)
a1.invert_yaxis()
sem_grade(a1)
a1.grid(True, axis="x")
a1.set_axisbelow(True)
a1.spines["left"].set_visible(False)
a1.set_xlabel("erros")
a1.legend(ncol=3, loc="lower right", bbox_to_anchor=(1, -0.34))
titulo(a1, "Erros por CDN e camada", "empilhado por tier")

cod = q("""
    SELECT CASE WHEN http_code = '' THEN '(sem código)' ELSE http_code END AS codigo,
           sum(errors) erros
    FROM live_error_attr_hourly GROUP BY 1 ORDER BY erros DESC LIMIT 12
""")
barras_h(a2, cod.codigo, cod.erros.values, color=CAT[1])
titulo(a2, "Erros por código HTTP", "12 códigos mais frequentes")
plt.tight_layout()
plt.show()

q("""
    SELECT error_name, sum(errors) erros, count(DISTINCT sinal) sinais,
           count(DISTINCT cdn) cdns,
           100.0*sum(errors) FILTER (WHERE http_code = '')
               / nullif(sum(errors), 0) pct_sem_http
    FROM live_error_attr_hourly GROUP BY 1 ORDER BY erros DESC LIMIT 15
""")
'''
)

md(
    """
> **A grande maioria dos erros ao vivo não é um erro HTTP.** A categoria sem
> código concentra cerca de 95% do volume, e o que há dentro dela são falhas de
> player e de direito de acesso: `hls:networkError_manifestLoadError`,
> `resource-load-error`, `drm-not-supported`, `geo-fencing`,
> `user-not-authorized`.
>
> Esse é provavelmente o dado mais alinhado à tese do projeto em todo o dump.
> Um sistema que investigue incidentes olhando códigos de status na borda
> enxergaria 5% do problema. As falhas que realmente impedem o assinante de
> assistir acontecem **no cliente** — no parsing do manifesto, na negociação de
> DRM, na verificação de direito regional — e só aparecem em telemetria coletada
> no player. Justifica diretamente o requisito de uma API de ingestão que aceite
> eventos vindos da borda do parque de dispositivos.
"""
)

code(
    '''
# Categorias de erro separadas por tipo de conteúdo: ao vivo e sob demanda
# falham de formas diferentes, e isso muda a rota de investigação.
d = q("""
    SELECT kind, category, sum(errors) erros FROM error_cat_hourly
    GROUP BY 1, 2 ORDER BY erros DESC
""")
m = d.pivot(index="category", columns="kind", values="erros").fillna(0)
m = m.loc[m.sum(axis=1).sort_values(ascending=False).index]

f, ax = fig(9.5, 3.8)
y = np.arange(len(m))
for i, col in enumerate(m.columns):
    ax.barh(y + (i - 0.5) * 0.34, m[col], height=0.32, color=CAT[i],
            label={"live": "ao vivo", "vod": "sob demanda"}.get(col, col))
ax.set_yticks(y, m.index)
ax.invert_yaxis()
sem_grade(ax)
ax.grid(True, axis="x")
ax.set_axisbelow(True)
ax.spines["left"].set_visible(False)
ax.set_xlabel("erros no período")
ax.legend(ncol=2, loc="lower right", bbox_to_anchor=(1, -0.26))
titulo(ax, "Categorias de erro por tipo de conteúdo",
       "acesso domina os dois, mas entrega e origem pesam mais no ao vivo")
plt.tight_layout()
plt.show()
m
'''
)

md("## 4.7. Eventos ao vivo programados")

code(
    '''
q("""
    SELECT competition competicao, sport esporte, count(*) transmissoes,
           count(DISTINCT event_key) eventos,
           count(DISTINCT channel) canais,
           min(event_date) primeiro, max(event_date) ultimo,
           median((end_ts - start_ts)/60000.0) duracao_mediana_min
    FROM live_event GROUP BY 1, 2 ORDER BY transmissoes DESC
""")
'''
)

code(
    '''
q("""
    SELECT event_date dia, event_key evento, team_home mandante,
           team_away visitante, competition competicao,
           to_timestamp(min(start_ts)/1000) inicio,
           round((max(end_ts) - min(start_ts))/60000.0, 1) duracao_min
    FROM live_event GROUP BY 1, 2, 3, 4, 5 ORDER BY inicio
""")
'''
)

# =========================================================================== #
# 5. Incidentes
# =========================================================================== #

md(
    """
---
# 5. Incidentes e rótulos

Duas fontes descrevem "o que deu errado" com semânticas diferentes.
`incidents` / `incidents_platform` são chamados do ITSM — o registro
**burocrático**, aberto por gente, com prioridade e grupo responsável.
`incident_label` é o registro **analítico**: janelas rotuladas com veredito e
narrativa, usadas para treinar e avaliar um detector. É esta segunda tabela que
define o alvo de qualquer modelo de causa provável.
"""
)

md("## 5.1. Volumetria e sobreposição das duas bases de chamados")

code(
    '''
print(q("""
    SELECT 'incidents' AS tabela, count(*) chamados,
           count(DISTINCT sys_id) ids, count(DISTINCT assignment_group) grupos,
           to_timestamp(min(opened_at)/1000) primeiro,
           to_timestamp(max(opened_at)/1000) ultimo
    FROM incidents
    UNION ALL
    SELECT 'incidents_platform', count(*), count(DISTINCT sys_id),
           count(DISTINCT assignment_group),
           to_timestamp(min(opened_at)/1000), to_timestamp(max(opened_at)/1000)
    FROM incidents_platform
""").to_string(index=False))

print()
print(q("""
    SELECT count(*) FILTER (WHERE p.sys_id IS NULL)  AS so_em_incidents,
           count(*) FILTER (WHERE i.sys_id IS NULL)  AS so_em_platform,
           count(*) FILTER (WHERE i.sys_id IS NOT NULL
                              AND p.sys_id IS NOT NULL) AS em_ambas
    FROM (SELECT DISTINCT sys_id FROM incidents) i
    FULL OUTER JOIN (SELECT DISTINCT sys_id FROM incidents_platform) p
      USING (sys_id)
""").to_string(index=False))
'''
)

md(
    """
`incidents_platform` é majoritariamente um **subconjunto** de `incidents` — o
recorte dos chamados atribuídos à plataforma. Somar as duas tabelas contaria os
mesmos chamados duas vezes; as análises abaixo usam `incidents` como base e
tratam `incidents_platform` como filtro.
"""
)

md("## 5.2. Prioridade, estado e tempo de resolução")

code(
    '''
d = q("""
    SELECT priority prioridade, count(*) chamados,
           count(*) FILTER (WHERE resolved_at IS NOT NULL) resolvidos,
           median((resolved_at - opened_at)/60000.0) mttr_mediano_min,
           quantile_cont((resolved_at - opened_at)/60000.0, 0.9) mttr_p90_min,
           max((resolved_at - opened_at)/60000.0) mttr_max_min
    FROM incidents WHERE priority IS NOT NULL
    GROUP BY 1 ORDER BY 1
""")
d
'''
)

code(
    '''
f, (a1, a2) = plt.subplots(1, 2, figsize=(11.0, 3.8))
barras_h(a1, d.prioridade, d.chamados.values, color=CAT[0])
titulo(a1, "Chamados por prioridade", "volume no período")

# MTTR: prioridade é ordinal, logo escala sequencial de um tom só.
cor = [SEQ[7 - min(i, 5)] for i in range(len(d))]
barras_h(a2, d.prioridade, d.mttr_mediano_min.values, color=CAT[0],
         fmt="{:,.0f} min")
titulo(a2, "Tempo mediano até a resolução",
       "minutos entre abertura e resolução do chamado")
plt.tight_layout()
plt.show()
'''
)

md(
    """
A pirâmide de prioridade é fortemente concentrada na base (P4/P5), mas o tempo
de resolução **cresce** conforme a prioridade cai — o comportamento esperado de
uma fila que prioriza o crítico. O ponto relevante para o projeto está no
contraste de ordens de grandeza: o P1 resolve em minutos, o P5 leva quase um
dia. Um chamado de baixa prioridade que na verdade é o sintoma de uma
degradação ampla fica parado nessa fila — exatamente o custo que a correlação
automática pretende atacar.
"""
)

code(
    '''
d = q("""
    SELECT state estado, count(*) n FROM incidents
    WHERE state IS NOT NULL GROUP BY 1 ORDER BY n DESC
""")
g = q("""
    SELECT assignment_group grupo, count(*) chamados,
           median((resolved_at - opened_at)/60000.0) mttr_min
    FROM incidents WHERE assignment_group IS NOT NULL
    GROUP BY 1 ORDER BY chamados DESC LIMIT 12
""")
f, (a1, a2) = plt.subplots(1, 2, figsize=(11.0, 4.4))
barras_h(a1, [e[:34] for e in d.estado], d.n.values, color=CAT[0])
titulo(a1, "Estado dos chamados", "situação no momento do dump")
barras_h(a2, [x[:38] for x in g.grupo], g.chamados.values, color=CAT[2])
titulo(a2, "Grupos com mais chamados", "12 maiores filas")
plt.tight_layout()
plt.show()
g
'''
)

code(
    '''
# Distribuição do tempo de resolução. Histograma em escala log, porque o MTTR
# se espalha por várias ordens de grandeza.
h = q("""
    SELECT (resolved_at - opened_at)/60000.0 AS minutos FROM incidents
    WHERE resolved_at IS NOT NULL AND resolved_at > opened_at
""").minutos.values
f, ax = fig(9.5, 3.4)
bins = np.logspace(np.log10(max(h.min(), 0.1)), np.log10(h.max()), 44)
ax.hist(h, bins=bins, color=CAT[0], edgecolor=SURFACE, linewidth=0.6)
ax.set_xscale("log")
ax.set_xlabel("tempo até a resolução (minutos, escala log)")
ax.set_ylabel("chamados")
for v, lab, cor in [(np.median(h), "mediana", CAT[1]),
                    (np.percentile(h, 90), "p90", CAT[7])]:
    ax.axvline(v, color=cor, lw=1.4, ls=(0, (4, 3)))
    ax.text(v, ax.get_ylim()[1] * 0.94, f" {lab}: {v:,.0f} min",
            fontsize=8, color=cor)
titulo(ax, "Distribuição do tempo de resolução",
       f"{len(h):,} chamados resolvidos")
plt.tight_layout()
plt.show()
'''
)

code(
    '''
# Campos de causa raiz: quanto do acervo é aproveitável para treinar correlação?
q("""
    SELECT
      count(*) chamados,
      100.0*count(short_description)/count(*) pct_com_descricao,
      100.0*count(cause)/count(*) pct_com_causa,
      100.0*count(u_what_s_the_root_cause)/count(*) pct_com_causa_raiz,
      100.0*count(close_notes)/count(*) pct_com_notas,
      100.0*count(category)/count(*) pct_com_categoria,
      100.0*count(business_service)/count(*) pct_com_servico,
      100.0*count(*) FILTER (
        WHERE u_this_incident_was_caused_by_a_change_or_deploy = 'true'
      )/count(*) pct_causado_por_deploy
    FROM incidents
""")
'''
)

md("## 5.3. Rótulos analíticos: `incident_label`")

code(
    '''
q("""
    SELECT id, tier, kind AS tipo, severity AS severidade, verdict AS veredito,
           provenance AS procedencia,
           to_timestamp(ts_start/1000) inicio,
           round((ts_end - ts_start)/3600000.0, 2) duracao_h,
           services AS servicos
    FROM incident_label ORDER BY ts_start
""")
'''
)

code(
    '''
f, axes = plt.subplots(1, 3, figsize=(11.0, 3.2))
for ax, col, tit in [(axes[0], "provenance", "Procedência"),
                     (axes[1], "tier", "Tier"),
                     (axes[2], "kind", "Tipo")]:
    d = q(f"SELECT {col} k, count(*) n FROM incident_label GROUP BY 1 ORDER BY n DESC")
    barras_h(ax, [str(x)[:24] for x in d.k], d.n.values, color=CAT[0])
    titulo(ax, tit)
plt.tight_layout()
plt.show()

print("serviços citados nos rótulos:")
q("""
    SELECT servico, count(*) rotulos FROM (
        SELECT trim(unnest(str_split(
                   replace(replace(replace(services, '[', ''), ']', ''), '"', ''),
                   ','))) AS servico
        FROM incident_label
    ) WHERE servico <> '' GROUP BY 1 ORDER BY rotulos DESC
""")
'''
)

md(
    """
São **20 rótulos** — um acervo pequeno para treinar um classificador
supervisionado, mas suficiente como conjunto de avaliação de um detector. A
mistura de procedências é o dado mais informativo: rótulos `detector-derived`
foram gerados automaticamente e ainda não têm veredito humano, enquanto
`team-confirmed` e `rca-confirmed` carregam validação. Só estes últimos servem
como verdade de referência.

Vale notar que três rótulos são `load_test`: janelas de teste de carga que um
detector ingênuo classificaria como incidente. Elas são o contraexemplo mais
valioso do acervo, porque delimitam o que **não** deve gerar alerta.
"""
)

code(
    '''
# Linha do tempo dos rótulos, para ver como se distribuem no período coberto.
d = q("""
    SELECT id, to_timestamp(ts_start/1000) ini,
           to_timestamp(coalesce(ts_end, ts_start + 3600000)/1000) fim,
           provenance, kind
    FROM incident_label ORDER BY ts_start
""")
# janela em que existe telemetria de alta resolução, para contraste
tel = q("""
    SELECT to_timestamp(min(epoch_ms)/1000) a, to_timestamp(max(epoch_ms)/1000) b
    FROM prom_point
""").iloc[0]

cores_prov = {p: CAT[i] for i, p in enumerate(sorted(d.provenance.unique()))}
f, ax = fig(9.5, 5.4)
y = np.arange(len(d))
ini = mpl.dates.date2num(d.ini)
fim = mpl.dates.date2num(d.fim)
ax.axvspan(mpl.dates.date2num(tel.a), mpl.dates.date2num(tel.b),
           color=CAT[0], alpha=0.10, lw=0, zorder=0)
ax.axvline(mpl.dates.date2num(tel.a), color=CAT[0], lw=1.2, ls=(0, (4, 3)),
           zorder=1)
ax.barh(y, np.maximum(fim - ini, 0.35), left=ini, height=0.6, zorder=2,
        color=[cores_prov[p] for p in d.provenance])
ax.set_yticks(y, [i[:42] for i in d.id])
ax.invert_yaxis()
ax.xaxis_date()
sem_grade(ax)
ax.grid(True, axis="x")
ax.spines["left"].set_visible(False)
ax.annotate("telemetria de alta\\nresolução disponível",
            xy=(mpl.dates.date2num(tel.a), 0.8),
            xytext=(8, 0), textcoords="offset points",
            fontsize=8, color=CAT[0], va="center")
handles = [mpl.patches.Patch(color=c, label=k) for k, c in cores_prov.items()]
ax.legend(handles=handles, ncol=4, loc="lower right", bbox_to_anchor=(1, -0.14))
titulo(ax, "Rótulos de incidente contra a janela de telemetria",
       "largura da barra = duração da janela rotulada; faixa azul = período com prom_point")
plt.tight_layout()
plt.show()
'''
)

md(
    """
Os rótulos cobrem de março a julho de 2026, mas a telemetria de alta resolução
(`prom_point`, `signal_point`) começa apenas em 12 de julho. **A maior parte dos
rótulos não tem telemetria correspondente no dump.** Isso restringe severamente
o que se pode validar: a seção 7 quantifica quantos rótulos sobrevivem ao
recorte.
"""
)

# =========================================================================== #
# 6. Coleta
# =========================================================================== #

md(
    """
---
# 6. Operação da coleta

As tabelas `*_run` são o log do próprio Argus: quanto tempo cada coletor levou,
quantas linhas trouxe e quanto custou. Elas respondem uma pergunta que o caso de
negócio levanta explicitamente — o custo de propriedade de uma plataforma
própria — com número em vez de estimativa.
"""
)

code(
    '''
d = q("""
    SELECT source fonte, count(*) execucoes,
           sum(rows_upserted) linhas, sum(cost_usd) custo_usd,
           median(duration_s) duracao_mediana_s,
           quantile_cont(duration_s, 0.95) duracao_p95_s,
           sum(bytes_scanned)/1e9 gb_varridos,
           to_timestamp(min(started_at)/1000) primeira,
           to_timestamp(max(started_at)/1000) ultima
    FROM collector_run GROUP BY 1 ORDER BY custo_usd DESC
""")
print(f"{d.execucoes.sum():,} execuções | US$ {d.custo_usd.sum():,.2f} no período | "
      f"{d.gb_varridos.sum():,.1f} GB varridos")
d
'''
)

code(
    '''
f, (a1, a2) = plt.subplots(1, 2, figsize=(11.0, 4.8))
top = d.nlargest(14, "custo_usd")
barras_h(a1, top.fonte, top.custo_usd.values, color=CAT[1], fmt="US$ {:,.2f}")
titulo(a1, "Custo por fonte", "soma de cost_usd no período")
top2 = d.nlargest(14, "execucoes")
barras_h(a2, top2.fonte, top2.execucoes.values, color=CAT[0])
titulo(a2, "Execuções por fonte", "número de rodadas do coletor")
plt.tight_layout()
plt.show()
'''
)

md(
    """
O custo se concentra nas fontes `llm_*` — as etapas de investigação, crítica e
narrativa que usam modelo de linguagem — e não na ingestão de telemetria. É um
dado relevante para o dimensionamento da solução proposta: o gargalo econômico
da camada agêntica não é armazenar métrica, é **raciocinar sobre ela**. Qualquer
requisito não funcional de custo precisa mirar a frequência de invocação do
agente, não o volume de ingestão.
"""
)

code(
    '''
# Custo acumulado ao longo do tempo, separando as etapas de LLM das demais.
d = q("""
    SELECT to_timestamp(started_at/1000) t,
           CASE WHEN source LIKE 'llm%' THEN 'camada agêntica (LLM)'
                ELSE 'ingestão de telemetria' END AS classe,
           cost_usd
    FROM collector_run WHERE cost_usd IS NOT NULL ORDER BY 1
""")
f, ax = fig(9.5, 3.6)
for i, (k, g) in enumerate(d.groupby("classe")):
    ax.plot(g.t, g.cost_usd.cumsum(), color=CAT[i], lw=2, label=k)
    ax.annotate(f"US$ {g.cost_usd.sum():,.2f}",
                (g.t.iloc[-1], g.cost_usd.cumsum().iloc[-1]),
                xytext=(6, -3), textcoords="offset points",
                fontsize=8.5, color=CAT[i])
ax.legend(ncol=2, loc="upper left")
ax.set_ylabel("custo acumulado (US$)")
titulo(ax, "Custo acumulado da coleta",
       "a camada de raciocínio custa mais que a de ingestão")
plt.tight_layout()
plt.show()
'''
)

code(
    '''
# Saúde dos coletores especializados.
for t, nome in [("prom_run", "Prometheus"), ("nr_run", "New Relic"),
                ("apollo_run", "Apollo"), ("ca_run", "Cloud Armor"),
                ("rpaas_run", "RPaaS")]:
    cols = set(q(f"SELECT * FROM {t} LIMIT 0").columns)
    extra = []
    if "queries_ok" in cols:
        extra.append("sum(queries_err) erros_query")
    if "points_inserted" in cols:
        extra.append("sum(points_inserted) pontos")
    if "rows_inserted" in cols:
        extra.append("sum(rows_inserted) linhas")
    if "rows_seen" in cols:
        extra.append("sum(rows_seen) linhas_vistas")
    if "buckets_upd" in cols:
        extra.append("sum(buckets_upd) buckets")
    sel = ", ".join(["count(*) execucoes", "median(duration_s) dur_mediana_s",
                     "max(duration_s) dur_max_s"] + extra)
    print(f"--- {nome} ({t})")
    print(q(f"SELECT {sel} FROM {t}").to_string(index=False))
    print()
'''
)

code(
    '''
# Frescor da ingestão por fonte, e quanto do histórico veio no dump.
ref = q("SELECT max(last_ingested_ts) m FROM signal_meta").m.iloc[0]
d = q(f"""
    SELECT source fonte, rows_total linhas_historico,
           to_timestamp(last_ingested_ts/1000) ultimo_dado,
           ({ref} - last_ingested_ts)/60000.0 atraso_min,
           rows_last_run linhas_ultima_rodada
    FROM signal_meta ORDER BY linhas_historico DESC
""")
d
'''
)

code(
    '''
# O dump é uma janela do histórico, não a base inteira. Quanto ele representa?
d = q("""
    SELECT m.source fonte, m.rows_total historico,
           count(s.ts) no_dump,
           100.0 * count(s.ts) / nullif(m.rows_total, 0) pct
    FROM signal_meta m LEFT JOIN signal_point s ON s.source = m.source
    GROUP BY 1, 2 ORDER BY historico DESC
""")
g = d.sort_values("pct", ascending=False)
f, ax = fig(9.5, 4.4)
barras_h(ax, g.fonte, g.pct.values, color=CAT[0], fmt="{:.1f}%")
titulo(ax, "Fração do histórico presente no dump",
       "linhas em signal_point sobre rows_total declarado em signal_meta")
plt.tight_layout()
plt.show()
d
'''
)

md(
    """
O dump é um **recorte**, não a base completa. O Prometheus declara 1,87 bilhão
de linhas no histórico e entrega menos de 0,2% delas aqui. Isso não invalida a
análise — a janela é contínua e recente —, mas impede qualquer afirmação sobre
sazonalidade longa, e significa que os volumes desta análise **não** devem ser
usados para dimensionar a plataforma de produção.
"""
)

# =========================================================================== #
# 7. Analise cruzada
# =========================================================================== #

md(
    """
---
# 7. Análise cruzada entre camadas

Até aqui cada fonte foi lida isoladamente — que é exatamente o problema que o
projeto quer resolver. Esta seção faz o oposto: coloca infraestrutura, QoE,
mudanças e incidentes na **mesma linha do tempo** e pergunta se um lado explica
o outro. É o teste de viabilidade da premissa central da solução proposta.
"""
)

md("## 7.1. A janela realmente comum")

code(
    '''
CHAVE = {
    "prom_point": "epoch_ms", "signal_point": "ts", "signal_bucket": "bts",
    "rpaas_bucket": "bucket_ts_ms", "ca_point": "ts_ms",
    "service_overview": "timestamp", "operation_metrics": "start_ts",
    "live_qoe_hourly": "hour_ts", "live_active_15min": "bucket_ts",
    "player_hourly": "hour_ts", "device_hourly": "hour_ts",
    "geo_hourly": "hour_ts", "error_cat_hourly": "hour_ts",
    "live_error_attr_hourly": "hour_ts", "tsuru_event": "start_time_ms",
    "incidents": "opened_at", "incident_label": "ts_start",
}
lim = q(" UNION ALL ".join(
    f"SELECT '{t}' tabela, min({c}) a, max({c}) b FROM {t}"
    for t, c in CHAVE.items() if t in TABLES))
lim["inicio"] = pd.to_datetime(lim.a, unit="ms", utc=True)
lim["fim"] = pd.to_datetime(lim.b, unit="ms", utc=True)

# a interseção é ditada pelas fontes de telemetria e QoE, não pelos incidentes
nucleo = ["prom_point", "signal_point", "rpaas_bucket", "service_overview",
          "live_qoe_hourly", "live_active_15min", "player_hourly"]
sub = lim[lim.tabela.isin(nucleo)]
T0, T1 = sub.inicio.max(), sub.fim.min()
print(f"janela comum às camadas de telemetria e QoE:")
print(f"  {T0:%Y-%m-%d %H:%M} → {T1:%Y-%m-%d %H:%M} UTC "
      f"({(T1 - T0).days} dias, {(T1 - T0).total_seconds() / 3600:.0f} h)")
MS0, MS1 = int(T0.timestamp() * 1000), int(T1.timestamp() * 1000)

lim[["tabela", "inicio", "fim"]].sort_values("inicio").reset_index(drop=True)
'''
)

code(
    '''
# Quanto do acervo semântico sobrevive a esse recorte?
print(q(f"""
    SELECT 'rótulos (incident_label)' AS acervo,
           count(*) total,
           count(*) FILTER (WHERE ts_start BETWEEN {MS0} AND {MS1}) na_janela
    FROM incident_label
    UNION ALL
    SELECT 'chamados (incidents)', count(*),
           count(*) FILTER (WHERE opened_at BETWEEN {MS0} AND {MS1})
    FROM incidents
    UNION ALL
    SELECT 'eventos ao vivo (live_event)', count(*),
           count(*) FILTER (WHERE start_ts BETWEEN {MS0} AND {MS1})
    FROM live_event
    UNION ALL
    SELECT 'mudanças (tsuru_event)', count(*),
           count(*) FILTER (WHERE start_time_ms BETWEEN {MS0} AND {MS1})
    FROM tsuru_event
""").to_string(index=False))
'''
)

md(
    """
Este é o resultado mais importante da seção. O acervo rotulado, que seria a
verdade de referência para avaliar um detector, **quase não sobrevive** ao
recorte: a telemetria de alta resolução e os rótulos de incidente mal se
encontram no tempo. Um modelo supervisionado treinado neste dump teria pouquíssimos
exemplos positivos com sinal correspondente. O caminho viável com estes dados é
**detecção não supervisionada** (desvio de linha de base), usando os poucos
rótulos que sobrevivem apenas como verificação qualitativa.
"""
)

md("## 7.2. A infraestrutura explica a experiência?")

code(
    '''
# Todas as camadas reamostradas para a grade horária, que é a mais grossa.
painel = q(f"""
    WITH qoe AS (
        SELECT hour_ts h, sum(sessions) sessoes, sum(errors) erros,
               100.0*sum(errors)/nullif(sum(sessions),0) qoe_erro_pct,
               avg(bufferratio_avg) buffer, avg(jointime_s_avg) jointime,
               avg(latency_ms_avg) latencia
        FROM live_qoe_hourly GROUP BY 1
    ),
    borda AS (
        SELECT (bucket_ts_ms // 3600000) * 3600000 h,
               sum(requests_total) req,
               100.0*sum(requests_5xx)/nullif(sum(requests_total),0) borda_5xx_pct,
               100.0*sum(requests_4xx)/nullif(sum(requests_total),0) borda_4xx_pct
        FROM rpaas_bucket GROUP BY 1
    ),
    apm AS (
        SELECT (timestamp // 3600000) * 3600000 h,
               avg(error_rate_pct) apm_erro_pct, avg(apdex_score) apdex,
               avg(response_time_avg_ms) apm_tempo
        FROM service_overview GROUP BY 1
    ),
    gql AS (
        SELECT (start_ts // 3600000) * 3600000 h,
               100.0*sum(error_count)/nullif(sum(request_count),0) gql_erro_pct,
               avg(p99_ms) gql_p99
        FROM operation_metrics GROUP BY 1
    )
    SELECT to_timestamp(qoe.h/1000) t, qoe.* EXCLUDE (h),
           borda.* EXCLUDE (h), apm.* EXCLUDE (h), gql.* EXCLUDE (h)
    FROM qoe
    LEFT JOIN borda USING (h) LEFT JOIN apm USING (h) LEFT JOIN gql USING (h)
    WHERE qoe.h BETWEEN {MS0} AND {MS1}
    ORDER BY t
""")
print(f"{len(painel)} horas na janela comum")
painel.head()
'''
)

code(
    '''
cols = ["qoe_erro_pct", "buffer", "jointime", "latencia", "sessoes",
        "borda_5xx_pct", "borda_4xx_pct", "req",
        "apm_erro_pct", "apdex", "apm_tempo", "gql_erro_pct", "gql_p99"]
rot = ["QoE erro %", "buffer ratio", "join time", "latência", "sessões",
       "borda 5xx %", "borda 4xx %", "requisições",
       "APM erro %", "Apdex", "APM tempo", "GraphQL erro %", "GraphQL p99"]
corr = painel[cols].corr(method="spearman")

f, ax = fig(8.4, 6.8)
im = ax.imshow(corr.values, cmap=DIV_CMAP, vmin=-1, vmax=1)
ax.set_xticks(range(len(rot)), rot, rotation=40, ha="right")
ax.set_yticks(range(len(rot)), rot)
sem_grade(ax)
for s in ax.spines.values():
    s.set_visible(False)
for i in range(len(rot)):
    for j in range(len(rot)):
        v = corr.values[i, j]
        if not np.isnan(v):
            ax.text(j, i, f"{v:.2f}", ha="center", va="center", fontsize=6.8,
                    color="#ffffff" if abs(v) > 0.55 else INK)
# separa visualmente o bloco de QoE do bloco de infraestrutura
ax.axhline(4.5, color=INK, lw=1.2)
ax.axvline(4.5, color=INK, lw=1.2)
cb = f.colorbar(im, ax=ax, fraction=0.042, pad=0.03)
cb.outline.set_visible(False)
cb.set_label("correlação de Spearman", color=INK2, fontsize=8.5)
titulo(ax, "QoE × infraestrutura, na grade horária",
       "linha preta separa métricas de experiência (acima) das de infra")
plt.tight_layout()
plt.show()
'''
)

code(
    '''
# Ranking explícito: o que mais se associa ao erro percebido pelo assinante?
alvo = "qoe_erro_pct"
infra = ["borda_5xx_pct", "borda_4xx_pct", "req",
         "apm_erro_pct", "apdex", "apm_tempo", "gql_erro_pct", "gql_p99"]
r = (painel[infra + [alvo]].corr(method="spearman")[alvo]
     .drop(alvo).sort_values(key=abs, ascending=False))
nomes = dict(zip(infra, ["borda 5xx %", "borda 4xx %", "requisições",
                         "APM erro %", "Apdex", "APM tempo",
                         "GraphQL erro %", "GraphQL p99"]))

f, ax = fig(9.0, 3.8)
y = np.arange(len(r))
ax.barh(y, r.values, height=0.6,
        color=[CAT[0] if v > 0 else CAT[7] for v in r.values])
ax.set_yticks(y, [nomes[i] for i in r.index])
ax.invert_yaxis()
ax.axvline(0, color=INK, lw=1)
sem_grade(ax)
ax.grid(True, axis="x")
ax.set_axisbelow(True)
ax.spines["left"].set_visible(False)
for yi, v in zip(y, r.values):
    ax.text(v + (0.02 if v > 0 else -0.02), yi, f"{v:+.2f}", va="center",
            ha="left" if v > 0 else "right", fontsize=8, color=INK2)
lim_x = max(abs(r.values)) * 1.35
ax.set_xlim(-lim_x, lim_x)
ax.set_xlabel("correlação de Spearman com a taxa de erro de QoE")
titulo(ax, "O que acompanha o erro percebido pelo assinante",
       "azul: sobe junto · vermelho: move em direção oposta")
plt.tight_layout()
plt.show()
'''
)

md(
    """
As associações entre a infraestrutura e o erro percebido são **fracas** na grade
horária. Isso não é um defeito da análise — é a confirmação empírica da tese do
projeto. Se a taxa de 5xx da borda explicasse o erro do player, bastaria um
alarme de limiar na borda e não haveria problema a resolver. O que os dados
mostram é que a experiência degrada por caminhos que a métrica agregada de
infraestrutura não captura, e que **a média horária nacional dilui o recorte
onde a falha realmente acontece**.

Duas implicações práticas: (1) a correlação precisa ser feita por recorte, não
no agregado; (2) a janela de uma hora é grossa demais — um incidente de vinte
minutos desaparece nela.
"""
)

md("## 7.3. Mudanças na plataforma versus incidentes")

md(
    """
A hipótese "o incidente foi causado por uma mudança" é a mais comum na triagem.
Ela é testável: basta ver se um chamado tende a ser precedido por um deploy.
Mas uma proporção alta só significa alguma coisa se for **maior que a de um
instante qualquer** — por isso a comparação abaixo inclui um grupo de controle
com instantes sorteados na mesma janela.
"""
)

code(
    '''
d = q("""
    WITH janela AS (
        SELECT greatest(min_i, min_e) a, least(max_i, max_e) b FROM (
            SELECT min(opened_at) min_i, max(opened_at) max_i,
                   (SELECT min(start_time_ms) FROM tsuru_event) min_e,
                   (SELECT max(start_time_ms) FROM tsuru_event) max_e
            FROM incidents)
    ),
    reais AS (
        SELECT opened_at t FROM incidents, janela
        WHERE opened_at BETWEEN a AND b
    ),
    controle AS (
        SELECT a + (random() * (b - a))::bigint t FROM janela, range(20000)
    )
    SELECT 'chamados reais' grupo, count(*) n,
           100.0 * count(*) FILTER (WHERE EXISTS (
               SELECT 1 FROM tsuru_event e
               WHERE e.start_time_ms BETWEEN r.t - 6*3600000 AND r.t)) / count(*) pct
    FROM reais r
    UNION ALL
    SELECT 'instantes sorteados (controle)', count(*),
           100.0 * count(*) FILTER (WHERE EXISTS (
               SELECT 1 FROM tsuru_event e
               WHERE e.start_time_ms BETWEEN c.t - 6*3600000 AND c.t)) / count(*)
    FROM controle c
""")
print("chamados precedidos por alguma mudança em até 6 h:")
print(d.to_string(index=False))
lift = d.pct.iloc[0] - d.pct.iloc[1]
print(f"\\ndiferença sobre o controle: {lift:+.1f} pontos percentuais")

print()
print("declaração explícita no próprio chamado:")
print(q("""
    SELECT u_this_incident_was_caused_by_a_change_or_deploy AS causado_por_deploy,
           count(*) chamados
    FROM incidents GROUP BY 1 ORDER BY chamados DESC
""").to_string(index=False))
'''
)

md(
    """
> **A proximidade temporal com um deploy não é evidência de causa neste
> dataset.** Chamados reais e instantes sorteados ao acaso têm praticamente a
> mesma chance de serem precedidos por uma mudança em 6 horas — a diferença é de
> poucos pontos percentuais. O motivo é a densidade: as mudanças são tão
> frequentes (e concentradas em rajadas) que quase qualquer instante tem uma
> perto.
>
> Sem esse controle, a estatística de "9 em cada 10 incidentes vieram depois de
> um deploy" pareceria um achado forte, e seria falsa. Um mecanismo de atribuição
> de causa que use proximidade temporal como sinal vai gerar falso positivo em
> massa; é preciso exigir coincidência de **serviço afetado**, não só de tempo.
>
> Note também que o campo declarativo do ITSM confirma a mesma direção por outro
> caminho: apenas 3 dos 501 chamados marcam explicitamente terem sido causados
> por mudança ou deploy.
"""
)

code(
    '''
# Sobreposição temporal das duas séries no período comum.
mud = q(f"""
    SELECT date_trunc('day', to_timestamp(start_time_ms/1000)) d, count(*) n
    FROM tsuru_event WHERE start_time_ms BETWEEN {MS0} AND {MS1}
    GROUP BY 1 ORDER BY 1
""")
inc = q(f"""
    SELECT date_trunc('day', to_timestamp(opened_at/1000)) d, count(*) n
    FROM incidents WHERE opened_at BETWEEN {MS0} AND {MS1}
    GROUP BY 1 ORDER BY 1
""")
f, (a1, a2) = plt.subplots(2, 1, figsize=(9.5, 4.6), sharex=True)
a1.bar(mud.d, mud.n, color=CAT[0], width=0.75)
a1.set_ylabel("mudanças")
a2.bar(inc.d, inc.n, color=CAT[1], width=0.75)
a2.set_ylabel("chamados abertos")
titulo(a1, "Mudanças na plataforma e chamados abertos, por dia",
       "mesma janela temporal nos dois painéis")
plt.tight_layout()
plt.show()
'''
)

md("## 7.4. Eventos ao vivo e carga")

code(
    '''
ev = q("""
    SELECT DISTINCT event_key, team_home, team_away, competition,
           min(start_ts) OVER (PARTITION BY event_key) ini,
           max(end_ts)   OVER (PARTITION BY event_key) fim
    FROM live_event ORDER BY ini
""")
s = q("""
    SELECT to_timestamp(bucket_ts/1000) t, sum(active_sessions) ativas,
           100.0*sum(active_with_error)/nullif(sum(active_sessions),0) pct_erro
    FROM live_active_15min GROUP BY 1 ORDER BY 1
""")

f, (a1, a2) = plt.subplots(2, 1, figsize=(9.5, 5.8), sharex=True)
for _, e in ev.iterrows():
    for ax in (a1, a2):
        ax.axvspan(pd.to_datetime(e.ini, unit="ms", utc=True),
                   pd.to_datetime(e.fim, unit="ms", utc=True),
                   color=CAT[3], alpha=0.28, lw=0, zorder=0)
a1.plot(s.t, s.ativas, color=CAT[0], lw=1.4, zorder=2)
a2.plot(s.t, s.pct_erro, color=CAT[7], lw=1.4, zorder=2)
a1.set_ylabel("sessões ativas")
a2.set_ylabel("% com erro")
# o eixo acompanha a janela da telemetria de QoE: eventos fora dela não têm
# série para comparar e só esticariam o gráfico
a1.set_xlim(s.t.min(), s.t.max())
n_dentro = ((ev.ini <= s.t.max().timestamp() * 1000)
            & (ev.fim >= s.t.min().timestamp() * 1000)).sum()
a1.legend(handles=[mpl.patches.Patch(color=CAT[3], alpha=0.5,
                                     label="evento ao vivo programado")],
          loc="upper left")
titulo(a1, "Audiência e erro durante eventos ao vivo programados",
       f"{n_dentro} dos {len(ev)} eventos de live_event caem na janela com telemetria de QoE")
plt.tight_layout()
plt.show()
'''
)

code(
    '''
# Dentro versus fora de evento — o pico de audiência vem acompanhado de erro?
janelas = " OR ".join(
    f"(bucket_ts BETWEEN {int(e.ini)} AND {int(e.fim)})" for _, e in ev.iterrows())
d = q(f"""
    SELECT CASE WHEN {janelas} THEN 'durante evento'
                ELSE 'fora de evento' END AS periodo,
           count(*) buckets,
           avg(active_sessions) sessoes_medias,
           max(active_sessions) sessoes_pico,
           100.0*sum(active_with_error)/nullif(sum(active_sessions),0) pct_erro,
           avg(jointime_s_avg) jointime_s, avg(bufferratio_avg) buffer,
           avg(latency_ms_p95) latencia_p95
    FROM live_active_15min GROUP BY 1
""")
d
'''
)

md("## 7.5. As janelas rotuladas se distinguem da linha de base?")

code(
    '''
# Para cada rótulo com telemetria disponível, compara a janela rotulada com a
# linha de base das 24 h anteriores.
rot = q(f"""
    SELECT id, ts_start, coalesce(ts_end, ts_start + 3600000) ts_end, provenance
    FROM incident_label
    WHERE ts_start BETWEEN {MS0} AND {MS1}
       OR coalesce(ts_end, ts_start) BETWEEN {MS0} AND {MS1}
    ORDER BY ts_start
""")
print(f"{len(rot)} de {q('SELECT count(*) n FROM incident_label').n.iloc[0]} "
      f"rótulos caem na janela com telemetria")

linhas = []
for r in rot.itertuples():
    base = q(f"""
        SELECT avg(error_rate_pct) erro, avg(apdex_score) apdex
        FROM service_overview
        WHERE timestamp BETWEEN {r.ts_start - 86400000} AND {r.ts_start}
    """).iloc[0]
    dentro = q(f"""
        SELECT avg(error_rate_pct) erro, avg(apdex_score) apdex
        FROM service_overview
        WHERE timestamp BETWEEN {r.ts_start} AND {r.ts_end}
    """).iloc[0]
    linhas.append({"rotulo": r.id, "procedencia": r.provenance,
                   "erro_base_pct": base.erro, "erro_janela_pct": dentro.erro,
                   "apdex_base": base.apdex, "apdex_janela": dentro.apdex})

if linhas:
    cmp = pd.DataFrame(linhas)
    cmp["delta_erro"] = cmp.erro_janela_pct - cmp.erro_base_pct
    display(cmp)
else:
    print("nenhum rótulo coincide com a janela de telemetria do APM — "
          "a comparação com linha de base não é possível neste dump")
'''
)

# =========================================================================== #
# 8. Sintese
# =========================================================================== #

md(
    """
---
# 8. Síntese

## 8.1. O que o dataset é

Uma janela contínua e recente da telemetria de produção do Globoplay, com quatro
camadas convergindo na mesma base: infraestrutura, experiência do assinante,
incidentes e o log da própria coleta. São 68,7 milhões de linhas em 33 tabelas,
sem duplicata de chave primária, sem violação de integridade referencial e com
alta continuidade nas grades temporais. **A qualidade técnica do dump é alta** —
os problemas encontrados são de *escopo*, não de *corrupção*.

## 8.2. Achados que mudam o desenho da solução

**1. O cruzamento UF × operadora não existe.** As duas dimensões de
`geo_hourly` são mutuamente exclusivas: nenhuma linha tem as duas preenchidas. O
caso de negócio sustenta que o diferencial da solução está em enxergar a
combinação de plataforma, modelo, UF e operadora — e essa combinação foi
removida na sanitização. O protótipo demonstra os recortes marginais; o
cruzamento precisa ser negociado com o parceiro ou tratado como requisito
dependente de dado de produção.

**2. Rótulos e telemetria mal se sobrepõem.** Os 20 rótulos de `incident_label`
cobrem março a julho de 2026; a telemetria de alta resolução começa em 12 de
julho. Sobra pouquíssima interseção. Não há base para treinar um classificador
supervisionado de causa provável com este dump. O caminho viável é detecção por
desvio de linha de base, com os rótulos sobreviventes servindo de verificação
qualitativa.

**3. A infraestrutura agregada não explica a experiência.** Na grade horária, as
correlações entre métricas de borda/APM/GraphQL e a taxa de erro de QoE são
fracas. Isso valida a premissa do projeto — se a relação fosse forte, um alarme
de limiar bastaria — e impõe duas exigências ao desenho: correlacionar **por
recorte**, nunca no agregado nacional, e trabalhar em granularidade mais fina
que uma hora.

**4. Uma fatia relevante do erro não tem dono.** Existe um player de
identificador vazio com volume comparável aos maiores players nomeados e taxa de
erro uma ordem de grandeza acima da média. Atribuir essas sessões é
pré-requisito para qualquer ranking de causa confiável.

**5. O custo da solução está no raciocínio, não na ingestão.** Em
`collector_run`, as etapas `llm_*` custam mais que toda a ingestão de
telemetria somada. O requisito não funcional de custo deve mirar a frequência de
invocação da camada agêntica, não o volume de dados.

**6. O dump é um recorte do histórico.** O Prometheus declara 1,87 bilhão de
linhas em `signal_meta` e entrega menos de 0,2% aqui. Os volumes desta análise
não servem para dimensionar a plataforma de produção, e não há base para
afirmações sobre sazonalidade longa.

## 8.3. O que isto habilita no projeto

| Capacidade pretendida | Viável com este dump? |
|---|---|
| Linha do tempo única correlacionando as camadas | **Sim** — a chave temporal é consistente entre fontes |
| Detecção de degradação sem erro (buffer, join time) | **Sim** — `live_qoe_hourly` e `live_active_15min` trazem as métricas |
| Recorte por player, dispositivo, sinal, CDN, UF | **Sim**, isolados |
| Recorte cruzado UF × operadora | **Não** — dimensões mutuamente exclusivas |
| Ranking supervisionado de causa provável | **Não** — rótulos insuficientes na janela com telemetria |
| Ranking não supervisionado por desvio de linha de base | **Sim** |
| Atribuição de incidente a deploy | **Parcialmente** — `tsuru_event` cobre a janela, mas o campo declarativo do ITSM é quase sempre vazio |

## 8.4. Próximos passos sugeridos

1. Levar ao parceiro a questão do cruzamento UF × operadora — é a lacuna de
   maior impacto sobre os requisitos.
2. Pedir uma extração de `incident_label` alinhada à janela de telemetria, ou
   telemetria retroativa que cubra os rótulos existentes.
3. Refazer a análise da seção 7.2 em granularidade de 15 minutos e **por
   recorte** (por sinal, por player), em vez do agregado horário.
4. Investigar a origem das sessões com player vazio.
5. Usar as três janelas `load_test` como conjunto de contraexemplos ao calibrar
   qualquer detector.
"""
)

md(
    """
---

*Notebook gerado por `tools/build_notebook.py` a partir de `data/parquet/`,
produzido por `tools/etl_dump.py` sobre `argus_dump.sql`. Para reproduzir:*

```bash
python tools/etl_dump.py --dump argus_dump.sql --out data/parquet
python tools/build_notebook.py
jupyter nbconvert --execute --inplace notebooks/eda_argus.ipynb
```
"""
)

# <<APPEND>>


# =========================================================================== #
# Montagem
# =========================================================================== #


def build(out: Path) -> None:
    nb = nbf.v4.new_notebook()
    nb.cells = [
        nbf.v4.new_markdown_cell(src) if kind == "md" else nbf.v4.new_code_cell(src)
        for kind, src in CELLS
    ]
    nb.metadata = {
        "kernelspec": {
            "display_name": "Python 3",
            "language": "python",
            "name": "python3",
        },
        "language_info": {"name": "python", "pygments_lexer": "ipython3"},
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    nbf.write(nb, str(out))
    n_md = sum(1 for k, _ in CELLS if k == "md")
    print(f"{out}: {len(CELLS)} celulas ({n_md} markdown, {len(CELLS) - n_md} codigo)")


if __name__ == "__main__":
    build(Path(__file__).resolve().parent.parent / "notebooks" / "eda_argus.ipynb")
