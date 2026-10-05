"""Ponte para o leitor de fatos de `tools/` -- a unica costura entre as metades.

O leitor do recorte (`CaseReader`) e o acesso ao banco foram escritos na pasta
`tools/`, que e ambiente de scripts de operacao e nao declara `[build-system]`:
nao da para depender dela como pacote. Enquanto a decisao de onde esse codigo
mora nao for tomada, este modulo resolve o import por caminho, e so ele.

Todo o resto do piloto importa daqui. Quando o leitor virar modulo do pacote,
muda este arquivo e mais nada -- e por isso que a feiura esta concentrada aqui
em vez de espalhada por `ferramentas.py`, `casos.py` e os testes.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

# agente/src/argus_agente/leitor.py -> agente/src/argus_agente -> ... -> fullstack
_FULLSTACK = Path(__file__).resolve().parents[3]
_MODULO = _FULLSTACK / "tools" / "agente_hipoteses_caso.py"


def _carregar() -> Any:
    """Importa `agente_hipoteses_caso` pelo caminho, sem instalar `tools`.

    Returns:
        Any: O modulo carregado.

    Raises:
        ImportError: Se o arquivo nao estiver onde este pacote espera.
    """
    if "argus_agente._leitor_tools" in sys.modules:
        return sys.modules["argus_agente._leitor_tools"]
    if not _MODULO.exists():
        raise ImportError(
            f"leitor de fatos nao encontrado em {_MODULO}; "
            "o piloto depende de tools/agente_hipoteses_caso.py"
        )
    spec = importlib.util.spec_from_file_location("argus_agente._leitor_tools", _MODULO)
    if spec is None or spec.loader is None:
        raise ImportError(f"nao foi possivel carregar {_MODULO}")
    modulo = importlib.util.module_from_spec(spec)
    sys.modules["argus_agente._leitor_tools"] = modulo
    spec.loader.exec_module(modulo)
    return modulo


_tools = _carregar()

# Reexportados com o nome que o piloto usa. `CaseReader` monta a fotografia
# imutavel do checkpoint: ultima versao por `fact_key` ate `input_lsn`, sem
# tombstone, sem fato com `available_at` ou `event_start` depois do `sim_now`.
CaseReader = _tools.CaseReader
MAX_ITENS_POR_RESPOSTA: int = _tools.MAX_ITEMS
MAX_CHAMADAS: int = _tools.MAX_CALLS

__all__ = ["CaseReader", "MAX_CHAMADAS", "MAX_ITENS_POR_RESPOSTA"]
