// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { apiClient } from "../api/client";
import { SettingsPage } from "./SettingsPage";

vi.mock("../api/client", () => ({
  apiClient: { GET: vi.fn(), PATCH: vi.fn() },
}));

const SETTINGS = {
  library_roots: ["C:/Photos"],
  log_level: "INFO",
  thumbnail_cache_max_mb: 2048,
  gpu_execution_provider: null,
  missing_photo_grace_period_days: 30,
  thumbnail_grid_size_px: 256,
  thumbnail_preview_size_px: 1024,
};

const PLUGINS = {
  items: [
    {
      id: "clip",
      name: "CLIP",
      capability_types: "embedding,tag",
      version: "1.0.0",
      source: "builtin",
      enabled: true,
      permissions: [],
    },
    {
      id: "vit-gpt2-caption",
      name: "Captioner",
      capability_types: "caption",
      version: "1.0.0",
      source: "builtin",
      enabled: true,
      permissions: [],
    },
  ],
};

function renderPage() {
  vi.mocked(apiClient.GET).mockImplementation(async (path: string) => {
    if (path === "/api/v1/settings") {
      return { data: SETTINGS, error: undefined, response: new Response() };
    }
    if (path === "/api/v1/plugins") {
      return { data: PLUGINS, error: undefined, response: new Response() };
    }
    throw new Error(`unexpected GET ${path}`);
  });

  const client = new QueryClient();
  return render(
    <QueryClientProvider client={client}>
      <SettingsPage />
    </QueryClientProvider>,
  );
}

describe("SettingsPage", () => {
  it("shows the current library roots and enabled AI modules", async () => {
    renderPage();

    await waitFor(() => screen.getByText("C:/Photos"));
    expect(screen.getByText(/Captioner/)).toBeTruthy();
  });

  it("disabling a module PATCHes it with enabled: false", async () => {
    renderPage();
    vi.mocked(apiClient.PATCH).mockResolvedValue({
      data: { ...PLUGINS.items[1], enabled: false },
      error: undefined,
      response: new Response(),
    });

    await waitFor(() => screen.getByText(/Captioner/));
    const captionCheckbox = screen.getByRole("checkbox", { name: /Captioner/ });
    fireEvent.click(captionCheckbox);

    await waitFor(() => {
      expect(apiClient.PATCH).toHaveBeenCalledWith(
        "/api/v1/plugins/{plugin_id}",
        {
          params: { path: { plugin_id: "vit-gpt2-caption" } },
          body: { enabled: false },
        },
      );
    });
  });
});
