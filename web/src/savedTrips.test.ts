// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";

import type { AuthClient, KeyValueStore, User } from "./auth";
import { createDemoSavedTrips, createServerSavedTrips } from "./savedTrips";
import type { Itinerary } from "./types";

function memoryStore(): KeyValueStore {
  const data = new Map<string, string>();
  return { getItem: (k) => data.get(k) ?? null, setItem: (k, v) => void data.set(k, v), removeItem: (k) => void data.delete(k) };
}

function plan(id: string, city: string): Itinerary {
  return {
    trip_id: id,
    destination: { name: city, lat: 0, lon: 0 },
    start_date: "2030-05-01",
    end_date: "2030-05-02",
    days: [
      { date: "2030-05-01", items: [] },
      { date: "2030-05-02", items: [] },
    ],
    totals: { cost: 0, currency: "EUR", walking_minutes: 0 },
  };
}

const ana: User = { id: "u1", name: "Ana", email: "ana@example.com" };
const bo: User = { id: "u2", name: "Bo", email: "bo@example.com" };

afterEach(() => vi.unstubAllGlobals());

describe("demo saved trips", () => {
  it("keeps each person's trips separate, newest first", async () => {
    const client = createDemoSavedTrips(memoryStore());
    await client.save(ana, plan("t1", "Rome"), null);
    await new Promise((r) => setTimeout(r, 2));
    await client.save(ana, plan("t2", "Lisbon"), null);
    await client.save(bo, plan("t3", "Tokyo"), null);

    expect((await client.list(ana)).map((t) => t.destination)).toEqual(["Lisbon", "Rome"]);
    expect((await client.list(bo)).map((t) => t.trip_id)).toEqual(["t3"]);
    expect((await client.list(ana))[0]).toMatchObject({ days: 2, start_date: "2030-05-01" });
  });

  it("saving the same trip again updates it instead of adding a copy", async () => {
    const client = createDemoSavedTrips(memoryStore());
    await client.save(ana, plan("t1", "Rome"), null);
    await client.save(ana, plan("t1", "Rome"), null);
    expect(await client.list(ana)).toHaveLength(1);
  });

  it("removes a trip from the list", async () => {
    const client = createDemoSavedTrips(memoryStore());
    await client.save(ana, plan("t1", "Rome"), null);
    await client.remove(ana, "t1");
    expect(await client.list(ana)).toEqual([]);
  });
});

describe("server saved trips", () => {
  it("calls /me/trips with the user's token", async () => {
    const authClient = { authHeaders: () => ({ Authorization: "Bearer tok" }) } as unknown as AuthClient;
    const calls: [string, string | undefined][] = [];
    vi.stubGlobal("fetch", async (url: string, init?: RequestInit) => {
      calls.push([url, init?.method]);
      expect((init?.headers as Record<string, string>).Authorization).toBe("Bearer tok");
      if (init?.method === "PUT") return Response.json({ trip_id: "t1" });
      if (init?.method === "DELETE") return new Response(null, { status: 204 });
      return Response.json([]);
    });
    const client = createServerSavedTrips(authClient, "http://api");
    await client.list(ana);
    await client.save(ana, plan("t1", "Rome"), null);
    await client.remove(ana, "t1");
    expect(calls).toEqual([
      ["http://api/me/trips", undefined],
      ["http://api/me/trips/t1", "PUT"],
      ["http://api/me/trips/t1", "DELETE"],
    ]);
  });

  it("says when the session has ended", async () => {
    vi.stubGlobal("fetch", async () => new Response(null, { status: 401 }));
    const client = createServerSavedTrips({ authHeaders: () => ({}) } as unknown as AuthClient, "http://api");
    await expect(client.list(ana)).rejects.toThrow(/Log in again/);
  });
});
