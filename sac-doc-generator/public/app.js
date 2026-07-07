const form = document.getElementById("analyze-form");
const liveFields = document.getElementById("live-fields");
const statusEl = document.getElementById("status");
const reportSection = document.getElementById("report");
const reportContent = document.getElementById("report-content");
const analyzeBtn = document.getElementById("analyze-btn");
const downloadBtn = document.getElementById("download-md");

let lastMarkdown = "";

document.querySelectorAll('input[name="mode"]').forEach((radio) => {
  radio.addEventListener("change", (event) => {
    liveFields.hidden = event.target.value !== "live";
  });
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  statusEl.textContent = "";
  reportSection.hidden = true;

  const formData = new FormData(form);
  const mode = formData.get("mode");
  const payload = {
    mode,
    tenantBaseUrl: formData.get("tenantBaseUrl"),
    tokenUrl: formData.get("tokenUrl"),
    clientId: formData.get("clientId"),
    clientSecret: formData.get("clientSecret"),
  };

  analyzeBtn.disabled = true;
  analyzeBtn.textContent = "Analisando...";
  statusEl.style.color = "#666";
  statusEl.textContent = "Conectando e coletando metadados...";

  try {
    const response = await fetch("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await response.json();

    if (!response.ok) {
      throw new Error(data.error || "Falha ao gerar o relatório.");
    }

    lastMarkdown = data.markdown;
    reportContent.innerHTML = data.html;
    reportSection.hidden = false;
    statusEl.style.color = "#0a7a3d";
    statusEl.textContent = `Relatório gerado com sucesso (${data.models.length} modelo(s)).`;
  } catch (err) {
    statusEl.style.color = "#b00";
    statusEl.textContent = err.message;
  } finally {
    analyzeBtn.disabled = false;
    analyzeBtn.textContent = "Gerar documentação";
  }
});

downloadBtn.addEventListener("click", () => {
  const blob = new Blob([lastMarkdown], { type: "text/markdown" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "sac-documentacao.md";
  a.click();
  URL.revokeObjectURL(url);
});
