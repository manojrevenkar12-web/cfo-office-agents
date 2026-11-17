import "@fontsource/ibm-plex-sans-condensed/400.css";
import "@fontsource/ibm-plex-sans-condensed/500.css";
import "@fontsource/ibm-plex-sans-condensed/600.css";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./app/App";
import "./shared/theme.css";
import { applyTheme } from "./shared/theme";

applyTheme();
createRoot(document.getElementById("root")!).render(<StrictMode><App /></StrictMode>);
