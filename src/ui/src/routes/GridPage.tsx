import { useMemo } from "react";
import type React from "react";
import { useNavigate } from "react-router-dom";

import { usePhotoList } from "../api/hooks";
import { PhotoGrid } from "../components/PhotoGrid";

export function GridPage(): React.JSX.Element {
  const { data, fetchNextPage, hasNextPage, isFetchingNextPage } =
    usePhotoList();
  const navigate = useNavigate();

  const photos = useMemo(
    () => data?.pages.flatMap((page) => page.items) ?? [],
    [data],
  );

  return (
    <div style={{ height: "100%" }}>
      <PhotoGrid
        photos={photos}
        onEndReached={() => {
          if (hasNextPage && !isFetchingNextPage) {
            void fetchNextPage();
          }
        }}
        onPhotoClick={(photo) => navigate(`/photo/${photo.id}`)}
      />
    </div>
  );
}
