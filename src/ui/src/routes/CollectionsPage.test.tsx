// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "../api/client";
import { CollectionsPage } from "./CollectionsPage";

vi.mock("../api/client", () => ({
  apiClient: { GET: vi.fn(), POST: vi.fn() },
}));

window.__LAUNCH_TOKEN__ = "test-token";

const COLLECTIONS = {
  items: [
    {
      id: "coll-1",
      name: "Trip",
      type: "virtual",
      created_at: "2024-01-01T00:00:00Z",
      item_count: 2,
    },
  ],
};

const MEMBERS = { photo_ids: ["photo-1", "photo-2"], next_offset: null };

const BUILTIN_FILTERS = {
  items: [
    {
      key: "screenshots",
      label: "Screenshots",
      search_query: { text: "screenshot", mode: "text" },
    },
  ],
};

function mockGet(): void {
  vi.mocked(apiClient.GET).mockImplementation(async (path: string) => {
    if (path === "/api/v1/collections") {
      return { data: COLLECTIONS, error: undefined, response: new Response() };
    }
    if (path === "/api/v1/collections/{collection_id}/members") {
      return { data: MEMBERS, error: undefined, response: new Response() };
    }
    if (path === "/api/v1/builtin-filters") {
      return {
        data: BUILTIN_FILTERS,
        error: undefined,
        response: new Response(),
      };
    }
    throw new Error(`unexpected GET ${path}`);
  });
}

function renderPage() {
  const client = new QueryClient();
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <CollectionsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("CollectionsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("lists existing collections with their item counts", async () => {
    mockGet();

    renderPage();

    await waitFor(() => screen.getByText("Trip"));
    expect(screen.getByText("(2 photos)")).toBeTruthy();
  });

  it("creates a new collection from the name field", async () => {
    mockGet();
    vi.mocked(apiClient.POST).mockResolvedValue({
      data: {
        id: "coll-2",
        name: "Vacation",
        type: "virtual",
        created_at: "2024-01-01T00:00:00Z",
        item_count: 0,
      },
      error: undefined,
      response: new Response(),
    });

    renderPage();

    await waitFor(() => screen.getByText("Trip"));
    fireEvent.change(screen.getByLabelText("New collection name"), {
      target: { value: "Vacation" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create" }));

    await waitFor(() =>
      expect(apiClient.POST).toHaveBeenCalledWith("/api/v1/collections", {
        body: { name: "Vacation" },
      }),
    );
  });

  it("shows a collection's members as thumbnails when selected", async () => {
    mockGet();

    renderPage();

    await waitFor(() => screen.getByText("Trip"));
    fireEvent.click(screen.getByRole("button", { name: "Trip" }));

    await waitFor(() => screen.getAllByRole("img"));
    expect(screen.getAllByRole("img")).toHaveLength(2);
  });

  it("creates a smart collection from a quick filter preset with one click", async () => {
    mockGet();
    vi.mocked(apiClient.POST).mockResolvedValue({
      data: {
        id: "coll-3",
        name: "Screenshots",
        type: "smart",
        created_at: "2024-01-01T00:00:00Z",
        item_count: 0,
      },
      error: undefined,
      response: new Response(),
    });

    renderPage();

    await waitFor(() => screen.getByText("Screenshots"));
    fireEvent.click(
      screen.getByRole("button", { name: "Create smart collection" }),
    );

    await waitFor(() => screen.getByText("Created."));
    expect(apiClient.POST).toHaveBeenCalledWith("/api/v1/collections", {
      body: {
        name: "Screenshots",
        search_query: { text: "screenshot", mode: "text" },
      },
    });
  });
});
