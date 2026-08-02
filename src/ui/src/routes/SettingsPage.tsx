import { useState } from "react";
import type React from "react";

import {
  usePlugins,
  useSettings,
  useUpdatePlugin,
  useUpdateSettings,
} from "../api/hooks";
import { getLaunchToken } from "../api/launchToken";

function LibraryRoots(): React.JSX.Element {
  const { data: settings, isLoading } = useSettings();
  const updateSettings = useUpdateSettings();
  const [newRoot, setNewRoot] = useState("");

  if (isLoading || !settings) {
    return <p>Loading settings...</p>;
  }

  const roots = settings.library_roots ?? [];

  const addRoot = (): void => {
    const trimmed = newRoot.trim();
    if (!trimmed || roots.includes(trimmed)) {
      return;
    }
    updateSettings.mutate({ library_roots: [...roots, trimmed] });
    setNewRoot("");
  };

  const removeRoot = (root: string): void => {
    updateSettings.mutate({
      library_roots: roots.filter((existing) => existing !== root),
    });
  };

  return (
    <section>
      <h2>Library roots</h2>
      <ul>
        {roots.map((root) => (
          <li key={root}>
            {root}
            <button type="button" onClick={() => removeRoot(root)}>
              Remove
            </button>
          </li>
        ))}
      </ul>
      <input
        type="text"
        placeholder="Add a folder path"
        aria-label="New library root"
        value={newRoot}
        onChange={(event) => setNewRoot(event.target.value)}
      />
      <button type="button" onClick={addRoot}>
        Add
      </button>
    </section>
  );
}

const CPU_ONLY_PROVIDER = "CPUExecutionProvider";

function GpuAndPerformance(): React.JSX.Element {
  const { data: settings, isLoading } = useSettings();
  const updateSettings = useUpdateSettings();
  const [cacheLimitInput, setCacheLimitInput] = useState<string | null>(null);

  if (isLoading || !settings) {
    return <p>Loading settings...</p>;
  }

  const cpuOnly = settings.gpu_execution_provider === CPU_ONLY_PROVIDER;
  const cacheLimitValue =
    cacheLimitInput ?? String(settings.thumbnail_cache_max_mb);

  const commitCacheLimit = (): void => {
    const parsed = Number(cacheLimitValue);
    if (Number.isFinite(parsed) && parsed > 0) {
      updateSettings.mutate({ thumbnail_cache_max_mb: parsed });
    }
    setCacheLimitInput(null);
  };

  return (
    <section>
      <h2>GPU &amp; performance</h2>
      <label>
        <input
          type="checkbox"
          checked={cpuOnly}
          onChange={(event) =>
            updateSettings.mutate({
              gpu_execution_provider: event.target.checked
                ? CPU_ONLY_PROVIDER
                : null,
            })
          }
        />
        CPU only (disable GPU acceleration)
      </label>
      <label>
        Thumbnail cache limit (MB)
        <input
          type="number"
          min={1}
          value={cacheLimitValue}
          onChange={(event) => setCacheLimitInput(event.target.value)}
          onBlur={commitCacheLimit}
        />
      </label>
    </section>
  );
}

function AiModules(): React.JSX.Element {
  const { data, isLoading } = usePlugins();
  const updatePlugin = useUpdatePlugin();

  if (isLoading || !data) {
    return <p>Loading plugins...</p>;
  }

  return (
    <section>
      <h2>AI modules</h2>
      <ul>
        {data.items.map((plugin) => (
          <li key={plugin.id}>
            <label>
              <input
                type="checkbox"
                checked={plugin.enabled}
                onChange={(event) =>
                  updatePlugin.mutate({
                    pluginId: plugin.id,
                    enabled: event.target.checked,
                  })
                }
              />
              {plugin.name} ({plugin.capability_types})
            </label>
          </li>
        ))}
      </ul>
    </section>
  );
}

function Diagnostics(): React.JSX.Element {
  const [includePaths, setIncludePaths] = useState(false);

  const downloadUrl =
    `/api/v1/diagnostics/bundle?include_paths=${includePaths}` +
    `&token=${encodeURIComponent(getLaunchToken())}`;

  return (
    <section>
      <h2>Diagnostics</h2>
      <p>
        Create a zip with recent logs, versions, capability status, and host
        details to attach to a bug report.
      </p>
      <label>
        <input
          type="checkbox"
          checked={includePaths}
          onChange={(event) => setIncludePaths(event.target.checked)}
        />
        Include library folder paths (these can reveal personal information)
      </label>
      <p>
        <a href={downloadUrl} download="diagnostics-bundle.zip">
          Create diagnostics bundle
        </a>
      </p>
    </section>
  );
}

/**
 * Library roots, enabled AI modules (TASK-069), and GPU/performance
 * controls (TASK-071). Per-capability provider selection is not exposed:
 * v1 ships exactly one provider per capability (CLIP embedding/tagging,
 * vit-gpt2 captioning, Laplacian quality, pHash duplicate detection), so
 * there is nothing to choose between yet -- this section becomes real once
 * a second provider for some capability exists. GPU preference only offers
 * "auto" vs. "CPU only" (not a per-execution-provider picker) since the
 * settings API doesn't expose which providers are actually available on
 * this machine -- select_execution_provider's CUDA/DirectML/CPU fallback
 * order already handles "auto" correctly without the UI needing to know.
 */
export function SettingsPage(): React.JSX.Element {
  return (
    <div>
      <h1>Settings</h1>
      <LibraryRoots />
      <AiModules />
      <GpuAndPerformance />
      <Diagnostics />
    </div>
  );
}
