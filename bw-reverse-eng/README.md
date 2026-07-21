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
A configuração de HANA só é exigida quando `--source hana` (o padrão) — no
modo `--source csv` (ver abaixo) o `.env` nem precisa existir.

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

### Fonte alternativa: tabelas em arquivos CSV

Quando não há acesso SQL direto ao HANA (ex: o cliente só consegue exportar as
tabelas de dicionário para arquivo), use `--source csv` em vez de conectar ao
HANA — nenhuma outra etapa do fluxo (`process`, `generate-docs`, `summary`)
muda, porque a extração continua gerando o mesmo snapshot JSON:

```bash
bw-reveng test-connection --source csv --csv-dir ./exports_cliente/
bw-reveng extract --source csv --csv-dir ./exports_cliente/ --output ./data/snapshot_2026-07-21/
```

Cada tabela deve estar em `<TABELA>.csv` dentro do diretório informado (ex:
`RSDCUBE.csv`, `RSDIOBJ.csv`, `SYS.VIEWS.csv`), com as mesmas colunas das
tabelas de dicionário reais (ver `extractor/csv_source.py:KNOWN_TABLES` para a
lista completa e `extractor/classic_layer.py`/`extractor/nextgen_layer.py`
para as colunas exatas usadas em cada consulta). O delimitador é detectado
automaticamente (vírgula, ponto e vírgula, tab ou `|`); use `--csv-delimiter`
para forçar um valor. Tabelas ausentes não travam a extração — o tipo de
objeto correspondente é apenas reportado vazio no log, e tabelas de texto
(`*T`) ausentes não quebram os JOINs (a descrição só fica em branco).

A documentação gerada fica em `docs/index.md` (índice geral + visão macro de
lineage), `docs/objects/<id>.md` (uma página por objeto, com diagrama de
contexto imediato) e `docs/reports.md` (sumário, objetos sem documentação e
complexidade).

### Scaffold para SAP Datasphere (arquitetura medalhão Bronze/Prata/Ouro)

```bash
bw-reveng export-datasphere --input ./processed/ --output ./datasphere/scaffold.json
```

Classifica cada objeto numa camada medalhão — heurística por tipo + posição no
grafo de lineage (ver `processor/medallion.py`): DSO/ADSO sem fonte observada
→ Bronze, DSO/ADSO com fonte, InfoObject e Hierarquia → Prata, InfoCube/
MultiProvider/CompositeProvider/OpenODSView → Ouro, e Transformação/DTP/
Process Chain → `pipeline` (orquestração, não é uma camada de dado). Gera um
JSON com entidades nomeadas por convenção (`BRZ_`/`SLV_`/`GLD_`), espaços
sugeridos (`BW_BRONZE`/`BW_SILVER`/`BW_GOLD`) e os fluxos de transformação
entre elas.

**Leia isto antes de usar**: o JSON gerado **não é um CSN oficial pronto para
importar** e **não reproduz o resultado do BW automaticamente**. Faltam duas
coisas que este app não extrai hoje:
1. **Schema de campos** de cada objeto (nome/tipo/chave) — por isso todo
   `csn_stub.elements` sai vazio.
2. **Lógica de negócio das regras de transformação** (mapeamentos, rotinas,
   fórmulas) — as regras complexas do BW costumam ficar serializadas e só
   seriam recuperáveis via RFC/BAPI (`RSTRAN_*`), camada não implementada
   nesta versão (ver seção 3.3 da especificação e `Fora do escopo` abaixo).

Trate o arquivo gerado como um **rascunho de arquitetura-alvo** para acelerar
o redesenho manual no Data Builder — o próprio JSON lista essas limitações em
`avisos` e uma pendência por objeto/fluxo.

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
| RF01 Conexão e autenticação | `config/settings.py`, `extractor/connection.py` (HANA), `extractor/csv_source.py` (CSV) |
| RF02 Extração de metadados | `extractor/classic_layer.py`, `extractor/nextgen_layer.py`, `extractor/export.py` |
| RF03 Modelo unificado | `processor/models.py`, `processor/normalizer.py` |
| RF04 Grafo de lineage | `processor/graph_builder.py` |
| RF05 Documentação + Mermaid | `docgen/markdown_generator.py`, `docgen/mermaid_generator.py` |
| RF06 Inventário e relatórios | `processor/reports.py` |
| Scaffold Bronze/Prata/Ouro para Datasphere | `processor/medallion.py`, `exporters/datasphere.py` |

## Fora do escopo (v1)

Alteração de objetos no BW, extração de dados transacionais, automação de
deploy de transporte e análise de performance de queries (ver seção 1.2).
Também fora do escopo: extração de schema de campos por objeto e da lógica de
negócio das regras de transformação (exigiria camada RFC/BAPI, não
implementada) — por isso o `export-datasphere` gera um rascunho, não uma
migração automática pronta para carregar.
