"use client";

import { createContext, useContext } from "react";

export type Panel = "login" | "register" | null;

interface LandingAuthContextValue {
  openLogin: () => void;
  openRegister: () => void;
}

export const LandingAuthContext = createContext<LandingAuthContextValue>({
  openLogin: () => {},
  openRegister: () => {},
});

export function useLandingAuth() {
  return useContext(LandingAuthContext);
}
