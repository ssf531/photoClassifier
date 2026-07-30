// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "../api/client";
import { PluginsPage } from "./PluginsPage";

vi.mock("../api/client", () => ({
  apiClient: { GET: vi.fn(), PATCH: vi.fn() },
}));

const PLUGINS = {
  items: [
    {
      id: "clip",
      name: "CLIP",
      capability_types: "embedding,tag",
      version: "1.0.0",
      source: "builtin",
      enabled: false,
      permissions: [],
    },
    {
      id: "remote-tagger",
      name: "Remote Tagger",
      capability_types: "tag",
      version: "1.0.0",
      source: "download",
      enabled: false,
      permissions: ["network:outbound"],
    },
  ],
};

function renderPage() {
  vi.mocked(apiClient.GET).mockResolvedValue({
    data: PLUGINS,
    error: undefined,
    response: new Response(),
  });

  const client = new QueryClient();
  return render(
    <QueryClientProvider client={client}>
      <PluginsPage />
    </QueryClientProvider>,
  );
}

describe("PluginsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("enables a plugin with no declared permissions immediately, no prompt", async () => {
    renderPage();
    await waitFor(() => screen.getByText("CLIP"));

    const enableButtons = screen.getAllByRole("button", { name: "Enable" });
    fireEvent.click(enableButtons[0]);

    expect(screen.queryByRole("alertdialog")).toBeNull();
    await waitFor(() => {
      expect(apiClient.PATCH).toHaveBeenCalledWith(
        "/api/v1/plugins/{plugin_id}",
        {
          params: { path: { plugin_id: "clip" } },
          body: { enabled: true },
        },
      );
    });
  });

  it("shows an explicit permission prompt naming network:outbound before enabling completes", async () => {
    renderPage();
    await waitFor(() => screen.getByText("Remote Tagger"));

    const enableButtons = screen.getAllByRole("button", { name: "Enable" });
    fireEvent.click(enableButtons[enableButtons.length - 1]);

    const prompt = screen.getByRole("alertdialog");
    expect(prompt.textContent).toContain("network:outbound");
    expect(apiClient.PATCH).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Approve" }));

    await waitFor(() => {
      expect(apiClient.PATCH).toHaveBeenCalledWith(
        "/api/v1/plugins/{plugin_id}",
        {
          params: { path: { plugin_id: "remote-tagger" } },
          body: { enabled: true },
        },
      );
    });
  });

  it("does not enable if the permission prompt is cancelled", async () => {
    renderPage();
    await waitFor(() => screen.getByText("Remote Tagger"));

    const enableButtons = screen.getAllByRole("button", { name: "Enable" });
    fireEvent.click(enableButtons[enableButtons.length - 1]);
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));

    expect(screen.queryByRole("alertdialog")).toBeNull();
    expect(apiClient.PATCH).not.toHaveBeenCalled();
  });
});
