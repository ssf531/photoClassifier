// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "../api/client";
import { useProgressSocket } from "../api/ProgressSocketContext";
import type { JobProgress, ProgressSocket } from "../api/progressSocket";
import { OnboardingPage } from "./OnboardingPage";

vi.mock("../api/client", () => ({
  apiClient: { GET: vi.fn(), POST: vi.fn(), PATCH: vi.fn() },
}));

vi.mock("../api/ProgressSocketContext", () => ({
  useProgressSocket: vi.fn(),
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
  ],
};

function mockScanFlow(): void {
  vi.mocked(apiClient.POST).mockImplementation(
    async (path: string, options?: unknown) => {
      const body = (options as { body?: { path?: string } } | undefined)?.body;
      if (path === "/api/v1/library-roots") {
        return {
          data: { id: "root-1", path: body?.path ?? "" },
          error: undefined,
          response: new Response(),
        };
      }
      if (path === "/api/v1/scan") {
        return {
          data: { job_id: "job-1" },
          error: undefined,
          response: new Response(),
        };
      }
      throw new Error(`unexpected POST ${path}`);
    },
  );
}

function renderPage(
  subscribeImpl: ProgressSocket["subscribe"] = vi.fn(() => () => {}),
) {
  vi.mocked(useProgressSocket).mockReturnValue({
    subscribe: subscribeImpl,
  } as unknown as ProgressSocket);
  vi.mocked(apiClient.GET).mockResolvedValue({
    data: PLUGINS,
    error: undefined,
    response: new Response(),
  });

  const client = new QueryClient();
  return render(
    <QueryClientProvider client={client}>
      <OnboardingPage />
    </QueryClientProvider>,
  );
}

async function advanceToScanStep(): Promise<void> {
  fireEvent.change(screen.getByLabelText("Library root path"), {
    target: { value: "C:/Photos" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Next" }));
  await waitFor(() => screen.getByText("2. Enable AI modules"));
  fireEvent.click(screen.getByRole("button", { name: "Start first scan" }));
  await waitFor(() => screen.getByText("3. Scanning your library"));
}

describe("OnboardingPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("walks pick root -> enable modules -> start scan, calling each API with the prior step's result", async () => {
    renderPage();
    mockScanFlow();

    await advanceToScanStep();

    expect(apiClient.POST).toHaveBeenCalledWith("/api/v1/library-roots", {
      body: { path: "C:/Photos" },
    });
    expect(apiClient.POST).toHaveBeenCalledWith("/api/v1/scan", {
      body: { library_root_id: "root-1" },
    });
  });

  it("renders progress updates for the triggered job only", async () => {
    let capturedListener: ((progress: JobProgress) => void) | undefined;
    const subscribeImpl: ProgressSocket["subscribe"] = vi.fn((listener) => {
      capturedListener = listener;
      return () => {};
    });
    renderPage(subscribeImpl);
    mockScanFlow();

    await advanceToScanStep();

    capturedListener?.({
      jobId: "job-1",
      jobType: "scan",
      status: "running",
      progressPct: 42,
    });
    await waitFor(() => screen.getByText(/running \(42%\)/));

    // A progress event for a different job must not update the display.
    capturedListener?.({
      jobId: "other-job",
      jobType: "scan",
      status: "completed",
      progressPct: 100,
    });
    expect(screen.getByText(/running \(42%\)/)).toBeTruthy();
  });

  it("shows a job's progress even if it arrived before the scan response named that job", async () => {
    let capturedListener: ((progress: JobProgress) => void) | undefined;
    const subscribeImpl: ProgressSocket["subscribe"] = vi.fn((listener) => {
      capturedListener = listener;
      return () => {};
    });
    renderPage(subscribeImpl);

    vi.mocked(apiClient.POST).mockImplementation(
      async (path: string, options?: unknown) => {
        const body = (options as { body?: { path?: string } } | undefined)
          ?.body;
        if (path === "/api/v1/library-roots") {
          return {
            data: { id: "root-1", path: body?.path ?? "" },
            error: undefined,
            response: new Response(),
          };
        }
        if (path === "/api/v1/scan") {
          // Simulate a scan against a tiny/empty folder that completes and
          // broadcasts its progress before this POST's response resolves.
          capturedListener?.({
            jobId: "job-1",
            jobType: "scan",
            status: "completed",
            progressPct: 100,
          });
          return {
            data: { job_id: "job-1" },
            error: undefined,
            response: new Response(),
          };
        }
        throw new Error(`unexpected POST ${path}`);
      },
    );

    await advanceToScanStep();

    await waitFor(() => screen.getByText(/completed \(100%\)/));
  });
});
