import { useState } from "react";
import type React from "react";
import { Link } from "react-router-dom";

import type { DuplicateGroupSummary } from "../api/hooks";
import {
  useAddCollectionMembers,
  useCollections,
  useDuplicateGroups,
} from "../api/hooks";
import { thumbnailUrl } from "../api/thumbnailUrl";

function DuplicateGroupCard({
  group,
}: {
  group: DuplicateGroupSummary;
}): React.JSX.Element {
  const { data: collections } = useCollections();
  const addMembers = useAddCollectionMembers();
  const [selectedPhotoIds, setSelectedPhotoIds] = useState<Set<string>>(
    new Set(),
  );
  const [selectedCollectionId, setSelectedCollectionId] = useState("");
  const [added, setAdded] = useState(false);

  const toggle = (photoId: string): void => {
    setSelectedPhotoIds((previous) => {
      const next = new Set(previous);
      if (next.has(photoId)) {
        next.delete(photoId);
      } else {
        next.add(photoId);
      }
      return next;
    });
    setAdded(false);
  };

  const handleAdd = (): void => {
    if (!selectedCollectionId || selectedPhotoIds.size === 0) {
      return;
    }
    addMembers.mutate(
      {
        collectionId: selectedCollectionId,
        photoIds: [...selectedPhotoIds],
      },
      { onSuccess: () => setAdded(true) },
    );
  };

  return (
    <section>
      <ul
        style={{
          display: "flex",
          flexWrap: "wrap",
          gap: 8,
          listStyle: "none",
          padding: 0,
        }}
      >
        {group.members.map((member) => (
          <li key={member.photo_id}>
            <label>
              <input
                type="checkbox"
                aria-label={`Select ${member.photo_id}`}
                checked={selectedPhotoIds.has(member.photo_id)}
                onChange={() => toggle(member.photo_id)}
              />
              <Link to={`/photo/${member.photo_id}`}>
                <img
                  src={thumbnailUrl(member.photo_id, "grid")}
                  alt={member.photo_id}
                  width={120}
                  height={120}
                  style={{ objectFit: "cover" }}
                />
              </Link>
              {member.is_recommended_keeper && <span> Suggested keeper</span>}
            </label>
          </li>
        ))}
      </ul>
      <label>
        Add selected to collection
        <select
          aria-label="Add selected to collection"
          value={selectedCollectionId}
          onChange={(event) => {
            setSelectedCollectionId(event.target.value);
            setAdded(false);
          }}
        >
          <option value="">Choose a collection</option>
          {(collections?.items ?? []).map((collection) => (
            <option key={collection.id} value={collection.id}>
              {collection.name}
            </option>
          ))}
        </select>
      </label>
      <button
        type="button"
        onClick={handleAdd}
        disabled={!selectedCollectionId || selectedPhotoIds.size === 0}
      >
        Add selected
      </button>
      {added && <span> Added.</span>}
    </section>
  );
}

/**
 * Review UI for duplicate groups (TASK-076, SDD §10.2): `is_recommended_keeper`
 * (computed upstream by TASK-046) is shown only as a suggestion -- nothing
 * is preselected, including non-keeper members, so acting on a group
 * (adding chosen photos to a collection) always requires an explicit
 * per-photo selection first. v1 has no delete action (MVP scope overlay);
 * export is deferred until TASK-083/TASK-0D land.
 */
export function DuplicateReviewPage(): React.JSX.Element {
  const { data, isLoading } = useDuplicateGroups();

  if (isLoading || !data) {
    return <p>Loading duplicate groups...</p>;
  }

  return (
    <div>
      <h1>Duplicate Review</h1>
      {data.items.length === 0 ? (
        <p>No duplicate groups found.</p>
      ) : (
        data.items.map((group) => (
          <DuplicateGroupCard key={group.id} group={group} />
        ))
      )}
    </div>
  );
}
