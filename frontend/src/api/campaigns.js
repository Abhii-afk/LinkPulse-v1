import { requestJson } from "./client.js";

export async function listCampaigns({ accessToken, fetchImpl } = {}) {
  return requestJson("/api/v1/campaigns", { accessToken, fetchImpl });
}

export async function createCampaign(
  { name, description, accessToken, fetchImpl } = {},
) {
  return requestJson("/api/v1/campaigns", {
    method: "POST",
    body: { name, description },
    accessToken,
    fetchImpl,
  });
}
