import { useState } from "react";
import type React from "react";
import { Link } from "react-router-dom";

import {
  useBuiltinFilters,
  useCollectionMembers,
  useCollections,
  useCreateCollection,
  useExportCollectionXmp,
} from "../api/hooks";
import { thumbnailUrl } from "../api/thumbnailUrl";

function QuickFilters(): React.JSX.Element | null {
  const { data } = useBuiltinFilters();
  const createCollection = useCreateCollection();
  const [createdKey, setCreatedKey] = useState<string | null>(null);

  if (!data || data.items.length === 0) {
    return null;
  }

  return (
    <div>
      <h2>Quick filters</h2>
      <ul>
        {data.items.map((preset) => (
          <li key={preset.key}>
            {preset.label}{" "}
            <button
              type="button"
              onClick={() => {
                createCollection.mutate(
                  { name: preset.label, search_query: preset.search_query },
                  { onSuccess: () => setCreatedKey(preset.key) },
                );
              }}
            >
              Create smart collection
            </button>
            {createdKey === preset.key && <span> Created.</span>}
          </li>
        ))}
      </ul>
    </div>
  );
}

function ExportCollectionXmpButton({
  collectionId,
}: {
  collectionId: string;
}): React.JSX.Element {
  const exportCollectionXmp = useExportCollectionXmp();
  const [preset, setPreset] = useState("default");
  const [message, setMessage] = useState<string | null>(null);

  const handleExport = (): void => {
    setMessage(null);
    exportCollectionXmp.mutate(
      { collectionId, preset },
      {
        onSuccess: (report) => {
          const total = report?.items.length ?? 0;
          const succeeded =
            report?.items.filter((item) => item.success).length ?? 0;
          setMessage(`Exported ${succeeded}/${total} succeeded.`);
        },
      },
    );
  };

  return (
    <div>
      <label>
        Export preset
        <select
          aria-label="Collection export preset"
          value={preset}
          onChange={(event) => setPreset(event.target.value)}
        >
          <option value="default">Default</option>
          <option value="lightroom">Lightroom keyword hierarchy</option>
        </select>
      </label>
      <button
        type="button"
        onClick={handleExport}
        disabled={exportCollectionXmp.isPending}
      >
        Export collection to XMP
      </button>
      {message && <span> {message}</span>}
    </div>
  );
}

function CollectionMembers({
  collectionId,
}: {
  collectionId: string;
}): React.JSX.Element {
  const { data, isLoading } = useCollectionMembers(collectionId);

  if (isLoading || !data) {
    return <p>Loading members...</p>;
  }
  if (data.photo_ids.length === 0) {
    return <p>No photos in this collection yet.</p>;
  }

  return (
    <ul
      style={{
        display: "flex",
        flexWrap: "wrap",
        gap: 8,
        listStyle: "none",
        padding: 0,
      }}
    >
      {data.photo_ids.map((photoId) => (
        <li key={photoId}>
          <Link to={`/photo/${photoId}`}>
            <img
              src={thumbnailUrl(photoId, "grid")}
              alt={photoId}
              width={120}
              height={120}
              style={{ objectFit: "cover" }}
            />
          </Link>
        </li>
      ))}
    </ul>
  );
}

/**
 * Minimal list/create/view UI for virtual and smart collections (TASK-073,
 * TASK-074, SDD §4.8). Adding photos to a virtual collection happens from
 * the Photo Detail page -- multi-select bulk-add from the grid is
 * TASK-081's scope, not this one's. "Quick filters" (TASK-080) are
 * one-click presets that create a live smart collection from a built-in
 * SearchQuery instead of requiring a manual search first.
 */
export function CollectionsPage(): React.JSX.Element {
  const { data, isLoading } = useCollections();
  const createCollection = useCreateCollection();
  const [name, setName] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const handleCreate = (): void => {
    const trimmed = name.trim();
    if (!trimmed) {
      return;
    }
    createCollection.mutate({ name: trimmed });
    setName("");
  };

  if (isLoading || !data) {
    return <p>Loading collections...</p>;
  }

  return (
    <div>
      <h1>Collections</h1>
      <QuickFilters />
      <div>
        <input
          type="text"
          aria-label="New collection name"
          value={name}
          onChange={(event) => setName(event.target.value)}
        />
        <button type="button" onClick={handleCreate}>
          Create
        </button>
      </div>
      <ul>
        {data.items.map((collection) => (
          <li key={collection.id}>
            <button type="button" onClick={() => setSelectedId(collection.id)}>
              {collection.name}
            </button>{" "}
            ({collection.item_count} photos)
          </li>
        ))}
      </ul>
      {selectedId && (
        <>
          <ExportCollectionXmpButton collectionId={selectedId} />
          <CollectionMembers collectionId={selectedId} />
        </>
      )}
    </div>
  );
}
