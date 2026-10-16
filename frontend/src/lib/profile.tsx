import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import type { BuyerProfile } from "./api";
import { load, save } from "./storage";

const KEY = "kk:profile";

export const emptyProfile: BuyerProfile = {
  citizenship: null,
  age: null,
  household_income: null,
  first_timer: null,
};

type ProfileContextValue = {
  profile: BuyerProfile;
  setProfile: (p: BuyerProfile) => void;
  /** Always the latest profile; read by the chat adapter at send time. */
  profileRef: React.RefObject<BuyerProfile>;
};

const ProfileContext = createContext<ProfileContextValue | null>(null);

export function ProfileProvider({ children }: { children: ReactNode }) {
  const [profile, setProfile] = useState<BuyerProfile>(() => load(KEY, emptyProfile));
  const profileRef = useRef(profile);

  useEffect(() => {
    profileRef.current = profile;
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
