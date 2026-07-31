// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { apiClient } from "../api/client";
import { RecommendationsPage } from "./RecommendationsPage";

vi.mock("../api/client", () => ({
  apiClient: { GET: vi.fn() },
}));

window.__LAUNCH_TOKEN__ = "test-token";

const RECOMMENDATIONS = {
  items: [
    { category: "screenshots", photo_ids: ["photo-1", "photo-2"] },
    { category: "low_quality", photo_ids: ["photo-3"] },
    { category: "near_duplicates", photo_ids: [] },
  ],
};

function renderPage() {
  vi.mocked(apiClient.GET).mockResolvedValue({
    data: RECOMMENDATIONS,
    error: undefined,
    response: new Response(),
  });

  const client = new QueryClient();
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <RecommendationsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("RecommendationsPage", () => {
  it("shows each category's count and thumbnails, or a placeholder when empty", async () => {
    renderPage();

    await waitFor(() => screen.getByText("Screenshots (2)"));
    expect(screen.getByText("Low quality (1)")).toBeTruthy();
    expect(screen.getByText("Near-duplicates (0)")).toBeTruthy();
    expect(screen.getByText("Nothing here yet.")).toBeTruthy();
    expect(screen.getAllByRole("img")).toHaveLength(3);
  });
});
