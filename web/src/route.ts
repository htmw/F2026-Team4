// The few pages of the app, kept in the URL hash (#/login, #/trips) so links, the Back
// button and refresh work on any static host without server rewrites.

import { useEffect, useState } from "react";

export type Route =
  | { page: "plan" }
  | { page: "login"; next: "save" | null }
  | { page: "trips" };

export function parseRoute(hash: string): Route {
  const [path, query = ""] = hash.replace(/^#/, "").split("?");
  const parts = path.split("/").filter(Boolean);
  if (parts[0] === "login") {
    return { page: "login", next: new URLSearchParams(query).get("next") === "save" ? "save" : null };
  }
  if (parts[0] === "trips") return { page: "trips" };
  return { page: "plan" };
}

export function routeHash(route: Route): string {
  switch (route.page) {
    case "login":
      return route.next ? `#/login?next=${route.next}` : "#/login";
    case "trips":
      return "#/trips";
    default:
      return "#/";
  }
}

export function navigate(route: Route) {
  window.location.hash = routeHash(route);
}

export function useRoute(): Route {
  const [route, setRoute] = useState(() => parseRoute(window.location.hash));
  useEffect(() => {
    const update = () => setRoute(parseRoute(window.location.hash));
    window.addEventListener("hashchange", update);
    return () => window.removeEventListener("hashchange", update);
  }, []);
  return route;
}
