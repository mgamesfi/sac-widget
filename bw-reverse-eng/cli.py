"""CLI principal do bw-reveng (seção 8 da especificação)."""
from __future__ import annotations

import logging
import sys
from datetime import date, datetime
from pathlib import Path

import typer

from config.settings import load_app_settings, load_hana_settings
from extractor.connection import HanaConnection
from extractor.filters import ExtractionFilters
from extractor.pipeline import run_extraction
from processor.pipeline import load_processed, run_process
from processor.reports import complexity_report, missing_docs_report, summary_report
from processor.graph_builder import find_orphans

app = typer.Typer(
    name="bw-reveng",
    help="Engenharia reversa de metadados SAP BW 7.5 on HANA: extração, lineage e documentação.",
    no_args_is_help=True,
)


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stderr,
    )


def _connection_from_settings() -> HanaConnection:
    hana = load_hana_settings()
    return HanaConnection(
        host=hana.host,
        port=hana.port,
        user=hana.user,
        password=hana.password,
        client_cert=str(hana.client_cert) if hana.client_cert else None,
        client_key=str(hana.client_key) if hana.client_key else None,
        encrypt=hana.encrypt,
        validate_cert=hana.validate_cert,
        connect_timeout_s=hana.connect_timeout_s,
    )


@app.command("test-connection")
def test_connection() -> None:
    """Valida conectividade e permissões antes de uma extração completa (RF01)."""
    app_settings = load_app_settings()
    _configure_logging(app_settings.log_level)

    conn = _connection_from_settings()
    with conn:
        info = conn.test_connection()

    typer.echo(f"Host: {info['host']}:{info['port']}  Usuário: {info['user']}")
    if not info.get("ok"):
        typer.secho(f"FALHA: {info.get('error', 'permissões insuficientes')}", fg=typer.colors.RED)
        for label, ok in info.get("permissions", {}).items():
            typer.echo(f"  - {label}: {'OK' if ok else 'SEM ACESSO'}")
        raise typer.Exit(code=1)

    typer.secho(f"OK — HANA versão {info['hana_version']}", fg=typer.colors.GREEN)
    for label, ok in info.get("permissions", {}).items():
        typer.echo(f"  - {label}: {'OK' if ok else 'SEM ACESSO'}")


@app.command("extract")
def extract(
    output: Path = typer.Option(..., "--output", help="Diretório base para o snapshot de saída"),
    types: list[str] = typer.Option(
        None, "--type", help="Filtra por tipo de objeto (repetível). Vazio = todos."
    ),
    packages: list[str] = typer.Option(
        None, "--package", help="Filtra por pacote/namespace (repetível). Vazio = todos."
    ),
    since: str | None = typer.Option(
        None, "--since", help="Extração incremental: apenas objetos alterados desde AAAA-MM-DD"
    ),
    hana_schema: str | None = typer.Option(
        None, "--hana-schema", help="Schema HANA para enriquecer CompositeProviders com o catálogo"
    ),
) -> None:
    """Extrai metadados das camadas clássica e next-gen (RF02), roda dentro da VPN do cliente."""
    app_settings = load_app_settings()
    _configure_logging(app_settings.log_level)

    changed_since = date.fromisoformat(since) if since else None
    filters = ExtractionFilters(
        object_types=frozenset(types or ()),
        packages=frozenset(packages or ()),
        changed_since=changed_since,
    )

    conn = _connection_from_settings()
    with conn:
        snapshot_dir = run_extraction(
            conn, filters, output, app_settings.default_language, hana_schema
        )

    typer.secho(f"Snapshot gravado em {snapshot_dir}", fg=typer.colors.GREEN)


@app.command("process")
def process(
    input: Path = typer.Option(..., "--input", help="Diretório do snapshot extraído"),
    output: Path = typer.Option(..., "--output", help="Diretório de saída processada"),
) -> None:
    """Normaliza os objetos extraídos e monta o grafo de lineage (RF03/RF04)."""
    app_settings = load_app_settings()
    _configure_logging(app_settings.log_level)

    result = run_process(input, output)

    typer.secho(
        f"{len(result.objects)} objetos, {result.graph.number_of_edges()} relações — "
        f"gravado em {output}",
        fg=typer.colors.GREEN,
    )
    if result.warnings:
        typer.secho(f"{len(result.warnings)} avisos de normalização (ver processing.log.json)", fg=typer.colors.YELLOW)
    orphans = result.orphan_counts
    typer.echo(
        f"Órfãos — sem fonte: {orphans['sem_fonte']}, sem consumidor: {orphans['sem_consumidor']}, "
        f"isolados: {orphans['isolados']}"
    )


@app.command("generate-docs")
def generate_docs(
    input: Path = typer.Option(..., "--input", help="Diretório de saída processada (do comando process)"),
    output: Path = typer.Option(..., "--output", help="Diretório de saída da documentação"),
) -> None:
    """Gera documentação Markdown + diagramas Mermaid (RF05/RF06)."""
    from docgen.markdown_generator import generate_documentation

    app_settings = load_app_settings()
    _configure_logging(app_settings.log_level)

    objects, graph = load_processed(input)
    generate_documentation(
        objects,
        graph,
        output,
        app_settings.composite_provider_source_threshold,
        app_settings.transformation_rule_threshold,
    )
    typer.secho(f"Documentação gerada em {output}", fg=typer.colors.GREEN)


@app.command("summary")
def summary(
    input: Path = typer.Option(..., "--input", help="Diretório de saída processada (do comando process)"),
) -> None:
    """Imprime o relatório-sumário de inventário (RF06)."""
    app_settings = load_app_settings()
    _configure_logging(app_settings.log_level)

    objects, graph = load_processed(input)
    summ = summary_report(objects)
    missing = missing_docs_report(objects)
    complexity = complexity_report(
        objects,
        app_settings.composite_provider_source_threshold,
        app_settings.transformation_rule_threshold,
    )
    orphans = find_orphans(graph)

    typer.echo(f"Total de objetos: {summ.total}")
    typer.echo("Por tipo:")
    for tipo, qtd in summ.por_tipo.items():
        typer.echo(f"  - {tipo}: {qtd}")
    typer.echo("Por camada:")
    for camada, qtd in summ.por_camada.items():
        typer.echo(f"  - {camada}: {qtd}")
    typer.echo(f"Sem documentação: {len(missing)}")
    typer.echo(f"Achados de complexidade: {len(complexity)}")
    typer.echo(
        f"Órfãos — sem fonte: {len(orphans.sem_fonte)}, sem consumidor: {len(orphans.sem_consumidor)}"
    )


if __name__ == "__main__":
    app()
