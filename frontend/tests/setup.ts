import '@testing-library/jest-dom/vitest';

// JSDOM does not implement scrolling APIs that some components rely on.
if (!HTMLElement.prototype.scrollIntoView) {
  HTMLElement.prototype.scrollIntoView = () => {};
}

// Clipboard APIs are not available by default in JSDOM.
if (!('clipboard' in navigator)) {
  Object.defineProperty(navigator, 'clipboard', {
    value: {
      writeText: async () => {},
    },
    configurable: true,
  });
}

// matchMedia is commonly used by theming/responsive hooks.
if (!window.matchMedia) {
  window.matchMedia = (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  });
}

// Some UI libs rely on ResizeObserver being present.
if (!('ResizeObserver' in globalThis)) {
  class ResizeObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
  }

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  (globalThis as any).ResizeObserver = ResizeObserver;
}
