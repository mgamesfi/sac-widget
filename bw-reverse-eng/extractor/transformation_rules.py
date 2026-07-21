"""Extração da lógica de negócio das regras de transformação via RFC — complementar
à extração SQL (`extractor.classic_layer.extract_transformations`, que só traz a
CONTAGEM de regras via `RSTRANSTEPS`, não a lógica em si).

Leia isto antes de configurar: não existe, entre versões do SAP BW, um único BAPI
padronizado e documentado que sirva para "dump estruturado da lógica de uma
transformação" da forma que este reverse-engineering precisa. Duas estratégias são
oferecidas, configuráveis via `config.settings.RfcSettings`, e ambas devem ser
validadas/ajustadas com o time ABAP/BW do cliente antes de uso real:

1. **Função RFC estruturada** (`rules_function_module`): chama uma função
   RFC-enabled que devolva as regras em formato tabular. Pode ser uma função padrão
   do sistema (se o time do cliente confirmar uma disponível) ou, mais comumente na
   prática, uma função Z-customizada que o time ABAP do cliente implementa
   especificamente para este levantamento (é o caminho mais confiável). O nome dos
   parâmetros de entrada/saída também é configurável, pois varia por função.
2. **Fallback: leitura do código-fonte ABAP gerado** (`extract_routine_source`):
   quando a transformação usa rotinas (start/end/field routines), a lógica real
   está no programa ABAP gerado — este módulo lê o código-fonte via
   `RPY_PROGRAM_READ` (função padrão SAP, amplamente disponível). Não estrutura a
   lógica, mas recupera o texto para auditoria/leitura manual mesmo sem BAPI
   estruturado disponível.

Ambas seguem o mesmo padrão de tolerância a falha já usado no resto do app: se a
função RFC não existir ou faltar autorização, a transformação principal não é
afetada — apenas fica sem `regras`/`rotina_fonte`.
"""
from __future__ import annotations

import logging
from typing import Any

from extractor.rfc_connection import RfcCallError, RfcCaller

logger = logging.getLogger("bw_reveng.extractor.transformation_rules")

#: Chaves possíveis para a tabela de saída da função RFC configurada — varia
#: conforme a função (padrão ou Z-customizada) usada em cada cliente.
_TABLE_KEY_CANDIDATES = ("ET_RULES", "REGRAS", "RULES", "T_RULES")


def _first_present(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in row and row[key] not in (None, ""):
            return row[key]
    return None


def extract_transformation_rules(
    rfc: RfcCaller, tranid: str, function_module: str, tranid_param: str = "I_TRANID"
) -> list[dict[str, Any]]:
    """Chama `function_module` para uma transformação e normaliza a tabela de saída
    numa lista de regras. Tolerante a falha (função ausente/sem autorização -> [])."""
    try:
        result = rfc.call(function_module, **{tranid_param: tranid})
    except RfcCallError:
        logger.warning(
            "Função RFC '%s' indisponível para regras de %s — seguindo sem detalhe de regras",
            function_module,
            tranid,
            exc_info=True,
        )
        return []

    table: list[dict[str, Any]] = []
    for key in _TABLE_KEY_CANDIDATES:
        if key in result:
            table = result[key]
            break

    rules = []
    for row in table:
        rules.append(
            {
                "campo_origem": _first_present(row, "SOURCE_FIELD", "SOURCEFIELD", "SOURCE"),
                "campo_destino": _first_present(row, "TARGET_FIELD", "TARGETFIELD", "TARGET"),
                "tipo_regra": _first_present(row, "RULETYPE", "RULE_TYPE"),
                "rotina": _first_present(row, "ROUTINE", "ROUTINE_NAME", "PROGRAM"),
            }
        )
    return rules


def extract_routine_source(rfc: RfcCaller, program_name: str) -> str:
    """Lê o código-fonte ABAP de uma rotina (start/end/field routine) gerada para uma
    transformação, via `RPY_PROGRAM_READ`. Retorna "" se o programa não existir ou
    faltar autorização — mesmo padrão tolerante do resto do app."""
    try:
        result = rfc.call("RPY_PROGRAM_READ", PROGRAM_NAME=program_name)
    except RfcCallError:
        logger.warning("Não foi possível ler o programa '%s' via RPY_PROGRAM_READ", program_name, exc_info=True)
        return ""

    lines = result.get("SOURCE_EXTENDED") or result.get("QCONT") or []
    text_lines = [line.get("LINE", "") if isinstance(line, dict) else str(line) for line in lines]
    return "\n".join(text_lines)


def enrich_transformations_with_rules(
    rfc: RfcCaller,
    transformations: list[dict[str, Any]],
    function_module: str,
    tranid_param: str = "I_TRANID",
    fetch_routine_source: bool = False,
) -> None:
    """Para cada transformação já extraída via SQL, tenta obter a lógica de negócio
    real das regras via RFC e anexa em `REGRAS` (lista) — modifica `transformations`
    in place. Se `fetch_routine_source`, também tenta ler o código-fonte de cada
    rotina referenciada (`ROTINA_FONTE` por regra), quando aplicável.
    """
    for tr in transformations:
        rules = extract_transformation_rules(rfc, tr["TRANID"], function_module, tranid_param)
        if fetch_routine_source:
            for rule in rules:
                program_name = rule.get("rotina")
                if program_name:
                    rule["rotina_fonte"] = extract_routine_source(rfc, program_name)
        tr["REGRAS"] = rules
