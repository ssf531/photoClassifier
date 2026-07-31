import { useState } from "react";
import type React from "react";
import { Link } from "react-router-dom";

import {
  useCollectionMembers,
  useCollections,
  useCreateCollection,
} from "../api/hooks";
import { thumbnailUrl } from "../api/thumbnailUrl";

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
 * Minimal list/create/view UI for virtual collections (TASK-073, SDD §4.8).
 * Adding photos to a collection happens from the Photo Detail page --
 * multi-select bulk-add from the grid is TASK-081's scope, not this one's.
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
    createCollection.mutate(trimmed);
    setName("");
  };

  if (isLoading || !data) {
    return <p>Loading collections...</p>;
  }

  return (
    <div>
      <h1>Collections</h1>
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
      {selectedId && <CollectionMembers collectionId={selectedId} />}
    </div>
  );
}
