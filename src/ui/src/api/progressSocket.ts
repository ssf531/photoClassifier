import { getLaunchToken } from "./launchToken";

export type JobStatus =
  | "queued"
  | "running"
  | "paused"
  | "completed"
  | "failed"
  | "partially_completed"
  | "cancelled";

export interface JobProgress {
  jobId: string;
  jobType: string;
  status: JobStatus;
  progressPct: number;
}

interface JobProgressWire {
  job_id: string;
  job_type: string;
  status: JobStatus;
  progress_pct: number;
}

function fromWire(wire: JobProgressWire): JobProgress {
  return {
    jobId: wire.job_id,
    jobType: wire.job_type,
    status: wire.status,
    progressPct: wire.progress_pct,
  };
}

type ProgressListener = (progress: JobProgress) => void;

export interface ProgressSocketOptions {
  url: string;
  createWebSocket?: (url: string) => WebSocket;
  reconnectDelayMs?: number;
}

const DEFAULT_RECONNECT_DELAY_MS = 1000;

/**
 * Reconnect-on-drop subscription to the core's job-progress WebSocket
 * (FEAT-061). The server side has no per-connection session state --
 * `progress_stream()` just hands back a fresh queue -- so reconnecting and
 * resubscribing after a drop is always safe; only events that arrived while
 * disconnected are lost.
 */
export class ProgressSocket {
  private readonly url: string;
  private readonly createWebSocket: (url: string) => WebSocket;
  private readonly reconnectDelayMs: number;
  private readonly listeners = new Set<ProgressListener>();
  private socket: WebSocket | null = null;
  private closedByCaller = false;

  constructor(options: ProgressSocketOptions) {
    this.url = options.url;
    this.createWebSocket =
      options.createWebSocket ?? ((url) => new WebSocket(url));
    this.reconnectDelayMs =
      options.reconnectDelayMs ?? DEFAULT_RECONNECT_DELAY_MS;
  }

  connect(): void {
    this.closedByCaller = false;
    this.open();
  }

  close(): void {
    this.closedByCaller = true;
    this.socket?.close();
  }

  subscribe(listener: ProgressListener): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  private open(): void {
    const socket = this.createWebSocket(this.url);
    this.socket = socket;
    socket.onmessage = (event: MessageEvent<string>) => {
      const wire = JSON.parse(event.data) as JobProgressWire;
      const progress = fromWire(wire);
      for (const listener of this.listeners) listener(progress);
    };
    socket.onclose = () => {
      if (!this.closedByCaller) {
        setTimeout(() => this.open(), this.reconnectDelayMs);
      }
    };
  }
}

export function createProgressSocket(): ProgressSocket {
  const wsOrigin = window.location.origin.replace(/^http/, "ws");
  const url = `${wsOrigin}/api/v1/jobs/progress?token=${encodeURIComponent(getLaunchToken())}`;
  return new ProgressSocket({ url });
}
