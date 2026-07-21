"""Filtros de extração compartilhados entre classic_layer e nextgen_layer (RF02)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass(frozen=True)
class ExtractionFilters:
    """Filtros aplicáveis à extração de metadados.

    - `object_types`: restringe quais funções de extração rodam (ex: apenas InfoCubes).
      Vazio/None = extrai todos os tipos suportados.
    - `packages`: restringe por namespace/pacote de desenvolvimento (coluna `DEVCLASS`
      nas tabelas clássicas, quando disponível).
    - `changed_since`: extração incremental — apenas objetos alterados a partir desta data.
    """

    object_types: frozenset[str] = field(default_factory=frozenset)
    packages: frozenset[str] = field(default_factory=frozenset)
    changed_since: date | None = None

    def wants(self, object_type: str) -> bool:
        return not self.object_types or object_type in self.object_types

    def package_clause(self, column: str = "DEVCLASS") -> tuple[str, tuple]:
        """Retorna (fragmento SQL, params) para filtro de pacote, ou ("", ()) se não houver."""
        if not self.packages:
            return "", ()
        placeholders = ", ".join("?" for _ in self.packages)
        return f" AND {column} IN ({placeholders})", tuple(self.packages)

    def changed_since_clause(self, column: str = "TIMESTMP") -> tuple[str, tuple]:
        if not self.changed_since:
            return "", ()
        return f" AND {column} >= ?", (self.changed_since.strftime("%Y%m%d"),)
