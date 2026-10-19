import { describe, expect, it } from "vitest";

import App from "./App.jsx";
import LinksPage from "./pages/LinksPage.jsx";

describe("application shell", () => {
  it("hosts the links workspace without persisting an access token", () => {
    const view = App();

    expect(view.type).toBe(LinksPage);
    expect(view.props.accessToken).toBeNull();
  });
});
