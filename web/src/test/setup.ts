import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

// jsdom has no layout; layout animations call scrollTo while measuring.
window.scrollTo = () => {};
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
