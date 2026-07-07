import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { XMLParser } from "fast-xml-parser";

const FIXTURE_PATH = fileURLToPath(new URL("./fixtures/sample-models.json", import.meta.url));

/** Loads the bundled sample models, used by the UI's "demo mode" (no live tenant needed). */
export async function loadFixtureModels() {
  const raw = await readFile(FIXTURE_PATH, "utf-8");
  return JSON.parse(raw);
}

/**
 * Talks to the SAC Data Export (OData) API to discover models and their metadata.
 *
 * The provider catalog path below is documented by SAP's export-api samples. The
 * per-model $metadata path is generated per tenant (SAC exposes a tenant-specific
 * OpenAPI/EDMX document under Administration > App Integration) — verify it against
 * your tenant's own spec if it doesn't match. This client isolates that lookup here
 * so it's a one-file change if your tenant uses a different path.
 */
const xmlParser = new XMLParser({ ignoreAttributes: false, attributeNamePrefix: "@_" });

export async function listProviders({ baseUrl, accessToken }) {
  const url = `${trimSlash(baseUrl)}/dataexport/administration/Namespaces(NamespaceID='sac')/Providers/`;
  const res = await authedJsonFetch(url, accessToken);
  const entries = res?.d?.results ?? res?.value ?? [];
  return entries.map((entry) => ({
    id: entry.ProviderID ?? entry.id,
    name: entry.ProviderDescription ?? entry.name ?? entry.ProviderID,
    type: entry.ProviderType ?? "Unknown",
  }));
}

export async function fetchModelMetadata({ baseUrl, accessToken, providerId }) {
  const url = `${trimSlash(baseUrl)}/dataexport/providers/${encodeURIComponent(providerId)}/$metadata`;
  const response = await fetch(url, {
    headers: { Authorization: `Bearer ${accessToken}`, Accept: "application/xml" },
  });
  if (!response.ok) {
    throw new Error(
      `Metadata fetch failed for provider "${providerId}" (${response.status} ${response.statusText}). ` +
        `Verify the $metadata path against your tenant's own API spec (Administration > App Integration).`
    );
  }
  const xml = await response.text();
  return parseEdmxToModel(xml, providerId);
}

/** Converts a raw EDMX metadata document into the normalized model shape the evaluator expects. */
export function parseEdmxToModel(edmxXml, providerId) {
  const doc = xmlParser.parse(edmxXml);
  const schema = doc?.["edmx:Edmx"]?.["edmx:DataServices"]?.Schema;
  const entityType = Array.isArray(schema?.EntityType) ? schema.EntityType[0] : schema?.EntityType;
  const properties = toArray(entityType?.Property);

  const dimensions = [];
  const measures = [];

  for (const prop of properties) {
    const name = prop["@_Name"];
    const semantics = prop["@_sap:semantics"] ?? prop["@_semantics"] ?? "";
    const description = prop["@_sap:label"] ?? prop["@_label"] ?? "";
    const field = {
      id: name,
      name,
      description,
      dataType: prop["@_Type"] ?? "Unknown",
    };
    if (/amount|quantity|measure/i.test(semantics) || /Decimal|Int/.test(field.dataType)) {
      measures.push({ ...field, unitType: prop["@_sap:unit"] ?? null, currencyConversion: null });
    } else {
      dimensions.push({
        ...field,
        isPublic: false,
        hasHierarchy: false,
        hierarchyCount: 0,
        memberCount: null,
      });
    }
  }

  return {
    id: providerId,
    name: entityType?.["@_Name"] ?? providerId,
    description: "",
    type: "Analytic",
    dimensions,
    measures,
  };
}

async function authedJsonFetch(url, accessToken) {
  const response = await fetch(url, {
    headers: { Authorization: `Bearer ${accessToken}`, Accept: "application/json" },
  });
  if (!response.ok) {
    const body = await response.text().catch(() => "");
    throw new Error(`Request to ${url} failed (${response.status}): ${body.slice(0, 500)}`);
  }
  return response.json();
}

function toArray(value) {
  if (value == null) return [];
  return Array.isArray(value) ? value : [value];
}

function trimSlash(url) {
  return url.replace(/\/+$/, "");
}
