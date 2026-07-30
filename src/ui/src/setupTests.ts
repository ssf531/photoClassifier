import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// @testing-library/react's automatic cleanup only self-registers when it
// detects a global `afterEach` (e.g. vitest's `globals: true`), which this
// project doesn't enable -- without this, DOM from one test in a file leaks
// into the next, causing spurious "multiple elements found" failures for
// any two tests that render the same markup.
afterEach(() => {
  cleanup();
});
