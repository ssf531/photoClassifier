import { useState } from "react";
import type React from "react";

import type { SearchQueryRequest } from "../api/hooks";

export interface SearchBarProps {
  onSubmit: (query: SearchQueryRequest) => void;
}

interface FormState {
  text: string;
  dateStart: string;
  dateEnd: string;
  cameraModel: string;
  minRating: string;
  minLat: string;
  maxLat: string;
  minLon: string;
  maxLon: string;
}

const EMPTY_FORM: FormState = {
  text: "",
  dateStart: "",
  dateEnd: "",
  cameraModel: "",
  minRating: "",
  minLat: "",
  maxLat: "",
  minLon: "",
  maxLon: "",
};

function buildQuery(form: FormState): SearchQueryRequest {
  const dateRange =
    form.dateStart || form.dateEnd
      ? { start: form.dateStart || null, end: form.dateEnd || null }
      : undefined;

  const gpsBbox =
    form.minLat && form.maxLat && form.minLon && form.maxLon
      ? {
          min_lat: Number(form.minLat),
          max_lat: Number(form.maxLat),
          min_lon: Number(form.minLon),
          max_lon: Number(form.maxLon),
        }
      : undefined;

  const hasFilters = Boolean(
    dateRange || form.cameraModel || form.minRating || gpsBbox,
  );

  return {
    text: form.text || undefined,
    filters: hasFilters
      ? {
          date_range: dateRange,
          camera_model: form.cameraModel || undefined,
          min_rating: form.minRating ? Number(form.minRating) : undefined,
          gps_bbox: gpsBbox,
        }
      : undefined,
    mode: form.text.trim() ? "hybrid" : "metadata",
    limit: 100,
    offset: 0,
  };
}

/**
 * Unified search input + structured filter controls (TASK-067), producing
 * one SearchQuery-shaped payload per submission. Presentational only --
 * the parent route owns actually calling the search API, matching the
 * PhotoGrid/GridPage split (TASK-065).
 */
export function SearchBar({ onSubmit }: SearchBarProps): React.JSX.Element {
  const [form, setForm] = useState<FormState>(EMPTY_FORM);

  const set =
    (key: keyof FormState) => (event: React.ChangeEvent<HTMLInputElement>) =>
      setForm((prev) => ({ ...prev, [key]: event.target.value }));

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        onSubmit(buildQuery(form));
      }}
    >
      <input
        type="text"
        placeholder="Search photos"
        value={form.text}
        onChange={set("text")}
        aria-label="Search text"
      />
      <fieldset>
        <legend>Filters</legend>
        <label>
          From
          <input
            type="date"
            value={form.dateStart}
            onChange={set("dateStart")}
          />
        </label>
        <label>
          To
          <input type="date" value={form.dateEnd} onChange={set("dateEnd")} />
        </label>
        <label>
          Camera model
          <input
            type="text"
            value={form.cameraModel}
            onChange={set("cameraModel")}
          />
        </label>
        <label>
          Min rating
          <input
            type="number"
            min={1}
            max={5}
            value={form.minRating}
            onChange={set("minRating")}
          />
        </label>
        <label>
          Min latitude
          <input type="number" value={form.minLat} onChange={set("minLat")} />
        </label>
        <label>
          Max latitude
          <input type="number" value={form.maxLat} onChange={set("maxLat")} />
        </label>
        <label>
          Min longitude
          <input type="number" value={form.minLon} onChange={set("minLon")} />
        </label>
        <label>
          Max longitude
          <input type="number" value={form.maxLon} onChange={set("maxLon")} />
        </label>
      </fieldset>
      <button type="submit">Search</button>
    </form>
  );
}
