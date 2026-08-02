// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "../api/client";
import { SettingsPage } from "./SettingsPage";

vi.mock("../api/client", () => ({
  apiClient: { GET: vi.fn(), PATCH: vi.fn() },
}));

window.__LAUNCH_TOKEN__ = "test-token";

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
  beforeEach(() => {
    vi.clearAllMocks();
  });

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

  it("checking CPU only PATCHes gpu_execution_provider", async () => {
    renderPage();
    vi.mocked(apiClient.PATCH).mockResolvedValue({
      data: { ...SETTINGS, gpu_execution_provider: "CPUExecutionProvider" },
      error: undefined,
      response: new Response(),
    });

    await waitFor(() => screen.getByText("C:/Photos"));
    fireEvent.click(screen.getByRole("checkbox", { name: /CPU only/ }));

    await waitFor(() => {
      expect(apiClient.PATCH).toHaveBeenCalledWith("/api/v1/settings", {
        body: { gpu_execution_provider: "CPUExecutionProvider" },
      });
    });
  });

  it("commits a new cache limit on blur", async () => {
    renderPage();
    vi.mocked(apiClient.PATCH).mockResolvedValue({
      data: { ...SETTINGS, thumbnail_cache_max_mb: 4096 },
      error: undefined,
      response: new Response(),
    });

    await waitFor(() => screen.getByText("C:/Photos"));
    const cacheInput = screen.getByLabelText(/Thumbnail cache limit/);
    fireEvent.change(cacheInput, { target: { value: "4096" } });
    fireEvent.blur(cacheInput);

    await waitFor(() => {
      expect(apiClient.PATCH).toHaveBeenCalledWith("/api/v1/settings", {
        body: { thumbnail_cache_max_mb: 4096 },
      });
    });
  });

  it("links to the diagnostics bundle without paths by default", async () => {
    renderPage();

    await waitFor(() => screen.getByText("Create diagnostics bundle"));
    const link = screen.getByRole("link", {
      name: "Create diagnostics bundle",
    }) as HTMLAnchorElement;
    expect(link.href).toContain("/api/v1/diagnostics/bundle");
    expect(link.href).toContain("include_paths=false");
    expect(link.href).toContain("token=test-token");
  });

  it("includes paths in the diagnostics bundle link once consented", async () => {
    renderPage();

    await waitFor(() => screen.getByText("Create diagnostics bundle"));
    fireEvent.click(
      screen.getByRole("checkbox", { name: /Include library folder paths/ }),
    );

    const link = screen.getByRole("link", {
      name: "Create diagnostics bundle",
    }) as HTMLAnchorElement;
    expect(link.href).toContain("include_paths=true");
  });
});
