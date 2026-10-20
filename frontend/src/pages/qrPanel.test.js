import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

/**
 * The QR code panel fetches a protected endpoint, so the request has to
 * carry the session token. The panel is a hook driven component, which the
 * unit tests cannot render, so the wiring is pinned here instead.
 */
describe("the QR code panel", () => {
  it("asks for the QR code with the session token", () => {
    const source = readFileSync(new URL("../pages/LinksPage.jsx", import.meta.url), "utf8");

    expect(source).toContain("fetchQrCode(link.short_code, { accessToken })");
  });

  it("is given the token by the page that owns the session", () => {
    const source = readFileSync(new URL("../pages/LinksPage.jsx", import.meta.url), "utf8");

    expect(source).toContain("<QrCodePanel link={qrLink} accessToken={accessToken}");
  });
});
