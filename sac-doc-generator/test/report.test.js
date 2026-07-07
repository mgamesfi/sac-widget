import { test } from "node:test";
import assert from "node:assert/strict";
import { loadFixtureModels } from "../src/sac/modelClient.js";
import { evaluateModels } from "../src/evaluator/evaluate.js";
import { buildFullReportMarkdown } from "../src/report/buildReport.js";
import { renderReportHtml } from "../src/report/renderHtml.js";

test("end-to-end: fixture models produce a full markdown + html report", async () => {
  const models = await loadFixtureModels();
  assert.ok(models.length > 0);

  const evaluations = evaluateModels(models);
  assert.equal(evaluations.length, models.length);

  const markdown = buildFullReportMarkdown({ tenantLabel: "Demo", models, evaluations });
  assert.match(markdown, /# Documenta/);
  for (const model of models) {
    assert.ok(markdown.includes(model.name), `report should mention ${model.name}`);
  }

  const html = renderReportHtml(markdown);
  assert.match(html, /<h1>/);
  assert.match(html, /<table>/);
});
