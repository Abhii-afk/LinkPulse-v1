import { useEffect, useState } from "react";

/**
 * A tiny hash router.
 *
 * The project deliberately ships without a routing dependency, so the shell
 * keeps the current view in the URL hash. That gives every view a linkable
 * address without pulling a router into the bundle.
 */

export const ROUTES = [
  { id: "links", label: "Links" },
  { id: "campaigns", label: "Campaigns" },
  { id: "import", label: "Import" },
  { id: "analytics", label: "Analytics" },
  { id: "settings", label: "Settings" },
];

export const DEFAULT_ROUTE = "links";

export function isKnownRoute(candidate) {
  return ROUTES.some((route) => route.id === candidate);
}

export function readRouteFromHash(hash) {
  const candidate = String(hash || "")
    .replace(/^#\/?/, "")
    .trim();
  return isKnownRoute(candidate) ? candidate : DEFAULT_ROUTE;
}

export function useRoute() {
  const [route, setRoute] = useState(() =>
    readRouteFromHash(typeof window === "undefined" ? "" : window.location.hash),
  );

  useEffect(() => {
    const onHashChange = () => setRoute(readRouteFromHash(window.location.hash));
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  const navigate = (next) => {
    if (!isKnownRoute(next)) {
      return;
    }
    window.location.hash = `#/${next}`;
    setRoute(next);
  };

  return { route, navigate };
}
