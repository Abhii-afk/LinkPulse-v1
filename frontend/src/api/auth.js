import { requestJson } from "./client.js";

export async function signIn({ email, password, fetchImpl } = {}) {
  const payload = await requestJson("/api/v1/auth/login", {
    method: "POST",
    body: { email, password },
    fetchImpl,
  });

  return {
    accessToken: payload.access_token || null,
    role: payload.user?.role || null,
    email: payload.user?.email || null,
  };
}
