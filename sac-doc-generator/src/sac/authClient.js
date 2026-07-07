/**
 * OAuth2 "client credentials" (two-legged) token exchange, as documented by SAP for
 * SAC's App Integration OAuth clients. The token URL, client id and secret are
 * tenant-specific and generated under Administration > App Integration > OAuth Clients
 * in the target SAC tenant — they must be provided by the caller, never hardcoded.
 */
export async function fetchAccessToken({ tokenUrl, clientId, clientSecret }) {
  if (!tokenUrl || !clientId || !clientSecret) {
    throw new Error("tokenUrl, clientId and clientSecret are required");
  }

  const basicAuth = Buffer.from(`${clientId}:${clientSecret}`).toString("base64");

  const response = await fetch(tokenUrl, {
    method: "POST",
    headers: {
      "Content-Type": "application/x-www-form-urlencoded",
      Authorization: `Basic ${basicAuth}`,
    },
    body: new URLSearchParams({ grant_type: "client_credentials" }),
  });

  if (!response.ok) {
    const body = await response.text().catch(() => "");
    throw new Error(
      `Token exchange failed (${response.status} ${response.statusText}): ${body.slice(0, 500)}`
    );
  }

  const json = await response.json();
  if (!json.access_token) {
    throw new Error("Token endpoint did not return an access_token");
  }

  return {
    accessToken: json.access_token,
    expiresIn: json.expires_in ?? null,
    tokenType: json.token_type ?? "Bearer",
  };
}
