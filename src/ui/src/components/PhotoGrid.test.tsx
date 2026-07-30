// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { PhotoSummary } from "../api/hooks";
import { PhotoGrid } from "./PhotoGrid";

window.__LAUNCH_TOKEN__ = "test-token";

function makePhotos(count: number): PhotoSummary[] {
  return Array.from({ length: count }, (_, i) => ({
    id: `photo-${i}`,
    relative_path: `photo-${i}.jpg`,
    captured_at_utc: null,
  }));
}

// jsdom has no layout engine: @tanstack/react-virtual reads the scroll
// container's measured size via offsetWidth/offsetHeight (falling back to
// them even before any ResizeObserver callback fires), neither of which
// jsdom computes from real layout, so both need a manual stand-in for the
// virtualizer to compute a non-empty visible range at all.
function mockViewportHeight(px: number): void {
  class StubResizeObserver {
    observe(): void {}
    unobserve(): void {}
    disconnect(): void {}
  }
  vi.stubGlobal("ResizeObserver", StubResizeObserver);

  Object.defineProperty(HTMLElement.prototype, "offsetHeight", {
    configurable: true,
    value: px,
  });
  Object.defineProperty(HTMLElement.prototype, "offsetWidth", {
    configurable: true,
    value: 800,
  });
}

describe("PhotoGrid", () => {
  it("renders far fewer DOM nodes than the total item count (windowed rendering)", () => {
    mockViewportHeight(600);

    render(<PhotoGrid photos={makePhotos(100_000)} />);

    const renderedImages = screen.getAllByRole("img");
    expect(renderedImages.length).toBeGreaterThan(0);
    expect(renderedImages.length).toBeLessThan(200);
  });

  it("does not call onEndReached while far from the last row", () => {
    mockViewportHeight(600);
    const onEndReached = vi.fn();

    render(
      <PhotoGrid photos={makePhotos(100_000)} onEndReached={onEndReached} />,
    );

    expect(onEndReached).not.toHaveBeenCalled();
  });

  it("calls onEndReached once the visible range reaches the last row", () => {
    mockViewportHeight(600);
    const onEndReached = vi.fn();

    // 10 photos at 5 columns = 2 rows total, comfortably within one viewport.
    render(<PhotoGrid photos={makePhotos(10)} onEndReached={onEndReached} />);

    expect(onEndReached).toHaveBeenCalled();
  });
});
