import { useState } from "react";
import type React from "react";

import {
  usePlugins,
  useSettings,
  useUpdatePlugin,
  useUpdateSettings,
} from "../api/hooks";

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

/**
 * Library roots + enabled AI modules (TASK-069). Per-capability provider
 * selection is not exposed: v1 ships exactly one provider per capability
 * (CLIP embedding/tagging, vit-gpt2 captioning, Laplacian quality, pHash
 * duplicate detection), so there is nothing to choose between yet -- this
 * section becomes real once a second provider for some capability exists.
 */
export function SettingsPage(): React.JSX.Element {
  return (
    <div>
      <h1>Settings</h1>
      <LibraryRoots />
      <AiModules />
    </div>
  );
}
