const SEVERITY_LABEL = { high: "Alta", medium: "Média", low: "Baixa" };

/** Builds a full Markdown documentation + evaluation report for one model. */
export function buildModelReportMarkdown(model, evaluation) {
  const lines = [];
  lines.push(`## ${model.name}`);
  lines.push("");
  lines.push(`- **ID:** \`${model.id}\``);
  lines.push(`- **Tipo:** ${model.type}`);
  lines.push(`- **Descrição:** ${model.description?.trim() || "_(sem descrição)_"}`);
  lines.push(`- **Score de boas práticas:** ${evaluation.score}/100`);
  lines.push("");

  lines.push("### Dimensões");
  lines.push("");
  lines.push("| Nome | Descrição | Pública | Hierarquia | Membros |");
  lines.push("|---|---|---|---|---|");
  for (const d of model.dimensions) {
    lines.push(
      `| ${d.name} | ${d.description || "_—_"} | ${d.isPublic ? "Sim" : "Não"} | ${
        d.hasHierarchy ? `Sim (${d.hierarchyCount})` : "Não"
      } | ${d.memberCount ?? "—"} |`
    );
  }
  lines.push("");

  lines.push("### Medidas");
  lines.push("");
  lines.push("| Nome | Descrição | Tipo | Unidade/Moeda | Conversão de moeda |");
  lines.push("|---|---|---|---|---|");
  for (const m of model.measures) {
    lines.push(
      `| ${m.name} | ${m.description || "_—_"} | ${m.dataType} | ${m.unitType || "—"} | ${
        m.currencyConversion || "—"
      } |`
    );
  }
  lines.push("");

  lines.push("### Avaliação de boas práticas");
  lines.push("");
  if (evaluation.findings.length === 0) {
    lines.push("Nenhum problema encontrado pelas regras avaliadas.");
  } else {
    for (const f of evaluation.findings) {
      lines.push(`- **[${SEVERITY_LABEL[f.severity]}] ${f.ruleTitle}** — ${f.summary}`);
      lines.push(`  - Recomendação: ${f.recommendation}`);
      lines.push(`  - Afetados: ${f.affected.join(", ")}`);
    }
  }
  lines.push("");

  return lines.join("\n");
}

/** Builds the full report (all models) as a single Markdown document. */
export function buildFullReportMarkdown({ tenantLabel, models, evaluations }) {
  const generatedAt = new Date().toISOString();
  const avgScore = Math.round(
    evaluations.reduce((sum, e) => sum + e.score, 0) / (evaluations.length || 1)
  );

  const header = [
    `# Documentação e Avaliação do Ambiente SAC${tenantLabel ? ` — ${tenantLabel}` : ""}`,
    "",
    `_Gerado em ${generatedAt}_`,
    "",
    `**Modelos analisados:** ${models.length}  `,
    `**Score médio de boas práticas:** ${avgScore}/100`,
    "",
    "---",
    "",
  ].join("\n");

  const body = models
    .map((model, i) => buildModelReportMarkdown(model, evaluations[i]))
    .join("\n---\n\n");

  return header + body;
}
