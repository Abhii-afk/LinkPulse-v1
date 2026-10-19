import { requestJson } from "./client.js";

export const ALIAS_PATTERN = /^[A-Za-z0-9][A-Za-z0-9_-]*$/;

export function getAliasFeedback(alias, { aliasTaken = false } = {}) {
  const value = alias.trim();

  if (aliasTaken) {
    return {
      tone: "error",
      message: "This alias is already in use. Choose another alias.",
    };
  }

  if (!value) {
    return {
      tone: "neutral",
      message: "Leave this blank to let LinkPulse generate an alias.",
    };
  }

  if (value.length < 3 || value.length > 100) {
    return {
      tone: "error",
      message: "Use between 3 and 100 characters.",
    };
  }

  if (!ALIAS_PATTERN.test(value)) {
    return {
      tone: "error",
      message: "Use letters, numbers, hyphens, or underscores only.",
    };
  }

  return {
    tone: "valid",
    message: "Alias format is valid. The server will confirm availability when you save.",
  };
}

export function validateStepOne(form) {
  const errors = {};
  const destination = form.destinationUrl.trim();

  if (!destination) {
    errors.destinationUrl = "Enter a destination URL.";
  } else {
    try {
      const parsed = new URL(destination);
      if (!/^https?:$/.test(parsed.protocol)) {
        errors.destinationUrl = "Use an http or https URL.";
      }
    } catch {
      errors.destinationUrl = "Enter a valid destination URL.";
    }
  }

  const aliasFeedback = getAliasFeedback(form.customAlias);
  if (aliasFeedback.tone === "error") {
    errors.customAlias = aliasFeedback.message;
  }

  return errors;
}

function toIsoDate(value) {
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? null : parsed.toISOString();
}

export function validateStepTwo(form, now = new Date()) {
  const errors = {};

  if (form.enableExpiration) {
    const expiration = new Date(form.expiresAt);
    if (!form.expiresAt || Number.isNaN(expiration.getTime())) {
      errors.expiresAt = "Choose a valid expiration date and time.";
    } else if (expiration <= now) {
      errors.expiresAt = "Expiration must be in the future.";
    }
  }

  if (form.enableClickLimit) {
    const limit = Number(form.clickLimit);
    if (!Number.isInteger(limit) || limit < 1) {
      errors.clickLimit = "Enter a whole-number click limit of at least 1.";
    }
  }

  if (form.enablePassword && form.password.length < 8) {
    errors.password = "Password must contain at least 8 characters.";
  }

  return errors;
}

export function buildCreateLinkPayload(form) {
  const rules = {};
  const alias = form.customAlias.trim();

  if (form.enableExpiration && form.expiresAt) {
    rules.expires_at = toIsoDate(form.expiresAt);
  }
  if (form.enableClickLimit && form.clickLimit !== "") {
    rules.click_limit = Number(form.clickLimit);
  }
  if (form.enablePassword && form.password) {
    rules.password = form.password;
  }

  return {
    destination_url: form.destinationUrl.trim(),
    ...(alias ? { custom_alias: alias } : {}),
    rules,
  };
}

export async function createLink(payload, { accessToken, fetchImpl } = {}) {
  return requestJson("/api/v1/links", {
    method: "POST",
    body: payload,
    accessToken,
    fetchImpl,
  });
}
