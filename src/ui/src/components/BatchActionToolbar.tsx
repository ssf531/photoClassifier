import { useState } from "react";
import type React from "react";

import {
  useAddCollectionMembers,
  useCollections,
  useCopyToFolder,
  useExportXmp,
} from "../api/hooks";

export interface BatchActionToolbarProps {
  photoIds: string[];
  onClear: () => void;
}

function summarizeReport(
  items: { success: boolean }[] | undefined,
  total: number,
): string {
  const succeeded = items?.filter((item) => item.success).length ?? 0;
  return `${succeeded}/${total} succeeded.`;
}

/**
 * v1's batch actions are all additive (add to collection, export XMP,
 * copy to folder) -- the destructive staged-confirmation flow (TASK-077/
 * 078/079) is deferred to v2 (ADR-0007), so there is no confirmation
 * dialog here, matching the "no destructive action without explicit
 * per-item selection, no confirmation for additive actions" precedent
 * set by TASK-076's DuplicateReviewPage.
 */
export function BatchActionToolbar({
  photoIds,
  onClear,
}: BatchActionToolbarProps): React.JSX.Element {
  const { data: collections } = useCollections();
  const addMembers = useAddCollectionMembers();
  const exportXmp = useExportXmp();
  const copyToFolder = useCopyToFolder();

  const [collectionId, setCollectionId] = useState("");
  const [destination, setDestination] = useState("");
  const [message, setMessage] = useState<string | null>(null);

  const collectionItems = collections?.items ?? [];

  const handleAddToCollection = (): void => {
    if (!collectionId) {
      return;
    }
    setMessage(null);
    addMembers.mutate(
      { collectionId, photoIds },
      { onSuccess: () => setMessage(`Added ${photoIds.length} photo(s).`) },
    );
  };

  const handleExport = (): void => {
    setMessage(null);
    exportXmp.mutate(photoIds, {
      onSuccess: (report) =>
        setMessage(
          `Exported ${summarizeReport(report?.items, photoIds.length)}`,
        ),
    });
  };

  const handleCopy = (): void => {
    const trimmed = destination.trim();
    if (!trimmed) {
      return;
    }
    setMessage(null);
    copyToFolder.mutate(
      { photoIds, destinationFolder: trimmed },
      {
        onSuccess: (report) =>
          setMessage(
            `Copied ${summarizeReport(report?.items, photoIds.length)}`,
          ),
      },
    );
  };

  return (
    <div
      role="toolbar"
      aria-label="Batch actions"
      style={{
        display: "flex",
        flexWrap: "wrap",
        gap: "0.75rem",
        alignItems: "center",
        padding: "0.5rem",
        border: "1px solid",
      }}
    >
      <span>{photoIds.length} selected</span>

      <label>
        Add to collection
        <select
          aria-label="Add selected to collection"
          value={collectionId}
          onChange={(event) => setCollectionId(event.target.value)}
        >
          <option value="">Choose a collection</option>
          {collectionItems.map((collection) => (
            <option key={collection.id} value={collection.id}>
              {collection.name}
            </option>
          ))}
        </select>
      </label>
      <button
        type="button"
        onClick={handleAddToCollection}
        disabled={!collectionId || addMembers.isPending}
      >
        Add
      </button>

      <button
        type="button"
        onClick={handleExport}
        disabled={exportXmp.isPending}
      >
        Export to XMP
      </button>

      <label>
        Copy to folder
        <input
          type="text"
          aria-label="Batch destination folder"
          value={destination}
          onChange={(event) => setDestination(event.target.value)}
        />
      </label>
      <button
        type="button"
        onClick={handleCopy}
        disabled={!destination.trim() || copyToFolder.isPending}
      >
        Copy
      </button>

      <button type="button" onClick={onClear}>
        Clear selection
      </button>

      {message && <span>{message}</span>}
    </div>
  );
}
