import { useEffect, useState } from "react";
import { load, save } from "./storage";

export type Theme = "system" | "light" | "dark";
const KEY = "kk:theme";

function apply(theme: Theme) {
  const dark =
    theme === "dark" ||
    (theme === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.dataset.theme = dark ? "dark" : "light";
}

export function useTheme(): [Theme, (t: Theme) => void] {
  const [theme, setTheme] = useState<Theme>(() => load(KEY, "system"));
  useEffect(() => {
    apply(theme);
    save(KEY, theme);
    if (theme !== "system") return;
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => apply("system");
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, [theme]);
  return [theme, setTheme];
}

// Apply the saved theme before React renders, to avoid a flash.
apply(load<Theme>(KEY, "system"));
