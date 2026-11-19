// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

import { createDemoAuth } from "./auth";
import type { KeyValueStore } from "./auth";
import { LoginPage } from "./LoginPage";
import { MyTrips } from "./MyTrips";
import { createDemoSavedTrips } from "./savedTrips";
import type { Itinerary } from "./types";

afterEach(cleanup);

function memoryStore(): KeyValueStore {
  const data = new Map<string, string>();
  return { getItem: (k) => data.get(k) ?? null, setItem: (k, v) => void data.set(k, v), removeItem: (k) => void data.delete(k) };
}

function type(label: RegExp, value: string) {
  fireEvent.change(screen.getByLabelText(label), { target: { value } });
}

describe("LoginPage", () => {
  it("creates an account and reports the new user", async () => {
    const onLoggedIn = vi.fn();
    render(<LoginPage onLoggedIn={onLoggedIn} onCancel={() => {}} client={createDemoAuth(memoryStore())} />);
    fireEvent.click(screen.getByRole("button", { name: "Create an account" }));
    expect(screen.getByRole("heading", { name: "Create your account" })).toBeTruthy();
    type(/^Name$/, "Ana");
    type(/^Email$/, "ana@example.com");
    type(/^Password$/, "correct horse");
    fireEvent.click(screen.getByRole("button", { name: "Create account" }));
    await waitFor(() => expect(onLoggedIn).toHaveBeenCalledWith(expect.objectContaining({ name: "Ana" })));
  });

  it("shows a problem on the field it belongs to", async () => {
    render(<LoginPage onLoggedIn={() => {}} onCancel={() => {}} client={createDemoAuth(memoryStore())} />);
    type(/^Email$/, "ana@");
    type(/^Password$/, "whatever");
    fireEvent.click(screen.getByRole("button", { name: "Log in" }));
    const message = await screen.findByRole("alert");
    expect(message.textContent).toMatch(/name@example\.com/);
    expect(screen.getByLabelText(/^Email$/).getAttribute("aria-invalid")).toBe("true");
    expect(document.activeElement).toBe(screen.getByLabelText(/^Email$/));
  });

  it("says a wrong password doesn't match an account", async () => {
    const client = createDemoAuth(memoryStore());
    await client.signUp({ name: "Ana", email: "ana@example.com", password: "correct horse" });
    await client.logOut();
    render(<LoginPage onLoggedIn={() => {}} onCancel={() => {}} client={client} />);
    type(/^Email$/, "ana@example.com");
    type(/^Password$/, "wrong password");
    fireEvent.click(screen.getByRole("button", { name: "Log in" }));
    expect((await screen.findByRole("alert")).textContent).toBe("That email and password don't match an account.");
  });

  it("can show the password while typing", () => {
    render(<LoginPage onLoggedIn={() => {}} onCancel={() => {}} client={createDemoAuth(memoryStore())} />);
    const input = screen.getByLabelText(/^Password$/);
    expect(input.getAttribute("type")).toBe("password");
    fireEvent.click(screen.getByRole("button", { name: "Show password" }));
    expect(input.getAttribute("type")).toBe("text");
  });

  it("says demo accounts stay in this browser", () => {
    render(<LoginPage onLoggedIn={() => {}} onCancel={() => {}} client={createDemoAuth(memoryStore())} />);
    expect(screen.getByText(/kept in this browser only/)).toBeTruthy();
  });
});

describe("MyTrips", () => {
  const user = { id: "u1", name: "Ana", email: "ana@example.com" };
  const rome: Itinerary = {
    trip_id: "t1",
    destination: { name: "Rome", lat: 0, lon: 0 },
    start_date: "2030-05-01",
    end_date: "2030-05-03",
    days: [1, 2, 3].map((d) => ({ date: `2030-05-0${d}`, items: [] })),
    totals: { cost: 0, currency: "EUR", walking_minutes: 0 },
  };

  it("lists saved trips and opens one", async () => {
    const client = createDemoSavedTrips(memoryStore());
    await client.save(user, rome, null);
    const onOpen = vi.fn();
    render(<MyTrips user={user} onOpen={onOpen} onPlanNew={() => {}} client={client} />);
    expect(await screen.findByRole("heading", { name: "Rome" })).toBeTruthy();
    expect(screen.getByText(/3 days/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Open Rome trip" }));
    expect(onOpen).toHaveBeenCalledWith(expect.objectContaining({ trip_id: "t1" }));
  });

  it("removes a trip from the list", async () => {
    const client = createDemoSavedTrips(memoryStore());
    await client.save(user, rome, null);
    render(<MyTrips user={user} onOpen={() => {}} onPlanNew={() => {}} client={client} />);
    fireEvent.click(await screen.findByRole("button", { name: "Remove Rome trip from My trips" }));
    expect(await screen.findByText(/No saved trips yet/)).toBeTruthy();
  });

  it("explains how to save when there are no trips", async () => {
    render(<MyTrips user={user} onOpen={() => {}} onPlanNew={() => {}} client={createDemoSavedTrips(memoryStore())} />);
    expect(await screen.findByText(/No saved trips yet/)).toBeTruthy();
  });
});
