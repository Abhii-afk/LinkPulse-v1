import { describe, expect, it } from "vitest";

import App from "./App.jsx";

describe("foundation app shell", () => {
  it("renders the LinkPulse foundation message", () => {
    const view = App();
    const text = view.props.children
      .map((child) => child.props.children)
      .join(" ");

    expect(view.type).toBe("main");
    expect(text).toContain("LinkPulse");
    expect(text).toContain("Foundation ready");
  });
});
