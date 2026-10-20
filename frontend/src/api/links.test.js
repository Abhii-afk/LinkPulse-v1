import { describe, expect, it, vi } from "vitest";

import { ApiError } from "./client.js";
import {
  buildCreateLinkPayload,
  createLink,
  getAliasFeedback,
  validateStepOne,
  validateStepTwo,
} from "./links.js";

const validForm = {
  destinationUrl: "https://example.com/launch",
  customAlias: "launch-2026",
  enableExpiration: true,
  // The expiry is written with an explicit UTC offset so the expectation
  // below does not depend on the time zone the tests run in.
  expiresAt: "2099-01-01T12:00:00Z",
  enableClickLimit: true,
  clickLimit: "250",
  enablePassword: true,
  password: "private-pass",
};

describe("link wizard validation and payloads", () => {
  it("gives immediate, truthful alias feedback", () => {
    expect(getAliasFeedback("").tone).toBe("neutral");
    expect(getAliasFeedback("bad alias").tone).toBe("error");
    expect(getAliasFeedback("summer-deal").tone).toBe("valid");
    expect(getAliasFeedback("summer-deal", { aliasTaken: true })).toEqual({
      tone: "error",
      message: "This alias is already in use. Choose another alias.",
    });
  });

  it("blocks invalid destination and alias values on step one", () => {
    expect(
      validateStepOne({ destinationUrl: "not-a-url", customAlias: "no spaces" }),
    ).toEqual({
      destinationUrl: "Enter a valid destination URL.",
      customAlias: "Use letters, numbers, hyphens, or underscores only.",
    });
  });

  it("blocks invalid optional rules on step two", () => {
    expect(
      validateStepTwo({
        enableExpiration: true,
        expiresAt: "2020-01-01T12:00",
        enableClickLimit: true,
        clickLimit: "0",
        enablePassword: true,
        password: "short",
      }, new Date("2026-01-01T00:00:00Z")),
    ).toEqual({
      expiresAt: "Expiration must be in the future.",
      clickLimit: "Enter a whole-number click limit of at least 1.",
      password: "Password must contain at least 8 characters.",
    });
  });

  it("omits disabled rules and keeps enabled values in the backend shape", () => {
    expect(buildCreateLinkPayload(validForm)).toEqual({
      destination_url: "https://example.com/launch",
      custom_alias: "launch-2026",
      rules: {
        expires_at: "2099-01-01T12:00:00.000Z",
        click_limit: 250,
        password: "private-pass",
      },
    });

    expect(
      buildCreateLinkPayload({
        ...validForm,
        customAlias: "",
        enableExpiration: false,
        enableClickLimit: false,
        enablePassword: false,
      }),
    ).toEqual({
      destination_url: "https://example.com/launch",
      rules: {},
    });
  });
});

describe("createLink API integration", () => {
  it("posts the real create-link request with an in-memory token", async () => {
    const fetchImpl = vi.fn(async (_url, options) => ({
      ok: true,
      status: 201,
      text: async () => JSON.stringify({ short_url: "http://testserver/launch-2026" }),
      options,
    }));

    const payload = buildCreateLinkPayload(validForm);
    const response = await createLink(payload, {
      accessToken: "test-token-kept-in-memory",
      fetchImpl,
    });

    expect(response.short_url).toBe("http://testserver/launch-2026");
    expect(fetchImpl).toHaveBeenCalledOnce();
    const [, options] = fetchImpl.mock.calls[0];
    expect(options.method).toBe("POST");
    expect(options.headers.Authorization).toBe("Bearer test-token-kept-in-memory");
    expect(JSON.parse(options.body)).toEqual(payload);
  });

  it("surfaces an alias conflict instead of reporting a fake success", async () => {
    const fetchImpl = vi.fn(async () => ({
      ok: false,
      status: 409,
      text: async () => JSON.stringify({ detail: "Alias already in use" }),
    }));

    await expect(createLink(buildCreateLinkPayload(validForm), { fetchImpl })).rejects.toMatchObject({
      name: "ApiError",
      status: 409,
      message: "Alias already in use",
    });
    expect(fetchImpl).toHaveBeenCalledOnce();
  });

  it("reports network failures as API errors", async () => {
    const fetchImpl = vi.fn(async () => {
      throw new Error("offline");
    });

    await expect(createLink(buildCreateLinkPayload(validForm), { fetchImpl })).rejects.toBeInstanceOf(ApiError);
  });
});
