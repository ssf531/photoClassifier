// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";

import type { SearchResultItem } from "../api/hooks";
import { SearchResults } from "./SearchResults";

window.__LAUNCH_TOKEN__ = "test-token";

function mockViewportHeight(px: number): void {
  class StubResizeObserver {
    observe(): void {}
    unobserve(): void {}
    disconnect(): void {}
  }
  vi.stubGlobal("ResizeObserver", StubResizeObserver);

  Object.defineProperty(HTMLElement.prototype, "offsetHeight", {
    configurable: true,
    value: px,
  });
  Object.defineProperty(HTMLElement.prototype, "offsetWidth", {
    configurable: true,
    value: 800,
  });
}

describe("SearchResults", () => {
  it("renders results in the exact rank order it was given, never re-sorted", () => {
    mockViewportHeight(600);

    // Deliberately scrambled: descending score, but NOT ascending/matching
    // id or relative_path order -- if this component (or PhotoGrid) ever
    // sorted by id/name, this test would catch it.
    const results: SearchResultItem[] = [
      {
        id: "photo-zebra",
        relative_path: "zebra.jpg",
        captured_at_utc: null,
        score: 0.95,
      },
      {
        id: "photo-apple",
        relative_path: "apple.jpg",
        captured_at_utc: null,
        score: 0.8,
      },
      {
        id: "photo-mango",
        relative_path: "mango.jpg",
        captured_at_utc: null,
        score: 0.3,
      },
    ];

    render(
      <MemoryRouter>
        <SearchResults results={results} />
      </MemoryRouter>,
    );

    const renderedOrder = screen
      .getAllByRole("img")
      .map((img) => img.getAttribute("alt"));
    expect(renderedOrder).toEqual(["zebra.jpg", "apple.jpg", "mango.jpg"]);
  });
});
