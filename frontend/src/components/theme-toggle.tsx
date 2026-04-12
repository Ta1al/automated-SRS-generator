"use client";

import { useEffect, useState } from "react";

type Theme = "light" | "dark";
type ToggleSize = "sm" | "md";

const STORAGE_KEY = "asg-theme";

function getSystemTheme(): Theme {
  if (typeof window === "undefined") {
    return "light";
  }

  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function applyTheme(theme: Theme) {
  document.documentElement.setAttribute("data-theme", theme);
}

export function ThemeToggle({ size = "md" }: { size?: ToggleSize }) {
  // Keep server and first client render identical to avoid hydration mismatches.
  const [theme, setTheme] = useState<Theme>("light");

  useEffect(() => {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    const initialTheme = stored === "light" || stored === "dark" ? stored : getSystemTheme();
    applyTheme(initialTheme);
    const initialSyncFrame = window.requestAnimationFrame(() => {
      setTheme(initialTheme);
    });

    const mediaQuery = window.matchMedia("(prefers-color-scheme: dark)");

    const onSystemThemeChange = (event: MediaQueryListEvent) => {
      const saved = window.localStorage.getItem(STORAGE_KEY);
      if (saved === "light" || saved === "dark") {
        return;
      }

      const nextTheme: Theme = event.matches ? "dark" : "light";
      setTheme(nextTheme);
      applyTheme(nextTheme);
    };

    const onStorageChange = (event: StorageEvent) => {
      if (event.key !== STORAGE_KEY) {
        return;
      }

      const nextTheme: Theme =
        event.newValue === "light" || event.newValue === "dark"
          ? event.newValue
          : getSystemTheme();
      setTheme(nextTheme);
      applyTheme(nextTheme);
    };

    mediaQuery.addEventListener("change", onSystemThemeChange);
    window.addEventListener("storage", onStorageChange);

    return () => {
      window.cancelAnimationFrame(initialSyncFrame);
      mediaQuery.removeEventListener("change", onSystemThemeChange);
      window.removeEventListener("storage", onStorageChange);
    };
  }, []);

  const baseClasses =
    size === "sm"
      ? "h-8 rounded-full px-3 text-xs"
      : "h-9 rounded-full px-3.5 text-xs";

  return (
    <button
      type="button"
      onClick={() => {
        const nextTheme = theme === "dark" ? "light" : "dark";
        setTheme(nextTheme);
        applyTheme(nextTheme);
        window.localStorage.setItem(STORAGE_KEY, nextTheme);
      }}
      className={`${baseClasses} inline-flex items-center gap-2 border border-[color:var(--outline-variant)]/55 bg-[color:var(--surface-lowest)] text-[color:var(--foreground)] transition-colors hover:bg-[color:var(--surface-low)]`}
      aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}
      title={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}
      aria-pressed={theme === "dark"}
    >
      <span className="inline-block h-1.5 w-1.5 rounded-full bg-[color:var(--primary)]" />
      {theme === "dark" ? "Dark" : "Light"}
    </button>
  );
}