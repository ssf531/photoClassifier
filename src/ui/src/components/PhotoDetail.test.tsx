// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactElement } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "../api/client";
import { PhotoDetail } from "./PhotoDetail";

// openapi-fetch snapshots `fetch` once when the client is created, so
// stubbing global fetch after import has no effect; mocking the client's
// own GET/POST methods is the reliable seam for this component's data layer.
vi.mock("../api/client", () => ({
  apiClient: { GET: vi.fn(), POST: vi.fn() },
}));

window.__LAUNCH_TOKEN__ = "test-token";

const DETAIL_RESPONSE = {
  id: "photo-1",
  relative_path: "beach.jpg",
  captured_at_utc: null,
  camera_make: "Canon",
  camera_model: "EOS R5",
  width: 6000,
  height: 4000,
  ai_results: [
    {
      capability: "caption",
      payload: { caption: "a dog on the beach" },
      confidence: 0.9,
      model_version: "v1",
    },
    {
      capability: "tag",
      payload: {
        tags: [
          { label: "dog", confidence: 0.8 },
          { label: "beach", confidence: 0.7 },
        ],
      },
      confidence: 0.8,
      model_version: "v1",
    },
    {
      capability: "quality",
      payload: {
        sharpness_variance: 120.5,
        mean_brightness: 100,
        is_blurry: false,
        is_underexposed: false,
        is_overexposed: false,
      },
      confidence: 1.0,
      model_version: "v1",
    },
  ],
};

function renderWithClient(ui: ReactElement) {
  const client = new QueryClient();
  return render(
    <QueryClientProvider client={client}>{ui}</QueryClientProvider>,
  );
}

function mockGetResponse(data: unknown): void {
  vi.mocked(apiClient.GET).mockResolvedValue({
    data,
    error: undefined,
    response: new Response(),
  });
}

describe("PhotoDetail", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders caption, tags, and quality score for a fully-analyzed photo", async () => {
    mockGetResponse(DETAIL_RESPONSE);

    renderWithClient(<PhotoDetail photoId="photo-1" />);

    await waitFor(() => screen.getByText("a dog on the beach"));
    expect(screen.getByText("dog")).toBeTruthy();
    expect(screen.getByText("beach")).toBeTruthy();
    expect(screen.getByText("120.5")).toBeTruthy();
  });

  it("renders a placeholder when no capability has analyzed the photo yet", async () => {
    mockGetResponse({ ...DETAIL_RESPONSE, ai_results: [] });

    renderWithClient(<PhotoDetail photoId="photo-1" />);

    await waitFor(() => screen.getByText("Not analyzed yet."));
  });

  it("shows a message when no collections exist to add the photo to", async () => {
    vi.mocked(apiClient.GET).mockImplementation(async (path: string) => {
      const data =
        path === "/api/v1/collections" ? { items: [] } : DETAIL_RESPONSE;
      return { data, error: undefined, response: new Response() };
    });

    renderWithClient(<PhotoDetail photoId="photo-1" />);

    await waitFor(() =>
      screen.getByText(
        "No collections yet -- create one on the Collections page.",
      ),
    );
  });

  it("adds the current photo to the selected collection", async () => {
    vi.mocked(apiClient.GET).mockImplementation(async (path: string) => {
      const data =
        path === "/api/v1/collections"
          ? {
              items: [
                {
                  id: "coll-1",
                  name: "Trip",
                  type: "virtual",
                  created_at: "2024-01-01T00:00:00Z",
                  item_count: 0,
                },
              ],
            }
          : DETAIL_RESPONSE;
      return { data, error: undefined, response: new Response() };
    });
    vi.mocked(apiClient.POST).mockResolvedValue({
      data: null,
      error: undefined,
      response: new Response(),
    });

    renderWithClient(<PhotoDetail photoId="photo-1" />);

    await waitFor(() => screen.getByLabelText("Add to collection"));
    fireEvent.change(screen.getByLabelText("Add to collection"), {
      target: { value: "coll-1" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Add" }));

    await waitFor(() => screen.getByText("Added."));
    expect(apiClient.POST).toHaveBeenCalledWith(
      "/api/v1/collections/{collection_id}/members",
      {
        params: { path: { collection_id: "coll-1" } },
        body: { photo_ids: ["photo-1"] },
      },
    );
  });

  it("exports the photo to XMP and reports success", async () => {
    mockGetResponse(DETAIL_RESPONSE);
    vi.mocked(apiClient.POST).mockResolvedValue({
      data: { items: [{ photo_id: "photo-1", success: true, error: null }] },
      error: undefined,
      response: new Response(),
    });

    renderWithClient(<PhotoDetail photoId="photo-1" />);

    await waitFor(() => screen.getByRole("button", { name: "Export to XMP" }));
    fireEvent.click(screen.getByRole("button", { name: "Export to XMP" }));

    await waitFor(() => screen.getByText("Exported."));
    expect(apiClient.POST).toHaveBeenCalledWith("/api/v1/export/xmp", {
      body: { photo_ids: ["photo-1"] },
    });
  });

  it("shows the reported error when exporting to XMP fails", async () => {
    mockGetResponse(DETAIL_RESPONSE);
    vi.mocked(apiClient.POST).mockResolvedValue({
      data: {
        items: [
          {
            photo_id: "photo-1",
            success: false,
            error: "photo photo-1 has no AI result or rating to export",
          },
        ],
      },
      error: undefined,
      response: new Response(),
    });

    renderWithClient(<PhotoDetail photoId="photo-1" />);

    await waitFor(() => screen.getByRole("button", { name: "Export to XMP" }));
    fireEvent.click(screen.getByRole("button", { name: "Export to XMP" }));

    await waitFor(() =>
      screen.getByText("photo photo-1 has no AI result or rating to export"),
    );
  });

  it("copies the photo to the entered destination folder", async () => {
    mockGetResponse(DETAIL_RESPONSE);
    vi.mocked(apiClient.POST).mockResolvedValue({
      data: {
        items: [
          {
            photo_id: "photo-1",
            success: true,
            destination_path: "C:/Export/beach.jpg",
            error: null,
          },
        ],
      },
      error: undefined,
      response: new Response(),
    });

    renderWithClient(<PhotoDetail photoId="photo-1" />);

    await waitFor(() => screen.getByLabelText("Destination folder"));
    fireEvent.change(screen.getByLabelText("Destination folder"), {
      target: { value: "C:/Export" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Copy" }));

    await waitFor(() => screen.getByText("Copied."));
    expect(apiClient.POST).toHaveBeenCalledWith("/api/v1/export/copy", {
      body: { photo_ids: ["photo-1"], destination_folder: "C:/Export" },
    });
  });

  it("keeps the copy action disabled until a destination folder is entered", async () => {
    mockGetResponse(DETAIL_RESPONSE);

    renderWithClient(<PhotoDetail photoId="photo-1" />);

    await waitFor(() => screen.getByLabelText("Destination folder"));
    const copyButton = screen.getByRole("button", {
      name: "Copy",
    }) as HTMLButtonElement;
    expect(copyButton.disabled).toBe(true);

    fireEvent.change(screen.getByLabelText("Destination folder"), {
      target: { value: "C:/Export" },
    });
    expect(copyButton.disabled).toBe(false);
  });
});
