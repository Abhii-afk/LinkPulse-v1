import { describe, expect, it } from "vitest";

import App from "./App.jsx";
import AppShell from "./app/AppShell.jsx";

describe("application shell", () => {
  it("hosts the links workspace without persisting an access token", () => {
    const view = App();

    expect(view.type).toBe(AppShell);
    expect(view.props.accessToken).toBeNull();
  });

  it("passes the signed in session and the handlers to the shell", () => {
    const onSignIn = () => {};
    const onSignOut = () => {};
    const view = App({
      accessToken: "token",
      userRole: "admin",
      userEmail: "demo@example.com",
      onSignIn,
      onSignOut,
    });

    expect(view.props.accessToken).toBe("token");
    expect(view.props.userRole).toBe("admin");
    expect(view.props.userEmail).toBe("demo@example.com");
    expect(view.props.onSignIn).toBe(onSignIn);
    expect(view.props.onSignOut).toBe(onSignOut);
  });
});
