// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import type { ReactElement } from "react";
import { describe, expect, it, vi } from "vitest";

import { apiClient } from "../api/client";
import { PhotoDetail } from "./PhotoDetail";

// openapi-fetch snapshots `fetch` once when the client is created, so
// stubbing global fetch after import has no effect; mocking the client's
// own GET method is the reliable seam for this component's data layer.
vi.mock("../api/client", () => ({
  apiClient: { GET: vi.fn() },
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
});
