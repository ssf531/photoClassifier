import type React from "react";
import { Link } from "react-router-dom";

import type { Recommendation } from "../api/hooks";
import { useRecommendations } from "../api/hooks";
import { thumbnailUrl } from "../api/thumbnailUrl";

const CATEGORY_LABELS: Record<Recommendation["category"], string> = {
  screenshots: "Screenshots",
  low_quality: "Low quality",
  near_duplicates: "Near-duplicates",
};

function RecommendationSection({
  recommendation,
}: {
  recommendation: Recommendation;
}): React.JSX.Element {
  const label = CATEGORY_LABELS[recommendation.category];

  return (
    <section>
      <h2>
        {label} ({recommendation.photo_ids.length})
      </h2>
      {recommendation.photo_ids.length === 0 ? (
        <p>Nothing here yet.</p>
      ) : (
        <ul
          style={{
            display: "flex",
            flexWrap: "wrap",
            gap: 8,
            listStyle: "none",
            padding: 0,
          }}
        >
          {recommendation.photo_ids.map((photoId) => (
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
      )}
    </section>
  );
}

/**
 * Read-only suggestion view (TASK-075, SDD §10.2): "these N photos look
 * like screenshots," "these N are near-identical". Turning a suggestion
 * into an action (add to collection, review/select a keeper) is TASK-076/
 * TASK-081's scope, not this page's.
 */
export function RecommendationsPage(): React.JSX.Element {
  const { data, isLoading } = useRecommendations();

  if (isLoading || !data) {
    return <p>Loading recommendations...</p>;
  }

  return (
    <div>
      <h1>Recommendations</h1>
      {data.items.map((recommendation) => (
        <RecommendationSection
          key={recommendation.category}
          recommendation={recommendation}
        />
      ))}
    </div>
  );
}
