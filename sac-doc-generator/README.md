# SAC Doc Generator

Aplicação web que se conecta a um tenant do **SAP Analytics Cloud (SAC)**, extrai os
metadados dos modelos de dados e gera um relatório de **documentação + avaliação de
boas práticas**, com recomendações de melhoria.

## Escopo (v1)

- Foco em **modelos de dados** (dimensões, medidas, hierarquias). Stories/dashboards,
  segurança e fluxos de importação de dados ficam para versões futuras.
- Extração via APIs REST do SAC, autenticação **OAuth2 client credentials** (2-legged).
- Um motor de regras de boas práticas roda sobre os metadados extraídos e gera achados
  com severidade (alta/média/baixa) e recomendação.
- O relatório é gerado em Markdown e renderizado em HTML na própria aplicação, com
  opção de download do `.md`.

## Como rodar

```bash
npm install
npm start
# abra http://localhost:3000
```

Para desenvolvimento com reload automático: `npm run dev`.

Rodar os testes: `npm test`.

## Modo demo vs. tenant real

A tela inicial tem duas opções:

- **Modo demo**: usa dados de exemplo (`src/sac/fixtures/sample-models.json`) para
  demonstrar o pipeline completo sem precisar de credenciais. Útil para validar a
  ferramenta antes de conectar em um ambiente produtivo.
- **Conectar a um tenant real**: pede a URL base do tenant, a Token URL OAuth2, o
  Client ID e o Client Secret.

### Como obter as credenciais no SAC

1. No tenant SAC, vá em **Administration > App Integration > OAuth Clients**.
2. Crie um cliente OAuth com o fluxo **Client Credentials** (machine-to-machine).
3. Copie a **Token URL**, o **Client ID** e o **Secret** gerados — eles são
   específicos do seu tenant.

As credenciais são enviadas apenas na requisição de análise e **não são persistidas**
pelo backend (sem banco de dados, sem log de secrets).

## Arquitetura

```
src/
  sac/
    authClient.js     -> troca client_credentials por access_token (OAuth2 padrão)
    modelClient.js     -> lista providers e busca metadados ($metadata/EDMX) de cada modelo
    fixtures/           -> dados de exemplo para o modo demo
  evaluator/
    rules.js            -> regras de boas práticas (uma função pura por regra)
    evaluate.js          -> roda as regras e calcula um score 0-100 por modelo
  report/
    buildReport.js       -> monta o relatório em Markdown (inventário + achados)
    renderHtml.js         -> Markdown -> HTML para exibir no navegador
  server.js              -> Express: serve o front-end e a rota POST /api/analyze
public/                  -> front-end estático (form de conexão + visualizador do relatório)
```

### ⚠️ Nota importante sobre os endpoints da API do SAC

O caminho para listar os *providers* (modelos) segue o padrão documentado pela SAP
para a **Data Export API** (`/dataexport/administration/Namespaces(NamespaceID='sac')/Providers/`).

Já o caminho usado para buscar o `$metadata` (EDMX) de cada modelo individual
(`modelClient.js: fetchModelMetadata`) **é gerado por tenant** — o SAC expõe um
OpenAPI/EDMX específico da sua instância em Administration > App Integration. Se o
caminho não bater com o do seu tenant, ajuste apenas essa função; o restante do
pipeline (avaliação, relatório, UI) não precisa mudar.

## Regras de boas práticas implementadas

| Regra | Severidade | O que verifica |
|---|---|---|
| `generic-naming` | Alta | Nomes técnicos/genéricos (`Dimension_1`, `Measure_2`, ...) |
| `missing-version-dimension` | Alta | Modelo de planejamento sem dimensão `Version` |
| `currency-measure-without-conversion` | Alta | Medida monetária sem tipo de conversão de moeda |
| `dimension-missing-description` | Média | Dimensões sem descrição de negócio |
| `large-flat-dimension-no-hierarchy` | Média | Dimensão com >200 membros e sem hierarquia |
| `model-missing-description` | Baixa | Modelo sem descrição |
| `no-public-dimension-reuse` | Baixa | Baixo percentual de dimensões públicas/reutilizáveis |
| `too-many-measures` | Baixa | Modelo com mais de 40 medidas (possível falta de coesão) |

Novas regras podem ser adicionadas em `src/evaluator/rules.js` — cada regra é uma
função pura `(model) => finding[]`, o que facilita testá-las isoladamente
(`test/evaluate.test.js`).

## Limitações conhecidas (v1)

- Sem persistência: cada análise é feita sob demanda, nada é salvo entre sessões.
- Sem autenticação de usuários na própria aplicação (pensada para uso local/interno).
- Cobre apenas modelos de dados; stories, segurança (roles/teams) e import
  data flows ficam para uma v2.
- O parser de EDMX (`parseEdmxToModel`) classifica dimensões vs. medidas por
  heurística (tipo de dado + atributos de semântica); pode precisar de ajuste fino
  para modelos com estruturas incomuns.
