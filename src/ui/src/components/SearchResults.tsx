import type React from "react";
import { useNavigate } from "react-router-dom";

import type { SearchResultItem } from "../api/hooks";
import { PhotoGrid } from "./PhotoGrid";

export interface SearchResultsProps {
  results: SearchResultItem[];
}

/**
 * Ranked results grid reusing the TASK-065 virtualized grid (TASK-068).
 * `results` is rendered exactly as received -- PhotoGrid windows over
 * whatever order its `photos` array is in, and this component never sorts
 * it, so the server's rank order (POST /api/v1/search) is what the user
 * actually sees, all the way through.
 */
export function SearchResults({
  results,
}: SearchResultsProps): React.JSX.Element {
  const navigate = useNavigate();
  const photos = results.map((result) => ({
    id: result.id,
    relative_path: result.relative_path,
    captured_at_utc: result.captured_at_utc,
  }));

  return (
    <PhotoGrid
      photos={photos}
      onPhotoClick={(photo) => navigate(`/photo/${photo.id}`)}
    />
  );
}
