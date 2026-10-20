import { describe, expect, it } from "vitest";

import App from "./App.jsx";
import LinksPage from "./pages/LinksPage.jsx";

describe("application shell", () => {
  it("hosts the links workspace without persisting an access token", () => {
    const view = App();

    expect(view.type).toBe(LinksPage);
    expect(view.props.accessToken).toBeNull();
  });

  it("passes the signed in session and the sign in handlers to the workspace", () => {
    const onSignIn = () => {};
    const onSignOut = () => {};
    const view = App({ accessToken: "token", userRole: "admin", onSignIn, onSignOut });

    expect(view.props.accessToken).toBe("token");
    expect(view.props.userRole).toBe("admin");
    expect(view.props.onSignIn).toBe(onSignIn);
    expect(view.props.onSignOut).toBe(onSignOut);
  });
});
