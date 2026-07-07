import "dotenv/config";
import express from "express";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { fetchAccessToken } from "./sac/authClient.js";
import { listProviders, fetchModelMetadata, loadFixtureModels } from "./sac/modelClient.js";
import { evaluateModels } from "./evaluator/evaluate.js";
import { buildFullReportMarkdown } from "./report/buildReport.js";
import { renderReportHtml } from "./report/renderHtml.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const app = express();

app.use(express.json());
app.use(express.static(path.join(__dirname, "..", "public")));

app.post("/api/analyze", async (req, res) => {
  const { mode, tenantBaseUrl, tokenUrl, clientId, clientSecret } = req.body ?? {};

  try {
    const models = mode === "demo"
      ? await loadFixtureModels()
      : await fetchLiveModels({ tenantBaseUrl, tokenUrl, clientId, clientSecret });

    const evaluations = evaluateModels(models);
    const markdown = buildFullReportMarkdown({
      tenantLabel: mode === "demo" ? "Demo (dados de exemplo)" : tenantBaseUrl,
      models,
      evaluations,
    });

    res.json({
      tenantLabel: mode === "demo" ? "Demo (dados de exemplo)" : tenantBaseUrl,
      models,
      evaluations,
      markdown,
      html: renderReportHtml(markdown),
    });
  } catch (err) {
    res.status(400).json({ error: err.message });
  }
});

async function fetchLiveModels({ tenantBaseUrl, tokenUrl, clientId, clientSecret }) {
  if (!tenantBaseUrl || !tokenUrl || !clientId || !clientSecret) {
    throw new Error(
      "Informe tenantBaseUrl, tokenUrl, clientId e clientSecret, ou use o modo demo."
    );
  }
  const { accessToken } = await fetchAccessToken({ tokenUrl, clientId, clientSecret });
  const providers = await listProviders({ baseUrl: tenantBaseUrl, accessToken });
  const models = [];
  for (const provider of providers) {
    models.push(await fetchModelMetadata({ baseUrl: tenantBaseUrl, accessToken, providerId: provider.id }));
  }
  return models;
}

const port = process.env.PORT || 3000;
app.listen(port, () => {
  console.log(`sac-doc-generator listening on http://localhost:${port}`);
});
