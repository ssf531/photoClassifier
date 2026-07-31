import { useMemo, useState } from "react";
import type React from "react";
import { useNavigate } from "react-router-dom";

import type { PhotoSummary } from "../api/hooks";
import { usePhotoList } from "../api/hooks";
import { BatchActionToolbar } from "../components/BatchActionToolbar";
import { PhotoGrid } from "../components/PhotoGrid";

export function GridPage(): React.JSX.Element {
  const { data, fetchNextPage, hasNextPage, isFetchingNextPage } =
    usePhotoList();
  const navigate = useNavigate();
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());

  const photos = useMemo(
    () => data?.pages.flatMap((page) => page.items) ?? [],
    [data],
  );

  const toggleSelect = (photo: PhotoSummary): void => {
    setSelectedIds((previous) => {
      const next = new Set(previous);
      if (next.has(photo.id)) {
        next.delete(photo.id);
      } else {
        next.add(photo.id);
      }
      return next;
    });
  };

  return (
    <div style={{ height: "100%", display: "flex", flexDirection: "column" }}>
      {selectedIds.size > 0 && (
        <BatchActionToolbar
          photoIds={Array.from(selectedIds)}
          onClear={() => setSelectedIds(new Set())}
        />
      )}
      <div style={{ flex: 1, minHeight: 0 }}>
        <PhotoGrid
          photos={photos}
          onEndReached={() => {
            if (hasNextPage && !isFetchingNextPage) {
              void fetchNextPage();
            }
          }}
          onPhotoClick={(photo) => navigate(`/photo/${photo.id}`)}
          selectedIds={selectedIds}
          onToggleSelect={toggleSelect}
        />
      </div>
    </div>
  );
}
