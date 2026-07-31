import { useState } from "react";
import type React from "react";
import { Link } from "react-router-dom";

import type { ProblemGroup } from "../api/hooks";
import { useIgnoreProblems, useProblems, useRetryProblems } from "../api/hooks";
import { thumbnailUrl } from "../api/thumbnailUrl";

function ProblemGroupSection({
  group,
  selectedIds,
  onToggleSelect,
}: {
  group: ProblemGroup;
  selectedIds: Set<string>;
  onToggleSelect: (photoId: string) => void;
}): React.JSX.Element {
  return (
    <section>
      <h2>
        {group.error_code} ({group.items.length})
      </h2>
      <ul style={{ listStyle: "none", padding: 0 }}>
        {group.items.map((item) => (
          <li key={item.photo_id}>
            <label>
              <input
                type="checkbox"
                aria-label={`Select ${item.photo_id}`}
                checked={selectedIds.has(item.photo_id)}
                onChange={() => onToggleSelect(item.photo_id)}
              />
              <Link to={`/photo/${item.photo_id}`}>
                <img
                  src={thumbnailUrl(item.photo_id, "grid")}
                  alt={item.photo_id}
                  width={80}
                  height={80}
                  style={{ objectFit: "cover", verticalAlign: "middle" }}
                />
              </Link>
              {item.error_message}
            </label>
          </li>
        ))}
      </ul>
    </section>
  );
}

/**
 * SDD §16.3's Problems view: `job_item` failures grouped by `error_code`,
 * with "retry these" (re-enqueue analysis) and "ignore permanently" actions
 * so a partial failure rate stays visible instead of silently vanishing
 * into "completed."
 */
export function ProblemsPage(): React.JSX.Element {
  const { data, isLoading } = useProblems();
  const retryProblems = useRetryProblems();
  const ignoreProblems = useIgnoreProblems();
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [message, setMessage] = useState<string | null>(null);

  if (isLoading || !data) {
    return <p>Loading problems...</p>;
  }

  const toggleSelect = (photoId: string): void => {
    setSelectedIds((previous) => {
      const next = new Set(previous);
      if (next.has(photoId)) {
        next.delete(photoId);
      } else {
        next.add(photoId);
      }
      return next;
    });
  };

  const handleRetry = (): void => {
    setMessage(null);
    retryProblems.mutate(Array.from(selectedIds), {
      onSuccess: () => {
        setMessage("Retry queued.");
        setSelectedIds(new Set());
      },
    });
  };

  const handleIgnore = (): void => {
    setMessage(null);
    ignoreProblems.mutate(Array.from(selectedIds), {
      onSuccess: () => {
        setMessage("Ignored.");
        setSelectedIds(new Set());
      },
    });
  };

  return (
    <div>
      <h1>Problems</h1>
      {data.groups.length === 0 ? (
        <p>No problems -- everything analyzed successfully.</p>
      ) : (
        <>
          {selectedIds.size > 0 && (
            <div role="toolbar" aria-label="Problem actions">
              <span>{selectedIds.size} selected</span>{" "}
              <button
                type="button"
                onClick={handleRetry}
                disabled={retryProblems.isPending}
              >
                Retry selected
              </button>{" "}
              <button
                type="button"
                onClick={handleIgnore}
                disabled={ignoreProblems.isPending}
              >
                Ignore permanently
              </button>
            </div>
          )}
          {message && <p>{message}</p>}
          {data.groups.map((group) => (
            <ProblemGroupSection
              key={group.error_code}
              group={group}
              selectedIds={selectedIds}
              onToggleSelect={toggleSelect}
            />
          ))}
        </>
      )}
    </div>
  );
}
