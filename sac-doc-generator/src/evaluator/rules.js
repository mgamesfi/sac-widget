/**
 * Best-practice rules for SAC data models. Each rule receives the normalized model
 * (see modelClient.parseEdmxToModel for the shape) and returns zero or more findings.
 * Severity: "high" (fix before go-live), "medium" (fix soon), "low" (nice to have).
 */

const GENERIC_NAME_PATTERN = /^(dimension|measure|attribute|version|field)[_\s]?\d+$/i;

export const rules = [
  {
    id: "model-missing-description",
    title: "Modelo sem descrição de negócio",
    check(model) {
      if (model.description?.trim()) return [];
      return [
        {
          severity: "low",
          summary: `O modelo "${model.name}" não possui descrição.`,
          recommendation:
            "Preencha a descrição do modelo com o propósito de negócio, público-alvo e frequência de atualização.",
          affected: [model.name],
        },
      ];
    },
  },
  {
    id: "dimension-missing-description",
    title: "Dimensões sem descrição",
    check(model) {
      const offenders = model.dimensions.filter((d) => !d.description?.trim());
      if (offenders.length === 0) return [];
      return [
        {
          severity: "medium",
          summary: `${offenders.length} dimensão(ões) sem descrição de negócio.`,
          recommendation:
            "Adicione descrições claras a cada dimensão para que consumidores do modelo entendam seu significado sem precisar consultar o time de modelagem.",
          affected: offenders.map((d) => d.name),
        },
      ];
    },
  },
  {
    id: "generic-naming",
    title: "Nomenclatura genérica/técnica",
    check(model) {
      const offenders = [...model.dimensions, ...model.measures].filter((f) =>
        GENERIC_NAME_PATTERN.test(f.name)
      );
      if (offenders.length === 0) return [];
      return [
        {
          severity: "high",
          summary: `${offenders.length} objeto(s) com nome técnico/genérico (ex.: "Dimension_1").`,
          recommendation:
            "Renomeie dimensões e medidas com nomes de negócio significativos. Nomes genéricos dificultam a governança, o reuso e a auditoria do modelo.",
          affected: offenders.map((f) => f.name),
        },
      ];
    },
  },
  {
    id: "missing-version-dimension",
    title: "Modelo de planejamento sem dimensão Version",
    check(model) {
      if (model.type !== "Planning") return [];
      const hasVersion = model.dimensions.some((d) => /version/i.test(d.name));
      if (hasVersion) return [];
      return [
        {
          severity: "high",
          summary: "Modelo de planejamento não possui uma dimensão Version.",
          recommendation:
            "Modelos de planejamento devem ter uma dimensão Version para suportar cenários (Real, Orçamento, Previsão) e versionamento de dados.",
          affected: [model.name],
        },
      ];
    },
  },
  {
    id: "large-flat-dimension-no-hierarchy",
    title: "Dimensão grande sem hierarquia",
    check(model) {
      const offenders = model.dimensions.filter(
        (d) => (d.memberCount ?? 0) > 200 && !d.hasHierarchy
      );
      if (offenders.length === 0) return [];
      return [
        {
          severity: "medium",
          summary: `${offenders.length} dimensão(ões) com muitos membros (>200) e sem hierarquia.`,
          recommendation:
            "Considere adicionar hierarquias para permitir drill-down/consolidação e melhorar a performance de histórias que agregam por essas dimensões.",
          affected: offenders.map((d) => `${d.name} (${d.memberCount} membros)`),
        },
      ];
    },
  },
  {
    id: "currency-measure-without-conversion",
    title: "Medida monetária sem conversão de moeda configurada",
    check(model) {
      const offenders = model.measures.filter(
        (m) => m.unitType === "Currency" && !m.currencyConversion
      );
      if (offenders.length === 0) return [];
      return [
        {
          severity: "high",
          summary: `${offenders.length} medida(s) monetária(s) sem tipo de conversão de moeda.`,
          recommendation:
            "Configure a conversão de moeda (ex.: taxa corporativa, média ou de fechamento) para medidas monetárias usadas em relatórios multi-moeda, evitando somas incorretas entre moedas.",
          affected: offenders.map((m) => m.name),
        },
      ];
    },
  },
  {
    id: "no-public-dimension-reuse",
    title: "Baixo reuso de dimensões públicas",
    check(model) {
      if (model.dimensions.length === 0) return [];
      const publicRatio =
        model.dimensions.filter((d) => d.isPublic).length / model.dimensions.length;
      if (publicRatio >= 0.4) return [];
      return [
        {
          severity: "low",
          summary: `Apenas ${Math.round(publicRatio * 100)}% das dimensões são públicas/reutilizáveis.`,
          recommendation:
            "Avalie promover dimensões mestras (ex.: Cost Center, Product, Entity) para dimensões públicas, permitindo reuso entre modelos e reduzindo divergências de cadastro.",
          affected: [model.name],
        },
      ];
    },
  },
  {
    id: "too-many-measures",
    title: "Modelo com número excessivo de medidas",
    check(model) {
      if (model.measures.length <= 40) return [];
      return [
        {
          severity: "low",
          summary: `O modelo possui ${model.measures.length} medidas.`,
          recommendation:
            "Modelos com dezenas de medidas tendem a indicar que múltiplos assuntos de negócio foram combinados em um único modelo. Avalie separar em modelos menores e mais coesos.",
          affected: [model.name],
        },
      ];
    },
  },
];
