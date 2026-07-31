// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "../api/client";
import { SearchPage } from "./SearchPage";

vi.mock("../api/client", () => ({
  apiClient: { GET: vi.fn(), POST: vi.fn() },
}));

window.__LAUNCH_TOKEN__ = "test-token";

const SEARCH_RESULTS = {
  items: [
    {
      id: "photo-1",
      relative_path: "beach.jpg",
      captured_at_utc: null,
      score: 1,
    },
  ],
};

// SearchResults virtualizes its list (TanStack Virtual); jsdom has no real
// layout, so without a nonzero measured viewport it renders zero rows.
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

function renderPage() {
  const client = new QueryClient();
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <SearchPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

async function runASearch(): Promise<void> {
  fireEvent.change(screen.getByLabelText("Search text"), {
    target: { value: "sunset" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Search" }));
  await waitFor(() => screen.getByRole("img", { name: "beach.jpg" }));
}

describe("SearchPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockViewportHeight(600);
  });

  it("saves the most recent search as a smart collection", async () => {
    vi.mocked(apiClient.POST).mockImplementation(async (path: string) => {
      if (path === "/api/v1/search") {
        return {
          data: SEARCH_RESULTS,
          error: undefined,
          response: new Response(),
        };
      }
      if (path === "/api/v1/collections") {
        return {
          data: {
            id: "coll-1",
            name: "Sunsets",
            type: "smart",
            created_at: "2024-01-01T00:00:00Z",
            item_count: 0,
          },
          error: undefined,
          response: new Response(),
        };
      }
      throw new Error(`unexpected POST ${path}`);
    });

    renderPage();
    await runASearch();

    fireEvent.change(screen.getByLabelText("Smart collection name"), {
      target: { value: "Sunsets" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Save as smart collection" }),
    );

    await waitFor(() => screen.getByText("Saved."));
    expect(apiClient.POST).toHaveBeenCalledWith("/api/v1/collections", {
      body: {
        name: "Sunsets",
        search_query: expect.objectContaining({ text: "sunset" }),
      },
    });
  });

  it("does not save when no name has been entered", async () => {
    vi.mocked(apiClient.POST).mockImplementation(async (path: string) => {
      if (path === "/api/v1/search") {
        return {
          data: SEARCH_RESULTS,
          error: undefined,
          response: new Response(),
        };
      }
      throw new Error(`unexpected POST ${path}`);
    });

    renderPage();
    await runASearch();

    fireEvent.click(
      screen.getByRole("button", { name: "Save as smart collection" }),
    );

    expect(apiClient.POST).toHaveBeenCalledTimes(1);
    expect(apiClient.POST).toHaveBeenCalledWith(
      "/api/v1/search",
      expect.anything(),
    );
  });
});
