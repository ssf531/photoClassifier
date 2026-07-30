// @vitest-environment jsdom
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Link, MemoryRouter, Route, Routes } from "react-router-dom";

import {
  ProgressSocketProvider,
  useProgressSocket,
} from "./ProgressSocketContext";
import type { ProgressSocket } from "./progressSocket";

function makeFakeSocket(): ProgressSocket {
  return {
    connect: vi.fn(),
    close: vi.fn(),
    subscribe: vi.fn(() => () => {}),
  } as unknown as ProgressSocket;
}

function Probe({
  label,
  onRender,
}: {
  label: string;
  onRender: (socket: ProgressSocket) => void;
}) {
  const socket = useProgressSocket();
  onRender(socket);
  return <div>{label}</div>;
}

describe("ProgressSocketProvider", () => {
  it("preserves the same socket instance across route navigation (FEAT-062)", () => {
    const fakeSocket = makeFakeSocket();
    const createSocket = vi.fn(() => fakeSocket);
    const seen: ProgressSocket[] = [];

    render(
      <ProgressSocketProvider createSocket={createSocket}>
        <MemoryRouter initialEntries={["/"]}>
          <Link to="/search">Go to search</Link>
          <Routes>
            <Route
              path="/"
              element={<Probe label="grid" onRender={(s) => seen.push(s)} />}
            />
            <Route
              path="/search"
              element={<Probe label="search" onRender={(s) => seen.push(s)} />}
            />
          </Routes>
        </MemoryRouter>
      </ProgressSocketProvider>,
    );

    fireEvent.click(screen.getByText("Go to search"));

    expect(createSocket).toHaveBeenCalledTimes(1);
    expect(seen).toEqual([fakeSocket, fakeSocket]);
    expect(fakeSocket.connect).toHaveBeenCalledTimes(1);
    expect(fakeSocket.close).not.toHaveBeenCalled();
  });

  it("throws when used outside a ProgressSocketProvider", () => {
    function Bare() {
      useProgressSocket();
      return null;
    }

    // Suppress React's expected error-boundary console noise for this case.
    const consoleError = vi
      .spyOn(console, "error")
      .mockImplementation(() => {});
    expect(() => render(<Bare />)).toThrow(
      "useProgressSocket must be used within a ProgressSocketProvider",
    );
    consoleError.mockRestore();
  });
});
