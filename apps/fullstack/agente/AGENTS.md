# AGENTS.md — piloto de hipóteses com IA

Execução experimental. Um agente de IA investiga os fatos de um checkpoint e
formula hipóteses próprias, para comparação posterior com o motor determinístico
de `../processing`. Leia `README.md` para rodar e
`../../../artefatos/contrato-agente-hipoteses.md` para os contratos.

## Regras deste diretório

1. **O piloto não escreve em lugar nenhum do sistema.** Nada de `INSERT`,
   `UPDATE`, claim de cursor, publicação em API ou gravação em `gold`. A saída é
   arquivo local em `saidas/`, que é gitignored.
2. **O agente nunca vê a resposta do motor atual.** Anomalias, candidatos,
   score, `gold.hypothesis_*`, feedback, `incidents` e `incident_label` ficam
   fora da entrada. Se algum deles entrar, a comparação do Dia 6 perde sentido.
3. **A leitura dos fatos não se reimplementa aqui.** O recorte, o corte
   temporal, a seleção da última versão por `fact_key`, o tombstone e a
   paginação são do leitor em `../tools/agente_hipoteses_caso.py`, importado por
   `leitor.py`. Escrever uma segunda leitura neste pacote já aconteceu uma vez e
   produziu dois contratos incompatíveis para as mesmas três ferramentas.
   `tests/test_ferramentas.py` fixa as garantias de que o ciclo depende; um
   teste que passa a aceitar fato futuro é um defeito, não uma fixture nova.
4. **Teto é código, não instrução de prompt.** Os limites de chamadas, linhas e
   tempo vivem em `limites.py` e são verificados pelo executor. Não substitua
   uma guarda por uma frase no prompt pedindo ao modelo que se contenha.
5. **O modelo descreve, o executor registra.** Histórico de consultas, consumo,
   digest do recorte e identidade do modelo são escritos por código. Nunca
   aceite esses campos vindos da resposta do modelo.
6. **Credencial não entra no repositório.** As chaves `OLLAMA_*` saem do
   `apps/fullstack/.env`, que é gitignored.
7. **Toda saída possível do ciclo vira um `desfecho` gravado.** Ao acrescentar
   um caminho de término, acrescente também o desfecho correspondente em
   `contrato.py` e o rótulo em `registro.py`.

## Antes de entregar

```bash
make -C apps/fullstack test-agente
make -C apps/fullstack agente-ensaio
```

O lint segue o mesmo padrão dos outros apps Python: ruff com `line-length = 90`
e docstring Google em todo módulo, classe e função. Docstrings e comentários
deste diretório são escritos sem acentuação, como no resto do código.
