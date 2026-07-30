import { useState } from "react";
import type React from "react";

import type { PluginSummary } from "../api/hooks";
import { usePlugins, useUpdatePlugin } from "../api/hooks";

function PluginRow({ plugin }: { plugin: PluginSummary }): React.JSX.Element {
  const updatePlugin = useUpdatePlugin();
  const [pendingApproval, setPendingApproval] = useState(false);

  const requestEnable = (): void => {
    if (plugin.permissions.length > 0) {
      setPendingApproval(true);
      return;
    }
    updatePlugin.mutate({ pluginId: plugin.id, enabled: true });
  };

  const approve = (): void => {
    setPendingApproval(false);
    updatePlugin.mutate({ pluginId: plugin.id, enabled: true });
  };

  return (
    <li>
      <strong>{plugin.name}</strong> ({plugin.capability_types}) --{" "}
      {plugin.source}
      {plugin.enabled ? (
        <button
          type="button"
          onClick={() =>
            updatePlugin.mutate({ pluginId: plugin.id, enabled: false })
          }
        >
          Disable
        </button>
      ) : (
        <button type="button" onClick={requestEnable}>
          Enable
        </button>
      )}
      {pendingApproval && (
        <div
          role="alertdialog"
          aria-label={`Approve permissions for ${plugin.name}`}
        >
          <p>
            {plugin.name} requires: {plugin.permissions.join(", ")}
          </p>
          <button type="button" onClick={approve}>
            Approve
          </button>
          <button type="button" onClick={() => setPendingApproval(false)}>
            Cancel
          </button>
        </div>
      )}
    </li>
  );
}

/**
 * Discover/enable/disable UI with an explicit permission-approval step
 * (TASK-070, SDD §8.3): enabling a plugin that declares permissions (e.g.
 * `network:outbound`) shows what it's asking for and requires an explicit
 * Approve click before the enable request fires -- disabling, and enabling
 * a plugin with no declared permissions, need no such step.
 */
export function PluginsPage(): React.JSX.Element {
  const { data, isLoading } = usePlugins();

  if (isLoading || !data) {
    return <p>Loading plugins...</p>;
  }

  return (
    <div>
      <h1>Plugins</h1>
      <ul>
        {data.items.map((plugin) => (
          <PluginRow key={plugin.id} plugin={plugin} />
        ))}
      </ul>
    </div>
  );
}
