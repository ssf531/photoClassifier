import type React from "react";
import { useParams } from "react-router-dom";

import { PhotoDetail } from "../components/PhotoDetail";

export function PhotoDetailRoute(): React.JSX.Element {
  const { photoId } = useParams<{ photoId: string }>();
  if (!photoId) {
    return <p>No photo selected.</p>;
  }
  return <PhotoDetail photoId={photoId} />;
}
