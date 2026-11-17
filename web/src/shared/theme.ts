// Every colour, size and duration in the console. CSS reads them as variables written once at start-up.
export const COLOUR = {
  ground: "#F1F3EF",     // ledger paper
  panel: "#FFFFFF",
  ink: "#15202B",
  muted: "#5E6B73",
  rule: "#D6DCD5",
  posted: "#1E6B52",     // cleared by the agent
  review: "#A86A12",     // a person decides
  fault: "#A63D40",      // wrong posting, blocked, error
  wash: "#E6ECE4",
  focus: "#2B5F8A",
} as const;

export const TYPE = { family: "'IBM Plex Sans Condensed', system-ui, sans-serif", small: 13, body: 15, lead: 18, title: 24, display: 36 } as const;
export const SPACE = { xs: 4, sm: 8, md: 16, lg: 24, xl: 40 } as const;
export const LAYOUT = { maxWidth: 1180, listWidth: 380, radius: 6, barHeight: 8 } as const;
export const MOTION = { fast: 0.18, base: 0.32, slow: 0.6, stagger: 0.05, ease: [0.2, 0.8, 0.2, 1] as [number, number, number, number] };

export function applyTheme(root: HTMLElement = document.documentElement): void {
  for (const [k, v] of Object.entries(COLOUR)) root.style.setProperty(`--${k}`, v);
  for (const [k, v] of Object.entries(SPACE)) root.style.setProperty(`--space-${k}`, `${v}px`);
  for (const k of ["small", "body", "lead", "title", "display"] as const) root.style.setProperty(`--type-${k}`, `${TYPE[k]}px`);
  root.style.setProperty("--family", TYPE.family);
  root.style.setProperty("--max-width", `${LAYOUT.maxWidth}px`);
  root.style.setProperty("--list-width", `${LAYOUT.listWidth}px`);
  root.style.setProperty("--radius", `${LAYOUT.radius}px`);
  root.style.setProperty("--bar", `${LAYOUT.barHeight}px`);
}
