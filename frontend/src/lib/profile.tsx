import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import type { BuyerProfile } from "./api";
import { load, save } from "./storage";

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
  const setProfile = (next: BuyerProfile) => {
    profileRef.current = next;
    updateProfile(next);
  };

  useEffect(() => {
    save(KEY, profile);
  }, [profile]);

  return (
    <ProfileContext.Provider value={{ profile, setProfile, profileRef }}>
      {children}
    </ProfileContext.Provider>
  );
}

export function useProfile(): ProfileContextValue {
  const ctx = useContext(ProfileContext);
  if (!ctx) throw new Error("useProfile must be used inside ProfileProvider");
  return ctx;
}
