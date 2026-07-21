"""Normalização: consolida objetos clássicos e next-gen no modelo unificado (RF03)
e resolve as relações fonte→destino que alimentarão o grafo de lineage (RF04).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from processor.models import ObjectType, UnifiedObject

logger = logging.getLogger("bw_reveng.processor.normalizer")

#: Códigos de SOURCETYPE/TARGETTYPE usados pelo BW (RSTRAN/RSBKDTP/RSOHCPRSRC) mapeados
#: para o `ObjectType` unificado. Ajuste conforme observado no sistema do cliente.
_TYPE_CODE_MAP: dict[str, ObjectType] = {
    "CUBE": ObjectType.INFO_CUBE,
    "ODSO": ObjectType.DSO,
    "ADSO": ObjectType.ADSO,
    "HCPR": ObjectType.COMPOSITE_PROVIDER,
    "MPRO": ObjectType.MULTI_PROVIDER,
    "OSVI": ObjectType.OPEN_ODS_VIEW,
    "IOBJ": ObjectType.INFO_OBJECT,
    "CHA": ObjectType.INFO_OBJECT,
    "KYF": ObjectType.INFO_OBJECT,
    "DTPA": ObjectType.DTP,
}


@dataclass
class NormalizationResult:
    objects: list[UnifiedObject] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _base_object(
    tipo: ObjectType,
    nome_tecnico: str,
    descricao: str,
    pacote: str,
    atributos: dict[str, Any],
) -> UnifiedObject:
    return UnifiedObject(
        id=UnifiedObject.make_id(tipo, nome_tecnico),
        tipo=tipo,
        nome_tecnico=nome_tecnico,
        descricao=descricao or "",
        pacote=pacote or "",
        camada=UnifiedObject.camada_for(tipo),
        atributos_especificos=atributos,
    )


def _normalize_infoobjects(rows: list[dict[str, Any]]) -> list[UnifiedObject]:
    return [
        _base_object(
            ObjectType.INFO_OBJECT,
            r["IOBJNM"],
            r.get("TXTLG", ""),
            r.get("DEVCLASS", ""),
            {
                "iobjtp": r.get("IOBJTP"),
                "last_user": r.get("LASTUSER"),
                "timestmp": r.get("TIMESTMP"),
                # Um InfoObject É o campo (schema veio de RSDCHA/RSDKYF — ver
                # extractor.classic_layer._infoobject_datatypes).
                "tipo_dado": r.get("tipo_dado"),
                "comprimento": r.get("comprimento"),
                "moeda": r.get("moeda"),
                "unidade": r.get("unidade"),
            },
        )
        for r in rows
    ]


def _normalize_infocubes(rows: list[dict[str, Any]]) -> list[UnifiedObject]:
    return [
        _base_object(
            ObjectType.INFO_CUBE,
            r["INFOCUBE"],
            r.get("TXTLG", ""),
            r.get("DEVCLASS", ""),
            {
                "last_user": r.get("LASTUSER"),
                "timestmp": r.get("TIMESTMP"),
                "campos": r.get("CAMPOS", []),
            },
        )
        for r in rows
    ]


def _normalize_dsos(rows: list[dict[str, Any]]) -> list[UnifiedObject]:
    return [
        _base_object(
            ObjectType.DSO,
            r["ODSOBJECT"],
            r.get("TXTLG", ""),
            r.get("DEVCLASS", ""),
            {
                "last_user": r.get("LASTUSER"),
                "timestmp": r.get("TIMESTMP"),
                "campos": r.get("CAMPOS", []),
            },
        )
        for r in rows
    ]


def _normalize_multiproviders(rows: list[dict[str, Any]]) -> list[UnifiedObject]:
    objects = []
    for r in rows:
        obj = _base_object(
            ObjectType.MULTI_PROVIDER,
            r["INFOCUBE"],
            r.get("TXTLG", ""),
            r.get("DEVCLASS", ""),
            {
                "last_user": r.get("LASTUSER"),
                "timestmp": r.get("TIMESTMP"),
                "campos": r.get("CAMPOS", []),
            },
        )
        obj.fontes = list(r.get("PART_PROVIDERS", []))
        objects.append(obj)
    return objects


def _normalize_adsos(rows: list[dict[str, Any]]) -> list[UnifiedObject]:
    return [
        _base_object(
            ObjectType.ADSO,
            r["ADSONM"],
            r.get("TXTLG", ""),
            r.get("DEVCLASS", ""),
            {
                "last_user": r.get("LASTUSER"),
                "timestmp": r.get("TIMESTMP"),
                "campos": r.get("CAMPOS", []),
            },
        )
        for r in rows
    ]


def _normalize_composite_providers(rows: list[dict[str, Any]], warnings: list[str]) -> list[UnifiedObject]:
    objects = []
    for r in rows:
        hana_view = r.get("HANA_VIEW") or {}
        obj = _base_object(
            ObjectType.COMPOSITE_PROVIDER,
            r["COMPPROV"],
            r.get("TXTLG", ""),
            r.get("DEVCLASS", ""),
            {
                "last_user": r.get("LASTUSER"),
                "timestmp": r.get("TIMESTMP"),
                "num_elements": r.get("NUM_ELEMENTS", 0),
                "hana_view": hana_view,
                # Colunas reais vêm do catálogo HANA (SYS.TABLE_COLUMNS) quando
                # --hana-schema foi informado na extração — ver
                # extractor.nextgen_layer.enrich_with_hana_catalog.
                "campos": hana_view.get("campos", []),
            },
        )
        source_names = []
        for src in r.get("SOURCES", []):
            source_names.append(src["source"])
        obj.fontes = source_names
        objects.append(obj)
    return objects


def _normalize_open_ods_views(rows: list[dict[str, Any]]) -> list[UnifiedObject]:
    objects = []
    for r in rows:
        obj = _base_object(
            ObjectType.OPEN_ODS_VIEW,
            r["VIEWNAME"],
            r.get("TXTLG", ""),
            r.get("DEVCLASS", ""),
            {
                "source_type": r.get("SOURCETYPE"),
                "timestmp": r.get("TIMESTMP"),
                "campos": r.get("CAMPOS", []),
            },
        )
        if r.get("SOURCE"):
            obj.fontes = [r["SOURCE"]]
        objects.append(obj)
    return objects


def _normalize_transformations(rows: list[dict[str, Any]]) -> list[UnifiedObject]:
    objects = []
    for r in rows:
        obj = _base_object(
            ObjectType.TRANSFORMACAO,
            r["TRANID"],
            "",
            r.get("DEVCLASS", ""),
            {
                "num_regras": r.get("NUM_REGRAS", 0),
                "source_type": r.get("SOURCETYPE"),
                "target_type": r.get("TARGETTYPE"),
                "timestmp": r.get("TIMESTMP"),
            },
        )
        if r.get("SOURCE"):
            obj.fontes = [r["SOURCE"]]
        if r.get("TARGET"):
            obj.destinos = [r["TARGET"]]
        objects.append(obj)
    return objects


def _normalize_dtps(rows: list[dict[str, Any]]) -> list[UnifiedObject]:
    objects = []
    for r in rows:
        obj = _base_object(
            ObjectType.DTP,
            r["DTP"],
            "",
            r.get("DEVCLASS", ""),
            {
                "dtp_type": r.get("DTPTYPE"),
                "source_type": r.get("SOURCETYPE"),
                "target_type": r.get("TARGETTYPE"),
                "timestmp": r.get("TIMESTMP"),
            },
        )
        if r.get("SOURCE"):
            obj.fontes = [r["SOURCE"]]
        if r.get("TARGET"):
            obj.destinos = [r["TARGET"]]
        objects.append(obj)
    return objects


def _normalize_process_chains(rows: list[dict[str, Any]]) -> list[UnifiedObject]:
    objects = []
    for r in rows:
        obj = _base_object(
            ObjectType.PROCESS_CHAIN,
            r["CHAIN_ID"],
            "",
            r.get("DEVCLASS", ""),
            {"timestmp": r.get("TIMESTMP")},
        )
        obj.destinos = list(r.get("CALLED_CHAINS", []))
        objects.append(obj)
    return objects


def _normalize_hierarchies(rows: list[dict[str, Any]]) -> list[UnifiedObject]:
    objects = []
    for r in rows:
        obj = _base_object(
            ObjectType.HIERARQUIA,
            r["HIENM"],
            r.get("TXTSH", ""),
            r.get("DEVCLASS", ""),
            {"iobjnm": r.get("IOBJNM"), "timestmp": r.get("TIMESTMP")},
        )
        if r.get("IOBJNM"):
            obj.fontes = [r["IOBJNM"]]
        objects.append(obj)
    return objects


_NORMALIZERS = {
    "InfoObject": _normalize_infoobjects,
    "InfoCube": _normalize_infocubes,
    "DSO": _normalize_dsos,
    "MultiProvider": _normalize_multiproviders,
    "ADSO": _normalize_adsos,
    "OpenODSView": _normalize_open_ods_views,
    "Transformacao": _normalize_transformations,
    "DTP": _normalize_dtps,
    "ProcessChain": _normalize_process_chains,
    "Hierarquia": _normalize_hierarchies,
}


def normalize(objects_by_type: dict[str, list[dict[str, Any]]]) -> NormalizationResult:
    """Converte a saída crua da extração no modelo unificado (RF03) e resolve
    `fontes`/`destinos` (hoje contendo apenas nomes técnicos) para ids do modelo
    unificado (`ObjectType:nome_tecnico`), completando o grafo de lineage (RF04).
    """
    result = NormalizationResult()

    for object_type, rows in objects_by_type.items():
        normalizer_fn = _NORMALIZERS.get(object_type)
        if object_type == "CompositeProvider":
            result.objects.extend(_normalize_composite_providers(rows, result.warnings))
            continue
        if normalizer_fn is None:
            logger.warning("Nenhum normalizador para o tipo '%s' — objetos ignorados", object_type)
            result.warnings.append(f"Tipo sem normalizador: {object_type} ({len(rows)} objetos ignorados)")
            continue
        result.objects.extend(normalizer_fn(rows))

    _resolve_references(result)
    return result


def _resolve_references(result: NormalizationResult) -> None:
    """Substitui nomes técnicos crus em `fontes`/`destinos` por ids do modelo unificado.

    Como a origem SQL nem sempre informa o tipo do objeto referenciado (ex: DTPs e
    Transformações trazem SOURCETYPE/TARGETTYPE, mas MultiProvider/CompositeProvider
    trazem apenas o nome), a resolução tenta, nesta ordem: (1) tipo explícito via
    `_TYPE_CODE_MAP`, (2) busca por nome técnico entre todos os objetos já normalizados.
    Referências não resolvidas viram um warning e são descartadas (não geram nó "fantasma").
    """
    by_name: dict[str, list[str]] = {}
    for obj in result.objects:
        by_name.setdefault(obj.nome_tecnico, []).append(obj.id)

    def resolve(raw_name: str, type_code: str | None) -> str | None:
        if type_code and type_code in _TYPE_CODE_MAP:
            candidate = UnifiedObject.make_id(_TYPE_CODE_MAP[type_code], raw_name)
            if any(obj.id == candidate for obj in result.objects):
                return candidate
        matches = by_name.get(raw_name, [])
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            result.warnings.append(f"Referência ambígua a '{raw_name}': candidatos {matches}")
            return None
        result.warnings.append(f"Referência não resolvida: '{raw_name}' (tipo={type_code})")
        return None

    for obj in result.objects:
        type_code = obj.atributos_especificos.get("source_type")
        resolved_fontes = []
        for raw in obj.fontes:
            resolved = resolve(raw, type_code)
            resolved_fontes.append(resolved if resolved else raw)
        obj.fontes = resolved_fontes

        target_type_code = obj.atributos_especificos.get("target_type")
        resolved_destinos = []
        for raw in obj.destinos:
            resolved = resolve(raw, target_type_code)
            resolved_destinos.append(resolved if resolved else raw)
        obj.destinos = resolved_destinos
