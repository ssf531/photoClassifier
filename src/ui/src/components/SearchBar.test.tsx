// @vitest-environment jsdom
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { SearchBar } from "./SearchBar";

describe("SearchBar", () => {
  it("produces one correctly-shaped SearchQuery from a combined text+filter interaction", () => {
    const onSubmit = vi.fn();
    render(<SearchBar onSubmit={onSubmit} />);

    fireEvent.change(screen.getByLabelText("Search text"), {
      target: { value: "beach sunset" },
    });
    fireEvent.change(screen.getByLabelText("Camera model"), {
      target: { value: "EOS R5" },
    });
    fireEvent.change(screen.getByLabelText("Min rating"), {
      target: { value: "4" },
    });
    fireEvent.change(screen.getByLabelText("From"), {
      target: { value: "2024-01-01" },
    });

    fireEvent.click(screen.getByRole("button", { name: "Search" }));

    expect(onSubmit).toHaveBeenCalledTimes(1);
    expect(onSubmit).toHaveBeenCalledWith({
      text: "beach sunset",
      filters: {
        date_range: { start: "2024-01-01", end: null },
        camera_model: "EOS R5",
        min_rating: 4,
        gps_bbox: undefined,
      },
      mode: "hybrid",
      limit: 100,
      offset: 0,
    });
  });

  it("defaults to metadata mode with no filters when the bar is submitted empty", () => {
    const onSubmit = vi.fn();
    render(<SearchBar onSubmit={onSubmit} />);

    fireEvent.click(screen.getByRole("button", { name: "Search" }));

    expect(onSubmit).toHaveBeenCalledWith({
      text: undefined,
      filters: undefined,
      mode: "metadata",
      limit: 100,
      offset: 0,
    });
  });
});
