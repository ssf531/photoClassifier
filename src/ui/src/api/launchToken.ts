declare global {
  interface Window {
    __LAUNCH_TOKEN__?: string;
  }
}

/**
 * The core process embeds this directly into the served index.html (ADR-0002:
 * UI and API share one process, so the bearer token is never written to disk
 * or passed via stdin). Missing here means the app isn't running inside the
 * real webview host -- there is no fallback.
 */
export function getLaunchToken(): string {
  const token = window.__LAUNCH_TOKEN__;
  if (!token) {
    throw new Error("__LAUNCH_TOKEN__ was not injected into index.html");
  }
  return token;
}
