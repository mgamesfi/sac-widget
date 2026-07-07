import { rules } from "./rules.js";

const SEVERITY_WEIGHT = { high: 10, medium: 4, low: 1 };

/** Runs all rules against a single normalized model, returning findings + a 0-100 score. */
export function evaluateModel(model) {
  const findings = [];
  for (const rule of rules) {
    for (const finding of rule.check(model)) {
      findings.push({ ruleId: rule.id, ruleTitle: rule.title, ...finding });
    }
  }

  const penalty = findings.reduce((sum, f) => sum + SEVERITY_WEIGHT[f.severity], 0);
  const score = Math.max(0, 100 - penalty);

  return {
    modelId: model.id,
    modelName: model.name,
    score,
    findings: findings.sort((a, b) => SEVERITY_WEIGHT[b.severity] - SEVERITY_WEIGHT[a.severity]),
  };
}

export function evaluateModels(models) {
  return models.map(evaluateModel);
}
