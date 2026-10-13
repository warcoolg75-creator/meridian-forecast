import { createContext, useContext } from "react";

import type { User } from "./types";

/** "loading" until the start-up refresh answers, so a reload never flashes the login page. */
export type AuthStatus = "loading" | "authenticated" | "anonymous";

export type LoginResult = { ok: true } | { ok: false; status: number; message: string };

export interface AuthValue {
  status: AuthStatus;
  user: User | null;
  login: (email: string, password: string, remember: boolean) => Promise<LoginResult>;
  logout: () => Promise<void>;
}

export const AuthContext = createContext<AuthValue | null>(null);

export function useAuth(): AuthValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside <AuthProvider>");
  return value;
}
