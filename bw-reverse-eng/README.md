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
contexto imediato e, quando disponível, a tabela de **Campos**) e
`docs/reports.md` (sumário, objetos sem documentação e complexidade).

### Estrutura/schema (campos, tipos, chaves)

Além do inventário e do lineage, a extração também traz o schema de campos de
cada objeto quando as tabelas correspondentes estão disponíveis:

| Tipo de objeto | Fonte do schema |
|---|---|
| InfoObject | `RSDCHA` (características) / `RSDKYF` (key figures) — tipo de dado, comprimento, moeda/unidade |
| InfoCube / MultiProvider | `RSDCUBEIOBJ` (características + key figures atribuídos) + tipo de dado via RSDCHA/RSDKYF |
| DSO standard | `RSDODSOIOBJ` — campos e marcação de chave (`FIELDTYPE = 'KEY'`) |
| ADSO | Catálogo HANA (`SYS.TABLE_COLUMNS`), **melhor esforço**: assume que o nome da tabela ativa é igual ao nome técnico do ADSO — pode não bater dependendo da versão/Support Package |
| CompositeProvider / Open ODS View | Catálogo HANA (`SYS.TABLE_COLUMNS`) sobre a Calculation View / tabela de origem — fonte confiável, já que esses objetos são fisicamente HANA |

O schema fica em `atributos_especificos.campos` (lista de `{nome, tipo_dado,
comprimento, chave}`) no modelo unificado, e é exibido na página de cada
objeto. Os tipos de dado ficam no **vocabulário de origem** (BW: `CHAR`/`DEC`/
`CURR`; HANA: `NVARCHAR`/`DECIMAL`) — não há tradução automática para os tipos
CDS do Datasphere.

Aviso: ao contrário de `RSDIOBJ`/`RSDCUBE`/`RSTRAN` (citadas na seção 3.1 da
especificação), as tabelas `RSDCHA`/`RSDKYF`/`RSDCUBEIOBJ`/`RSDODSOIOBJ` são
menos universalmente documentadas — valide os nomes contra o sandbox do
cliente. Se divergirem, a extração principal do objeto não é afetada (mesmo
padrão tolerante usado em todo o app): o objeto é extraído normalmente, só sem
`campos`.

### Lógica de negócio das regras de transformação (via RFC complementar)

`RSTRANSTEPS` só dá a **contagem** de regras de uma Transformação — a lógica em
si (mapeamentos campo-a-campo, rotinas ABAP, fórmulas) fica armazenada de forma
serializada/binária no BW e não é recuperável via SQL puro (seção 3.3 da
especificação). Para isso, use a conexão RFC complementar:

```bash
# Testar a conexão RFC (separada da fonte principal --source)
bw-reveng test-connection --rfc

# Extrair incluindo a lógica de negócio das regras
bw-reveng extract --output ./data/snapshot_2026-07-21/ --with-rfc-rules
```

Configure `RFC_*` no `.env` (ver `.env.example`) — só é exigido quando você usa
`--rfc`/`--with-rfc-rules`; o fluxo principal (SQL/CSV) nunca depende disso.

**Leia isto antes de configurar**:
1. **Exige o SAP NW RFC SDK** — biblioteca C proprietária baixada do SAP
   Support Portal (não vai por `pip install pyrfc` sozinho; precisa da SDK
   instalada no SO). Este app foi implementado e testado com uma conexão RFC
   fake (injeção de dependência, ver `tests/test_rfc_connection.py`), mas
   **nunca rodou contra um SAP real** — valide com cuidado.
2. **Não existe um BAPI padrão universal** para "dump estruturado da lógica de
   uma transformação". `RFC_RULES_FUNCTION_MODULE` no `.env` é configurável
   porque, na prática, isso quase sempre exige uma função **Z-customizada**
   que o time ABAP do cliente precisa implementar e disponibilizar via RFC —
   confirme com o time do cliente qual função (padrão ou customizada) está
   disponível, e ajuste o nome dos parâmetros em
   `extractor/transformation_rules.py` se a função devolver campos com nomes
   diferentes dos já tratados (`SOURCE_FIELD`/`TARGET_FIELD`/`RULETYPE`/
   `ROUTINE`, entre variações comuns).
3. **Fallback sem BAPI estruturado**: com `RFC_FETCH_ROUTINE_SOURCE=true`, cada
   regra do tipo rotina tem seu código-fonte ABAP lido via `RPY_PROGRAM_READ`
   (função padrão SAP) — não estrutura a lógica, mas recupera o texto para
   leitura/auditoria manual.

Quando disponível, a lógica fica em `atributos_especificos.regras` (lista de
`{campo_origem, campo_destino, tipo_regra, rotina, rotina_fonte}`) de cada
Transformação, aparece no scaffold Datasphere (`fluxos[*].regras_bw`) e
substitui a mensagem genérica de pendência por uma nota específica — mas ainda
assim **precisa ser recriada manualmente** no Datasphere (rotinas ABAP não são
convertidas automaticamente para SQL/lógica gráfica).

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
importar** e **não reproduz o resultado do BW automaticamente**, mesmo com
schema de campos (seção anterior) e regras de transformação via RFC (seção
anterior) já extraídos. Duas ressalvas continuam valendo:
1. Os tipos de dado em `csn_stub.elements[*].tipo_dado_origem` estão no
   **vocabulário de origem** (BW/HANA), não nos tipos CDS do Datasphere —
   precisam de mapeamento manual (`avisos` e a `pendencia` de cada entidade
   deixam isso explícito). Quando o schema não foi resolvido para um objeto
   (tabela ausente, ADSO sem correspondência no catálogo HANA etc.),
   `elements` fica vazio e a pendência pede para completar manualmente.
2. **Lógica de negócio das regras de transformação** só aparece em
   `fluxos[*].regras_bw` se a extração rodou com `--with-rfc-rules` (seção
   anterior) — sem isso, cada fluxo só traz a contagem de regras
   (`num_regras_bw`) e origem/destino, não a lógica em si. Mesmo quando
   presente, a lógica (rotinas ABAP, fórmulas) precisa ser **recriada
   manualmente** como View/Data Flow no Datasphere — não há conversão
   automática de ABAP para SQL/lógica gráfica.

Trate o arquivo gerado como um **rascunho de arquitetura-alvo** para acelerar
o redesenho manual no Data Builder — o próprio JSON lista essas limitações em
`avisos` e uma pendência por objeto/fluxo, ajustada conforme o que foi
efetivamente extraído em cada execução.

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
SQL do HANA, lista de pacotes/namespaces relevantes e versão exata do Support
Package (pode afetar nomes de tabela/coluna — valide as queries de
`extractor/classic_layer.py` e `extractor/nextgen_layer.py` num sandbox do
cliente antes da extração completa).

Se for usar `--with-rfc-rules` (lógica de negócio das regras de
transformação), levante também: usuário CPIC + perfil `S_RS_ADMWB`/
`S_RS_IOBJ` (ou o que a função RFC escolhida exigir) com autorização de
execução (`S_RFC`) para a função configurada em `RFC_RULES_FUNCTION_MODULE` e
para `RPY_PROGRAM_READ` (se usar `RFC_FETCH_ROUTINE_SOURCE`), confirmação de
qual função RFC está disponível ou se o time ABAP precisa implementar uma
Z-customizada, e o SAP NW RFC SDK instalado na máquina que vai rodar a
extração.

## Mapeamento de requisitos

| Requisito | Onde |
|---|---|
| RF01 Conexão e autenticação | `config/settings.py`, `extractor/connection.py` (HANA), `extractor/csv_source.py` (CSV), `extractor/rfc_connection.py` (RFC complementar) |
| RF02 Extração de metadados (+ schema de campos) | `extractor/classic_layer.py`, `extractor/nextgen_layer.py`, `extractor/export.py` |
| RF03 Modelo unificado | `processor/models.py`, `processor/normalizer.py` |
| RF04 Grafo de lineage | `processor/graph_builder.py` |
| RF05 Documentação + Mermaid | `docgen/markdown_generator.py`, `docgen/mermaid_generator.py` |
| RF06 Inventário e relatórios | `processor/reports.py` |
| Lógica de negócio das regras (RFC, seção 3.3) | `extractor/rfc_connection.py`, `extractor/transformation_rules.py` |
| Scaffold Bronze/Prata/Ouro para Datasphere | `processor/medallion.py`, `exporters/datasphere.py` |

## Fora do escopo (v1)

Alteração de objetos no BW, extração de dados transacionais, automação de
deploy de transporte e análise de performance de queries (ver seção 1.2).
Também fora do escopo: tradução automática dos tipos de dado BW/HANA para os
tipos CDS do Datasphere, e uma função RFC padrão pronta para extrair regras de
transformação (o `RFC_RULES_FUNCTION_MODULE` quase sempre precisa ser uma
função Z-customizada implementada pelo time ABAP do cliente — ver seção
"Lógica de negócio das regras de transformação"). Por isso o
`export-datasphere` continua sendo um rascunho, não uma migração automática
pronta para carregar, mesmo com schema de campos e regras já extraídos.
