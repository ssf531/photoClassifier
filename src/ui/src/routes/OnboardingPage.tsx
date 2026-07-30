import { useEffect, useRef, useState } from "react";
import type React from "react";

import { useProgressSocket } from "../api/ProgressSocketContext";
import {
  useCreateLibraryRoot,
  usePlugins,
  useTriggerScan,
  useUpdatePlugin,
} from "../api/hooks";
import type { JobProgress } from "../api/progressSocket";

type Step = "root" | "modules" | "scan";

/**
 * First-run flow: pick a library root -> enable default AI modules -> start
 * the first scan (TASK-072), using only the settings/plugin/scan APIs a
 * user could otherwise drive by hand -- nothing here requires editing
 * config.toml directly.
 */
export function OnboardingPage(): React.JSX.Element {
  const [step, setStep] = useState<Step>("root");
  const [path, setPath] = useState("");
  const [libraryRootId, setLibraryRootId] = useState<string | null>(null);
  const [latestProgress, setLatestProgress] = useState<JobProgress | null>(
    null,
  );

  const createLibraryRoot = useCreateLibraryRoot();
  const triggerScan = useTriggerScan();
  const { data: plugins } = usePlugins();
  const updatePlugin = useUpdatePlugin();
  const progressSocket = useProgressSocket();

  // Subscribed unconditionally (not gated on a job existing yet) and every
  // event is buffered by job id: a scan against a small/empty folder can
  // finish before startScan()'s state updates re-render this component, so
  // by the time we know the job id its progress may have already arrived.
  const jobIdRef = useRef<string | null>(null);
  const progressByJobRef = useRef(new Map<string, JobProgress>());

  useEffect(() => {
    return progressSocket.subscribe((progress) => {
      progressByJobRef.current.set(progress.jobId, progress);
      if (progress.jobId === jobIdRef.current) {
        setLatestProgress(progress);
      }
    });
  }, [progressSocket]);

  const handlePickRoot = async (): Promise<void> => {
    const trimmed = path.trim();
    if (!trimmed) {
      return;
    }
    const root = await createLibraryRoot.mutateAsync(trimmed);
    setLibraryRootId(root.id);
    setStep("modules");
  };

  const enableAll = (): void => {
    for (const plugin of plugins?.items ?? []) {
      if (!plugin.enabled && plugin.permissions.length === 0) {
        updatePlugin.mutate({ pluginId: plugin.id, enabled: true });
      }
    }
  };

  const startScan = async (): Promise<void> => {
    if (!libraryRootId) {
      return;
    }
    const result = await triggerScan.mutateAsync(libraryRootId);
    jobIdRef.current = result.job_id;
    setLatestProgress(progressByJobRef.current.get(result.job_id) ?? null);
    setStep("scan");
  };

  return (
    <div>
      <h1>Welcome</h1>
      {step === "root" && (
        <section>
          <h2>1. Choose a photo folder</h2>
          <input
            type="text"
            aria-label="Library root path"
            value={path}
            onChange={(event) => setPath(event.target.value)}
          />
          <button type="button" onClick={() => void handlePickRoot()}>
            Next
          </button>
        </section>
      )}
      {step === "modules" && (
        <section>
          <h2>2. Enable AI modules</h2>
          <ul>
            {(plugins?.items ?? []).map((plugin) => (
              <li key={plugin.id}>
                {plugin.name}: {plugin.enabled ? "enabled" : "disabled"}
              </li>
            ))}
          </ul>
          <button type="button" onClick={enableAll}>
            Enable all
          </button>
          <button type="button" onClick={() => void startScan()}>
            Start first scan
          </button>
        </section>
      )}
      {step === "scan" && (
        <section>
          <h2>3. Scanning your library</h2>
          {latestProgress ? (
            <p>
              {latestProgress.status} ({Math.round(latestProgress.progressPct)}
              %)
            </p>
          ) : (
            <p>Waiting for progress...</p>
          )}
        </section>
      )}
    </div>
  );
}
