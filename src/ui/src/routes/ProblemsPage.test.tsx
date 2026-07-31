// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "../api/client";
import { ProblemsPage } from "./ProblemsPage";

vi.mock("../api/client", () => ({
  apiClient: { GET: vi.fn(), POST: vi.fn() },
}));

window.__LAUNCH_TOKEN__ = "test-token";

const PROBLEMS = {
  groups: [
    {
      error_code: "provider_error",
      items: [
        { photo_id: "photo-1", error_message: "boom" },
        { photo_id: "photo-2", error_message: "boom again" },
      ],
    },
    {
      error_code: "capability_unavailable",
      items: [{ photo_id: "photo-3", error_message: "no model" }],
    },
  ],
};

function mockGetProblems(data: unknown = PROBLEMS): void {
  vi.mocked(apiClient.GET).mockResolvedValue({
    data,
    error: undefined,
    response: new Response(),
  });
}

function renderPage() {
  const client = new QueryClient();
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <ProblemsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("ProblemsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows a clean message when there are no problems", async () => {
    mockGetProblems({ groups: [] });

    renderPage();

    await waitFor(() =>
      screen.getByText("No problems -- everything analyzed successfully."),
    );
  });

  it("lists problems grouped by error code", async () => {
    mockGetProblems();

    renderPage();

    await waitFor(() => screen.getByText("provider_error (2)"));
    expect(screen.getByText("capability_unavailable (1)")).toBeTruthy();
    expect(screen.getByText("boom")).toBeTruthy();
    expect(screen.getByText("no model")).toBeTruthy();
  });

  it("retries the selected photos", async () => {
    mockGetProblems();
    vi.mocked(apiClient.POST).mockResolvedValue({
      data: { job_id: "job-1" },
      error: undefined,
      response: new Response(),
    });

    renderPage();

    await waitFor(() => screen.getByLabelText("Select photo-1"));
    fireEvent.click(screen.getByLabelText("Select photo-1"));
    fireEvent.click(screen.getByRole("button", { name: "Retry selected" }));

    await waitFor(() => screen.getByText("Retry queued."));
    expect(apiClient.POST).toHaveBeenCalledWith("/api/v1/problems/retry", {
      body: { photo_ids: ["photo-1"] },
    });
  });

  it("ignores the selected photos", async () => {
    mockGetProblems();
    vi.mocked(apiClient.POST).mockResolvedValue({
      data: null,
      error: undefined,
      response: new Response(),
    });

    renderPage();

    await waitFor(() => screen.getByLabelText("Select photo-3"));
    fireEvent.click(screen.getByLabelText("Select photo-3"));
    fireEvent.click(screen.getByRole("button", { name: "Ignore permanently" }));

    await waitFor(() => screen.getByText("Ignored."));
    expect(apiClient.POST).toHaveBeenCalledWith("/api/v1/problems/ignore", {
      body: { photo_ids: ["photo-3"] },
    });
  });

  it("does not show the action toolbar until something is selected", async () => {
    mockGetProblems();

    renderPage();

    await waitFor(() => screen.getByText("provider_error (2)"));
    expect(screen.queryByRole("toolbar")).toBeNull();
  });
});
