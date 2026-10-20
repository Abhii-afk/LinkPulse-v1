import { describe, expect, it } from "vitest";

import AppShell from "./AppShell.jsx";
import LinksPage from "../pages/LinksPage.jsx";
import { DEFAULT_ROUTE, ROUTES, readRouteFromHash } from "./useRoute.js";

function findChildren(node, type) {
  const found = [];
  const walk = (current) => {
    if (!current || typeof current !== "object") {
      return;
    }
    if (Array.isArray(current)) {
      current.forEach(walk);
      return;
    }
    if (current.type === type) {
      found.push(current);
    }
    if (current.props && current.props.children) {
      walk(current.props.children);
    }
  };
  walk(node);
  return found;
}

describe("the workspace shell", () => {
  it("offers a section for every part of the workspace", () => {
    expect(ROUTES.map((route) => route.id)).toEqual([
      "links",
      "campaigns",
      "import",
      "analytics",
      "settings",
    ]);
  });

  it("reads a known route from the hash and falls back to the links", () => {
    expect(readRouteFromHash("#/campaigns")).toBe("campaigns");
    expect(readRouteFromHash("#/import")).toBe("import");
    expect(readRouteFromHash("#/nonsense")).toBe(DEFAULT_ROUTE);
    expect(readRouteFromHash("")).toBe(DEFAULT_ROUTE);
  });

  it("renders the navigation for every section", () => {
    const view = AppShell({ route: "links" });
    const nav = findChildren(view, "nav");

    expect(nav).toHaveLength(1);
    const buttons = findChildren(nav[0], "button");
    expect(buttons.map((button) => button.props.children)).toEqual(
      ROUTES.map((route) => route.label),
    );
  });

  it("marks the current section as the active one", () => {
    const view = AppShell({ route: "analytics" });
    const nav = findChildren(view, "nav")[0];
    const buttons = findChildren(nav, "button");

    const active = buttons.filter((button) => button.props.className.includes("is-active"));
    expect(active).toHaveLength(1);
    expect(active[0].props.children).toBe("Analytics");
  });

  it("renders the page for the current section", () => {
    const view = AppShell({ route: "links", accessToken: null });
    const pages = findChildren(view, LinksPage);

    expect(pages).toHaveLength(1);
    expect(pages[0].props.accessToken).toBeNull();
  });

  it("shows the sign in form when there is no session", () => {
    const view = AppShell({ route: "links", accessToken: null });
    const text = JSON.stringify(view.props.children);

    expect(text).toContain("Sign in to publish");
  });
});
