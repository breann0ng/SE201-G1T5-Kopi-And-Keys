import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { load, save } from "./storage";

const KEY = "kk:dev-details";

type PrefsValue = { devDetails: boolean; setDevDetails: (on: boolean) => void };

const PrefsContext = createContext<PrefsValue | null>(null);

/** Viewer preferences. "Developer details" shows graph steps and SQL logs under answers. */
export function PrefsProvider({ children }: { children: ReactNode }) {
  const [devDetails, setDevDetails] = useState<boolean>(() => load(KEY, false));
  useEffect(() => save(KEY, devDetails), [devDetails]);
  return <PrefsContext.Provider value={{ devDetails, setDevDetails }}>{children}</PrefsContext.Provider>;
}

export function usePrefs(): PrefsValue {
  const ctx = useContext(PrefsContext);
  if (!ctx) throw new Error("usePrefs must be used inside PrefsProvider");
  return ctx;
}
