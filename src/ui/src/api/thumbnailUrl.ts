import { getLaunchToken } from "./launchToken";

export type ThumbnailSize = "grid" | "preview";

/**
 * An <img src> can't set an Authorization header, so the launch token
 * travels as a query parameter here instead (the thumbnail route accepts
 * both -- see `make_bearer_or_query_token_dependency`).
 */
export function thumbnailUrl(
  photoId: string,
  size: ThumbnailSize = "grid",
): string {
  return `/api/v1/thumbnails/${photoId}?size=${size}&token=${encodeURIComponent(getLaunchToken())}`;
}
