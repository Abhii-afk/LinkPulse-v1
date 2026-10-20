const DEFAULT_API_BASE_URL = "http://127.0.0.1:8000";

export const API_BASE_URL = (
  import.meta.env.VITE_API_BASE_URL || DEFAULT_API_BASE_URL
).replace(/\/$/, "");

export class ApiError extends Error {
  constructor(message, { status = 0, details = null } = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.details = details;
  }
}

function getErrorMessage(payload, status) {
  if (payload && typeof payload.detail === "string") {
    return payload.detail;
  }

  if (Array.isArray(payload?.detail)) {
    return payload.detail
      .map((item) => item?.msg)
      .filter(Boolean)
      .join("; ");
  }

  return `The request could not be completed (${status}).`;
}

async function readPayload(response) {
  const text = await response.text();
  if (!text) {
    return null;
  }

  try {
    return JSON.parse(text);
  } catch {
    return { detail: text };
  }
}

export async function requestJson(
  path,
  { method = "GET", body, accessToken, fetchImpl = globalThis.fetch } = {},
) {
  if (typeof fetchImpl !== "function") {
    throw new ApiError("Network requests are unavailable in this browser.");
  }

  const headers = { Accept: "application/json" };
  if (body !== undefined) {
    headers["Content-Type"] = "application/json";
  }
  if (accessToken) {
    headers.Authorization = `Bearer ${accessToken}`;
  }

  let response;
  try {
    response = await fetchImpl(`${API_BASE_URL}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(
      "LinkPulse could not reach the API. Check that the backend is running.",
    );
  }

  const payload = await readPayload(response);
  if (!response.ok) {
    throw new ApiError(getErrorMessage(payload, response.status), {
      status: response.status,
      details: payload,
    });
  }

  return payload;
}

export async function requestBlob(
  path,
  { accessToken, fetchImpl = globalThis.fetch } = {},
) {
  if (typeof fetchImpl !== "function") {
    throw new ApiError("Network requests are unavailable in this browser.");
  }

  const headers = { Accept: "image/png" };
  if (accessToken) {
    headers.Authorization = `Bearer ${accessToken}`;
  }

  let response;
  try {
    response = await fetchImpl(`${API_BASE_URL}${path}`, { method: "GET", headers });
  } catch {
    throw new ApiError(
      "LinkPulse could not reach the API. Check that the backend is running.",
    );
  }

  if (!response.ok) {
    const payload = await readPayload(response);
    throw new ApiError(getErrorMessage(payload, response.status), {
      status: response.status,
      details: payload,
    });
  }

  return response.blob();
}

export async function requestMultipart(
  path,
  { formData, accessToken, fetchImpl = globalThis.fetch } = {},
) {
  if (typeof fetchImpl !== "function") {
    throw new ApiError("Network requests are unavailable in this browser.");
  }

  const headers = {};
  if (accessToken) {
    headers.Authorization = `Bearer ${accessToken}`;
  }

  let response;
  try {
    response = await fetchImpl(`${API_BASE_URL}${path}`, {
      method: "POST",
      headers,
      body: formData,
    });
  } catch {
    throw new ApiError(
      "LinkPulse could not reach the API. Check that the backend is running.",
    );
  }

  const payload = await readPayload(response);
  if (!response.ok) {
    throw new ApiError(getErrorMessage(payload, response.status), {
      status: response.status,
      details: payload,
    });
  }

  return payload;
}
