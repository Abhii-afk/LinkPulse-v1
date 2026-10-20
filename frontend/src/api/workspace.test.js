import { describe, expect, it, vi } from "vitest";

import { ApiError } from "./client.js";
import {
  buildCreateLinkPayload,
  createLink,
  fetchQrCode,
  importLinksFromCsv,
  listLinks,
} from "./links.js";

const validForm = {
  destinationUrl: "https://example.com/launch",
  customAlias: "launch-2026",
  campaignId: "",
  enableExpiration: true,
  expiresAt: "2099-01-01T12:00:00Z",
  enableClickLimit: true,
  clickLimit: "250",
  enablePassword: true,
  password: "private-pass",
};

describe("the workspace api", () => {
  it("sends the campaign with the link when one is chosen", () => {
    const payload = buildCreateLinkPayload({
      ...validForm,
      campaignId: "6f1b0e2a-0c1e-4a6f-9a2f-2f6d1b4c8a91",
    });

    expect(payload.campaign_id).toBe("6f1b0e2a-0c1e-4a6f-9a2f-2f6d1b4c8a91");
  });

  it("leaves the campaign out when none is chosen", () => {
    const payload = buildCreateLinkPayload(validForm);

    expect("campaign_id" in payload).toBe(false);
  });

  it("lists the links the account owns", async () => {
    const fetchImpl = vi.fn(async () => ({
      ok: true,
      status: 200,
      text: async () => JSON.stringify([{ short_code: "demo-launch" }]),
    }));

    const links = await listLinks({ accessToken: "token", fetchImpl });

    expect(links).toEqual([{ short_code: "demo-launch" }]);
    const [url, options] = fetchImpl.mock.calls[0];
    expect(url).toContain("/api/v1/links");
    expect(options.headers.Authorization).toBe("Bearer token");
  });

  it("fetches the QR code as an image", async () => {
    const blob = { size: 12 };
    const fetchImpl = vi.fn(async () => ({
      ok: true,
      status: 200,
      blob: async () => blob,
    }));

    const result = await fetchQrCode("demo-launch", { accessToken: "token", fetchImpl });

    expect(result).toBe(blob);
    const [url, options] = fetchImpl.mock.calls[0];
    expect(url).toContain("/api/v1/links/demo-launch/qr");
    expect(options.headers.Authorization).toBe("Bearer token");
  });

  it("uploads the CSV as multipart form data", async () => {
    const fetchImpl = vi.fn(async () => ({
      ok: true,
      status: 200,
      text: async () => JSON.stringify({ total_processed: 1, successful_imports: 1, failed_imports: 0, errors: [] }),
    }));

    const file = new File(["destination_url\n"], "links.csv", { type: "text/csv" });
    const result = await importLinksFromCsv({ file, accessToken: "token", fetchImpl });

    expect(result.successful_imports).toBe(1);
    const [url, options] = fetchImpl.mock.calls[0];
    expect(url).toContain("/api/v1/links/bulk");
    expect(options.body).toBeInstanceOf(FormData);
    expect(options.body.get("file")).toBe(file);
  });

  it("reports a rejected import instead of pretending it worked", async () => {
    const fetchImpl = vi.fn(async () => ({
      ok: false,
      status: 400,
      text: async () => JSON.stringify({ detail: "CSV must include a 'destination_url' column" }),
    }));

    await expect(
      importLinksFromCsv({ file: new File(["x"], "links.csv"), accessToken: "token", fetchImpl }),
    ).rejects.toMatchObject({ name: "ApiError", status: 400 });
  });

  it("reports a missing QR code as an API error", async () => {
    const fetchImpl = vi.fn(async () => ({
      ok: false,
      status: 404,
      text: async () => JSON.stringify({ detail: "Link not found" }),
    }));

    await expect(
      fetchQrCode("missing", { accessToken: "token", fetchImpl }),
    ).rejects.toBeInstanceOf(ApiError);
  });
});
