import { describe, expect, it, vi } from "vitest";

import {
  ProgressSocket,
  type JobProgress,
  type ProgressSocketOptions,
} from "./progressSocket";

class FakeWebSocket {
  static instances: FakeWebSocket[] = [];
  onmessage: ((event: MessageEvent<string>) => void) | null = null;
  onclose: (() => void) | null = null;
  closed = false;

  constructor(public url: string) {
    FakeWebSocket.instances.push(this);
  }

  close(): void {
    this.closed = true;
    this.onclose?.();
  }

  emitMessage(payload: unknown): void {
    this.onmessage?.({ data: JSON.stringify(payload) } as MessageEvent<string>);
  }
}

function makeSocket(
  overrides: Partial<ProgressSocketOptions> = {},
): ProgressSocket {
  FakeWebSocket.instances.length = 0;
  return new ProgressSocket({
    url: "ws://127.0.0.1:8756/api/v1/jobs/progress",
    createWebSocket: (url) => new FakeWebSocket(url) as unknown as WebSocket,
    reconnectDelayMs: 100,
    ...overrides,
  });
}

const WIRE_PROGRESS = {
  job_id: "11111111-1111-1111-1111-111111111111",
  job_type: "analysis",
  status: "running",
  progress_pct: 42,
};

const EXPECTED_PROGRESS: JobProgress = {
  jobId: "11111111-1111-1111-1111-111111111111",
  jobType: "analysis",
  status: "running",
  progressPct: 42,
};

describe("ProgressSocket", () => {
  it("delivers progress events to subscribers", () => {
    const socket = makeSocket();
    const received: JobProgress[] = [];
    socket.subscribe((progress) => received.push(progress));

    socket.connect();
    FakeWebSocket.instances[0].emitMessage(WIRE_PROGRESS);

    expect(received).toEqual([EXPECTED_PROGRESS]);
  });

  it("resumes the stream after the connection drops, without the caller re-subscribing", () => {
    vi.useFakeTimers();
    try {
      const socket = makeSocket();
      const received: JobProgress[] = [];
      socket.subscribe((progress) => received.push(progress));
      socket.connect();
      expect(FakeWebSocket.instances).toHaveLength(1);

      // Simulate the core process restarting mid-stream.
      FakeWebSocket.instances[0].close();
      vi.advanceTimersByTime(100);

      expect(FakeWebSocket.instances).toHaveLength(2);
      FakeWebSocket.instances[1].emitMessage(WIRE_PROGRESS);
      expect(received).toEqual([EXPECTED_PROGRESS]);
    } finally {
      vi.useRealTimers();
    }
  });

  it("does not reconnect after an explicit close()", () => {
    vi.useFakeTimers();
    try {
      const socket = makeSocket();
      socket.connect();
      socket.close();

      vi.advanceTimersByTime(10_000);

      expect(FakeWebSocket.instances).toHaveLength(1);
      expect(FakeWebSocket.instances[0].closed).toBe(true);
    } finally {
      vi.useRealTimers();
    }
  });

  it("stops notifying a listener after it unsubscribes", () => {
    const socket = makeSocket();
    const received: JobProgress[] = [];
    const unsubscribe = socket.subscribe((progress) => received.push(progress));

    socket.connect();
    unsubscribe();
    FakeWebSocket.instances[0].emitMessage(WIRE_PROGRESS);

    expect(received).toEqual([]);
  });
});
