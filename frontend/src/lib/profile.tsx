import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import type { BuyerProfile } from "./api";
import { load, save } from "./storage";
import { profileChangeText } from "./profileChanges";

const KEY = "kk:profile";

export const emptyProfile: BuyerProfile = {
  citizenship: null,
  age: null,
  household_income: null,
  first_timer: null,
  subsidy_status: null,
  household_type: null,
};

type ProfileContextValue = {
  profile: BuyerProfile;
  setProfile: (p: BuyerProfile) => void;
  /** Always the latest profile; read by the chat adapter at send time. */
  profileRef: React.RefObject<BuyerProfile>;
  subscribeChanges: (listener: (text: string) => void) => () => void;
};

const ProfileContext = createContext<ProfileContextValue | null>(null);

export function ProfileProvider({ children }: { children: ReactNode }) {
  const [profile, updateProfile] = useState<BuyerProfile>(() => {
    const saved = { ...emptyProfile, ...load(KEY, emptyProfile) };
    if (!saved.subsidy_status && saved.first_timer !== null) {
      saved.subsidy_status = saved.first_timer ? "first_timer" : "second_timer";
    }
    return saved;
  });
  const profileRef = useRef(profile);
  const listeners = useRef(new Set<(text: string) => void>());
  const subscribeChanges = useCallback((listener: (text: string) => void) => {
    listeners.current.add(listener);
    return () => { listeners.current.delete(listener); };
  }, []);
  const setProfile = (next: BuyerProfile) => {
    const notice = profileChangeText(profileRef.current, next);
    profileRef.current = next;
    updateProfile(next);
    if (notice) listeners.current.forEach((listener) => listener(notice));
  };

  useEffect(() => {
    save(KEY, profile);
  }, [profile]);

  return (
    <ProfileContext.Provider value={{ profile, setProfile, profileRef, subscribeChanges }}>
      {children}
    </ProfileContext.Provider>
  );
}

export function useProfile(): ProfileContextValue {
  const ctx = useContext(ProfileContext);
  if (!ctx) throw new Error("useProfile must be used inside ProfileProvider");
  return ctx;
}
