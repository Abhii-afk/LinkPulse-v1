import { describe, expect, it, vi } from "vitest";

import { ApiError } from "./client.js";
import { signIn } from "./auth.js";

describe("sign in", () => {
  it("posts the credentials and returns the session", async () => {
    const fetchImpl = vi.fn(async (_url, options) => ({
      ok: true,
      status: 200,
      text: async () =>
        JSON.stringify({
          access_token: "token-kept-in-memory",
          token_type: "bearer",
          user: { id: "1", email: "demo@linkpulse.local", role: "user" },
        }),
      options,
    }));

    const session = await signIn({
      email: "demo@linkpulse.local",
      password: "demo-password-123",
      fetchImpl,
    });

    expect(session).toEqual({
      accessToken: "token-kept-in-memory",
      role: "user",
      email: "demo@linkpulse.local",
    });

    const [, options] = fetchImpl.mock.calls[0];
    expect(options.method).toBe("POST");
    expect(JSON.parse(options.body)).toEqual({
      email: "demo@linkpulse.local",
      password: "demo-password-123",
    });
  });

  it("reports rejected credentials instead of pretending to be signed in", async () => {
    const fetchImpl = vi.fn(async () => ({
      ok: false,
      status: 401,
      text: async () => JSON.stringify({ detail: "Incorrect email or password" }),
    }));

    await expect(
      signIn({ email: "demo@linkpulse.local", password: "wrong", fetchImpl }),
    ).rejects.toMatchObject({ name: "ApiError", status: 401 });
  });

  it("surfaces an unreachable API as an API error", async () => {
    const fetchImpl = vi.fn(async () => {
      throw new Error("offline");
    });

    await expect(
      signIn({ email: "demo@linkpulse.local", password: "demo-password-123", fetchImpl }),
    ).rejects.toBeInstanceOf(ApiError);
  });
});
