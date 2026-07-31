// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactElement } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "../api/client";
import { BatchActionToolbar } from "./BatchActionToolbar";

vi.mock("../api/client", () => ({
  apiClient: { GET: vi.fn(), POST: vi.fn() },
}));

window.__LAUNCH_TOKEN__ = "test-token";

const COLLECTIONS_RESPONSE = {
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

function renderWithClient(ui: ReactElement) {
  const client = new QueryClient();
  return render(
    <QueryClientProvider client={client}>{ui}</QueryClientProvider>,
  );
}

describe("BatchActionToolbar", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(apiClient.GET).mockResolvedValue({
      data: COLLECTIONS_RESPONSE,
      error: undefined,
      response: new Response(),
    });
  });

  it("shows the selected count", async () => {
    renderWithClient(
      <BatchActionToolbar photoIds={["a", "b", "c"]} onClear={vi.fn()} />,
    );

    await waitFor(() => screen.getByText("3 selected"));
  });

  it("adds all selected photos to the chosen collection", async () => {
    vi.mocked(apiClient.POST).mockResolvedValue({
      data: null,
      error: undefined,
      response: new Response(),
    });

    renderWithClient(
      <BatchActionToolbar photoIds={["a", "b"]} onClear={vi.fn()} />,
    );

    await screen.findByRole("option", { name: "Trip" });
    fireEvent.change(screen.getByLabelText("Add selected to collection"), {
      target: { value: "coll-1" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Add" }));

    await waitFor(() => screen.getByText("Added 2 photo(s)."));
    expect(apiClient.POST).toHaveBeenCalledWith(
      "/api/v1/collections/{collection_id}/members",
      {
        params: { path: { collection_id: "coll-1" } },
        body: { photo_ids: ["a", "b"] },
      },
    );
  });

  it("exports all selected photos to XMP and reports the success count", async () => {
    vi.mocked(apiClient.POST).mockResolvedValue({
      data: {
        items: [
          { photo_id: "a", success: true, error: null },
          { photo_id: "b", success: false, error: "no AI result" },
        ],
      },
      error: undefined,
      response: new Response(),
    });

    renderWithClient(
      <BatchActionToolbar photoIds={["a", "b"]} onClear={vi.fn()} />,
    );

    fireEvent.click(
      await screen.findByRole("button", { name: "Export to XMP" }),
    );

    await waitFor(() => screen.getByText("Exported 1/2 succeeded."));
    expect(apiClient.POST).toHaveBeenCalledWith("/api/v1/export/xmp", {
      body: { photo_ids: ["a", "b"] },
    });
  });

  it("copies all selected photos to the entered destination folder", async () => {
    vi.mocked(apiClient.POST).mockResolvedValue({
      data: {
        items: [
          { photo_id: "a", success: true, destination_path: "C:/x/a.jpg" },
          { photo_id: "b", success: true, destination_path: "C:/x/b.jpg" },
        ],
      },
      error: undefined,
      response: new Response(),
    });

    renderWithClient(
      <BatchActionToolbar photoIds={["a", "b"]} onClear={vi.fn()} />,
    );

    const destinationInput = await screen.findByLabelText(
      "Batch destination folder",
    );
    fireEvent.change(destinationInput, { target: { value: "C:/x" } });
    fireEvent.click(screen.getByRole("button", { name: "Copy" }));

    await waitFor(() => screen.getByText("Copied 2/2 succeeded."));
    expect(apiClient.POST).toHaveBeenCalledWith("/api/v1/export/copy", {
      body: { photo_ids: ["a", "b"], destination_folder: "C:/x" },
    });
  });

  it("calls onClear when 'Clear selection' is clicked", async () => {
    const onClear = vi.fn();
    renderWithClient(<BatchActionToolbar photoIds={["a"]} onClear={onClear} />);

    fireEvent.click(
      await screen.findByRole("button", { name: "Clear selection" }),
    );

    expect(onClear).toHaveBeenCalled();
  });
});
