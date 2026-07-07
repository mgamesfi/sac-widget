import { test } from "node:test";
import assert from "node:assert/strict";
import { evaluateModel } from "../src/evaluator/evaluate.js";

function baseModel(overrides = {}) {
  return {
    id: "M1",
    name: "Test Model",
    description: "A model used for tests",
    type: "Analytic",
    dimensions: [],
    measures: [],
    ...overrides,
  };
}

test("clean model scores 100 with no findings", () => {
  const result = evaluateModel(baseModel());
  assert.equal(result.score, 100);
  assert.equal(result.findings.length, 0);
});

test("flags generic dimension names as high severity", () => {
  const model = baseModel({
    dimensions: [
      { id: "d1", name: "Dimension_1", description: "x", isPublic: true, hasHierarchy: false, hierarchyCount: 0, memberCount: 3 },
    ],
  });
  const result = evaluateModel(model);
  const finding = result.findings.find((f) => f.ruleId === "generic-naming");
  assert.ok(finding, "expected generic-naming finding");
  assert.equal(finding.severity, "high");
});

test("flags planning models missing a Version dimension", () => {
  const model = baseModel({ type: "Planning", dimensions: [] });
  const result = evaluateModel(model);
  const finding = result.findings.find((f) => f.ruleId === "missing-version-dimension");
  assert.ok(finding);
});

test("does not flag missing Version dimension for non-planning models", () => {
  const model = baseModel({ type: "Analytic", dimensions: [] });
  const result = evaluateModel(model);
  const finding = result.findings.find((f) => f.ruleId === "missing-version-dimension");
  assert.equal(finding, undefined);
});

test("flags currency measures without conversion configured", () => {
  const model = baseModel({
    measures: [
      { id: "m1", name: "Revenue", description: "x", dataType: "Decimal", unitType: "Currency", currencyConversion: null },
    ],
  });
  const result = evaluateModel(model);
  const finding = result.findings.find((f) => f.ruleId === "currency-measure-without-conversion");
  assert.ok(finding);
});

test("flags large dimensions without a hierarchy", () => {
  const model = baseModel({
    dimensions: [
      { id: "d1", name: "Product", description: "x", isPublic: true, hasHierarchy: false, hierarchyCount: 0, memberCount: 5000 },
    ],
  });
  const result = evaluateModel(model);
  const finding = result.findings.find((f) => f.ruleId === "large-flat-dimension-no-hierarchy");
  assert.ok(finding);
});

test("score decreases as findings accumulate", () => {
  const clean = evaluateModel(baseModel());
  const dirty = evaluateModel(
    baseModel({
      type: "Planning",
      dimensions: [
        { id: "d1", name: "Dimension_1", description: "", isPublic: false, hasHierarchy: false, hierarchyCount: 0, memberCount: 5000 },
      ],
    })
  );
  assert.ok(dirty.score < clean.score);
});
