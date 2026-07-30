import type React from "react";

import type { AiResultSummary } from "../api/hooks";
import { usePhotoDetail } from "../api/hooks";
import { thumbnailUrl } from "../api/thumbnailUrl";

export interface PhotoDetailProps {
  photoId: string;
}

function CaptionResult({
  payload,
}: {
  payload: Record<string, unknown>;
}): React.JSX.Element {
  return <p>{String(payload.caption ?? "")}</p>;
}

function TagResult({
  payload,
}: {
  payload: Record<string, unknown>;
}): React.JSX.Element {
  const tags = Array.isArray(payload.tags)
    ? (payload.tags as { label: string }[])
    : [];
  return (
    <ul>
      {tags.map((tag) => (
        <li key={tag.label}>{tag.label}</li>
      ))}
    </ul>
  );
}

function QualityResult({
  payload,
}: {
  payload: Record<string, unknown>;
}): React.JSX.Element {
  return (
    <dl>
      <dt>Sharpness</dt>
      <dd>{String(payload.sharpness_variance ?? "unknown")}</dd>
      <dt>Blurry</dt>
      <dd>{payload.is_blurry ? "yes" : "no"}</dd>
    </dl>
  );
}

function AiResultPanel({
  result,
}: {
  result: AiResultSummary;
}): React.JSX.Element {
  switch (result.capability) {
    case "caption":
      return <CaptionResult payload={result.payload} />;
    case "tag":
      return <TagResult payload={result.payload} />;
    case "quality":
      return <QualityResult payload={result.payload} />;
    default:
      return <pre>{JSON.stringify(result.payload, null, 2)}</pre>;
  }
}

/**
 * Full preview + metadata + current AI-results panel for a single photo
 * (TASK-066). Renders whatever capabilities are actually present -- a photo
 * analyzed with none, some, or all enabled capabilities all render without
 * special-casing, matching the pipeline's per-capability fault isolation
 * (ADR-0004): a missing capability is just an absent entry in `ai_results`.
 */
export function PhotoDetail({ photoId }: PhotoDetailProps): React.JSX.Element {
  const { data, isLoading, isError } = usePhotoDetail(photoId);

  if (isLoading) {
    return <p>Loading...</p>;
  }
  if (isError || !data) {
    return <p>Photo not found.</p>;
  }

  return (
    <div>
      <img
        src={thumbnailUrl(photoId, "preview")}
        alt={data.relative_path}
        style={{ maxWidth: "100%" }}
      />
      <h2>{data.relative_path}</h2>
      <dl>
        <dt>Camera</dt>
        <dd>
          {data.camera_make ?? "unknown"} {data.camera_model ?? ""}
        </dd>
        <dt>Dimensions</dt>
        <dd>
          {data.width ?? "?"} x {data.height ?? "?"}
        </dd>
      </dl>
      <section>
        <h3>AI results</h3>
        {data.ai_results.length === 0 ? (
          <p>Not analyzed yet.</p>
        ) : (
          data.ai_results.map((result) => (
            <AiResultPanel key={result.capability} result={result} />
          ))
        )}
      </section>
    </div>
  );
}
