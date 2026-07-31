// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "../api/client";
import { DuplicateReviewPage } from "./DuplicateReviewPage";

vi.mock("../api/client", () => ({
  apiClient: { GET: vi.fn(), POST: vi.fn() },
}));

window.__LAUNCH_TOKEN__ = "test-token";

const DUPLICATE_GROUPS = {
  items: [
    {
      id: "group-1",
      detection_method: "dhash@1",
      created_at: "2024-01-01T00:00:00Z",
      members: [
        {
          photo_id: "photo-keeper",
          similarity_score: 1.0,
          is_recommended_keeper: true,
        },
        {
          photo_id: "photo-other",
          similarity_score: 0.9,
          is_recommended_keeper: false,
        },
      ],
    },
  ],
};

const COLLECTIONS = {
  items: [
    {
      id: "coll-1",
      name: "Trip",
      type: "virtual",
      created_at: "2024-01-01T00:00:00Z",
      item_count: 0,
    },
  ],
};

function mockGet(): void {
  vi.mocked(apiClient.GET).mockImplementation(async (path: string) => {
    if (path === "/api/v1/duplicate-groups") {
      return {
        data: DUPLICATE_GROUPS,
        error: undefined,
        response: new Response(),
      };
    }
    if (path === "/api/v1/collections") {
      return { data: COLLECTIONS, error: undefined, response: new Response() };
    }
    throw new Error(`unexpected GET ${path}`);
  });
}

function renderPage() {
  const client = new QueryClient();
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <DuplicateReviewPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("DuplicateReviewPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows the suggested keeper as a label, not a preselected checkbox, and nothing is checked by default", async () => {
    mockGet();

    renderPage();

    await waitFor(() => screen.getByText("Suggested keeper"));
    const checkboxes = screen.getAllByRole("checkbox") as HTMLInputElement[];
    expect(checkboxes).toHaveLength(2);
    expect(checkboxes.every((box) => !box.checked)).toBe(true);
  });

  it("keeps the add-to-collection action disabled until a photo and a collection are both selected", async () => {
    mockGet();

    renderPage();

    await waitFor(() => screen.getByText("Suggested keeper"));
    const addButton = screen.getByRole("button", {
      name: "Add selected",
    }) as HTMLButtonElement;
    expect(addButton.disabled).toBe(true);

    fireEvent.click(screen.getByLabelText("Select photo-other"));
    expect(addButton.disabled).toBe(true);

    fireEvent.change(screen.getByLabelText("Add selected to collection"), {
      target: { value: "coll-1" },
    });
    expect(addButton.disabled).toBe(false);
  });

  it("adds only the explicitly checked photos to the chosen collection", async () => {
    mockGet();
    vi.mocked(apiClient.POST).mockResolvedValue({
      data: null,
      error: undefined,
      response: new Response(),
    });

    renderPage();

    await waitFor(() => screen.getByText("Suggested keeper"));
    fireEvent.click(screen.getByLabelText("Select photo-other"));
    fireEvent.change(screen.getByLabelText("Add selected to collection"), {
      target: { value: "coll-1" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Add selected" }));

    await waitFor(() => screen.getByText("Added."));
    expect(apiClient.POST).toHaveBeenCalledWith(
      "/api/v1/collections/{collection_id}/members",
      {
        params: { path: { collection_id: "coll-1" } },
        body: { photo_ids: ["photo-other"] },
      },
    );
  });
});
