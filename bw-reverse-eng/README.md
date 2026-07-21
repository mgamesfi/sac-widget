# bw-reveng

Engenharia reversa de metadados do **SAP BW 7.5 on HANA**: extrai o inventário
de objetos de modelagem (clássicos e next-gen), monta o grafo de lineage
(fonte → destino) e gera documentação em Markdown com diagramas Mermaid.

Implementado conforme a especificação técnica (seções 1–11): ver mapeamento
de requisitos ao final deste README.

## Arquitetura

A extração (dentro da VPN do cliente) é separada do processamento e da
geração de documentação (fora da VPN), evitando manter uma conexão HANA/RFC
persistente através do túnel — ver seção 2 da especificação.

```
extractor/   -> conecta ao HANA, lê tabelas de dicionário, grava snapshot JSON
processor/   -> normaliza para o modelo unificado e monta o grafo de lineage
docgen/      -> gera Markdown + diagramas Mermaid a partir do grafo
```

## Instalação

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
# ou: pip install -r requirements.txt
```

## Configuração

Copie `.env.example` para `.env` e preencha as credenciais do usuário técnico
HANA. Nenhuma credencial deve ser hardcoded (ver seção 5, NFR Segurança).

## Uso

```bash
# 1. Testar conectividade e permissões (RF01)
bw-reveng test-connection

# 2. Extrair metadados (roda dentro da VPN do cliente)
bw-reveng extract --output ./data/snapshot_2026-07-21/
# filtros opcionais: --type InfoCube --package ZBW --since 2026-01-01

# 3. Processar e montar o grafo de lineage (pode rodar fora da VPN)
bw-reveng process --input ./data/snapshot_2026-07-21/ --output ./processed/

# 4. Gerar documentação (Markdown + Mermaid)
bw-reveng generate-docs --input ./processed/ --output ./docs/

# 5. Relatório-sumário (contagens, complexidade, órfãos)
bw-reveng summary --input ./processed/
```

A documentação gerada fica em `docs/index.md` (índice geral + visão macro de
lineage), `docs/objects/<id>.md` (uma página por objeto, com diagrama de
contexto imediato) e `docs/reports.md` (sumário, objetos sem documentação e
complexidade).

## Testes

```bash
pytest
```

Os testes não dependem de um HANA real nem do driver `hdbcli`: a camada de
extração é testada contra um `SqlConnection` fake (`tests/conftest.py`), e há
um teste de ponta a ponta (`tests/test_end_to_end.py`) cobrindo
extract → process → generate-docs.

## Pré-requisitos a levantar com o cliente

Ver seção 9 da especificação: usuário técnico HANA com `SELECT` em
`SYS`/`_SYS_BI` e nas tabelas de dicionário BW, liberação de VPN até a porta
SQL do HANA, confirmação de necessidade de RFC complementar, lista de
pacotes/namespaces relevantes e versão exata do Support Package (pode afetar
nomes de tabela/coluna — valide as queries de `extractor/classic_layer.py` e
`extractor/nextgen_layer.py` num sandbox do cliente antes da extração completa).

## Mapeamento de requisitos

| Requisito | Onde |
|---|---|
| RF01 Conexão e autenticação | `config/settings.py`, `extractor/connection.py` |
| RF02 Extração de metadados | `extractor/classic_layer.py`, `extractor/nextgen_layer.py`, `extractor/export.py` |
| RF03 Modelo unificado | `processor/models.py`, `processor/normalizer.py` |
| RF04 Grafo de lineage | `processor/graph_builder.py` |
| RF05 Documentação + Mermaid | `docgen/markdown_generator.py`, `docgen/mermaid_generator.py` |
| RF06 Inventário e relatórios | `processor/reports.py` |

## Fora do escopo (v1)

Alteração de objetos no BW, extração de dados transacionais, automação de
deploy de transporte e análise de performance de queries (ver seção 1.2).
