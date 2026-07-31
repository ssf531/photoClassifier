import { useVirtualizer } from "@tanstack/react-virtual";
import { useEffect, useRef } from "react";
import type React from "react";

import type { PhotoSummary } from "../api/hooks";
import { thumbnailUrl } from "../api/thumbnailUrl";

const ROW_HEIGHT_PX = 200;
const COLUMN_COUNT = 5;
const OVERSCAN_ROWS = 3;
const END_REACHED_ROW_THRESHOLD = 5;

export interface PhotoGridProps {
  photos: PhotoSummary[];
  onEndReached?: () => void;
  onPhotoClick?: (photo: PhotoSummary) => void;
  selectedIds?: Set<string>;
  onToggleSelect?: (photo: PhotoSummary) => void;
}

/**
 * Windowed rendering over `file`/thumbnail data (TASK-065): only the rows
 * intersecting the scroll viewport (plus a small overscan buffer) ever
 * mount, so the DOM node count stays bounded regardless of how many photos
 * the library has -- the property that makes a 100k-item grid scrollable
 * at all.
 */
export function PhotoGrid({
  photos,
  onEndReached,
  onPhotoClick,
  selectedIds,
  onToggleSelect,
}: PhotoGridProps): React.JSX.Element {
  const parentRef = useRef<HTMLDivElement>(null);
  const rowCount = Math.ceil(photos.length / COLUMN_COUNT);

  const rowVirtualizer = useVirtualizer({
    count: rowCount,
    getScrollElement: () => parentRef.current,
    estimateSize: () => ROW_HEIGHT_PX,
    overscan: OVERSCAN_ROWS,
  });

  const virtualRows = rowVirtualizer.getVirtualItems();
  const lastVisibleRowIndex = virtualRows[virtualRows.length - 1]?.index ?? -1;

  useEffect(() => {
    if (
      onEndReached &&
      rowCount > 0 &&
      lastVisibleRowIndex >= rowCount - END_REACHED_ROW_THRESHOLD
    ) {
      onEndReached();
    }
  }, [onEndReached, rowCount, lastVisibleRowIndex]);

  return (
    <div ref={parentRef} style={{ height: "100%", overflowY: "auto" }}>
      <div
        style={{
          height: rowVirtualizer.getTotalSize(),
          position: "relative",
          width: "100%",
        }}
      >
        {virtualRows.map((virtualRow) => {
          const startIndex = virtualRow.index * COLUMN_COUNT;
          const rowPhotos = photos.slice(startIndex, startIndex + COLUMN_COUNT);
          return (
            <div
              key={virtualRow.key}
              style={{
                position: "absolute",
                top: 0,
                left: 0,
                width: "100%",
                height: virtualRow.size,
                transform: `translateY(${virtualRow.start}px)`,
                display: "grid",
                gridTemplateColumns: `repeat(${COLUMN_COUNT}, 1fr)`,
              }}
            >
              {rowPhotos.map((photo) => (
                <div key={photo.id} style={{ position: "relative" }}>
                  <img
                    src={thumbnailUrl(photo.id)}
                    alt={photo.relative_path}
                    loading="lazy"
                    onClick={
                      onPhotoClick ? () => onPhotoClick(photo) : undefined
                    }
                    style={{
                      width: "100%",
                      height: "100%",
                      objectFit: "cover",
                      cursor: onPhotoClick ? "pointer" : undefined,
                    }}
                  />
                  {onToggleSelect && (
                    <input
                      type="checkbox"
                      aria-label={`Select ${photo.relative_path}`}
                      checked={selectedIds?.has(photo.id) ?? false}
                      onClick={(event) => event.stopPropagation()}
                      onChange={() => onToggleSelect(photo)}
                      style={{ position: "absolute", top: 4, left: 4 }}
                    />
                  )}
                </div>
              ))}
            </div>
          );
        })}
      </div>
    </div>
  );
}
