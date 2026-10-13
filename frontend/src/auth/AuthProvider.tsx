import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";

import { AUTH_BASE, onSessionExpired, refreshSession } from "../api/client";
import { AuthContext, type AuthStatus, type LoginResult } from "./auth-context";
import { setAccessToken } from "./tokenStore";
import type { Session, User } from "./types";

type State = { status: AuthStatus; user: User | null };

const SIGNED_OUT: State = { status: "anonymous", user: null };

async function errorMessage(response: Response): Promise<string> {
  const body = (await response.json().catch(() => null)) as { detail?: unknown } | null;
  if (typeof body?.detail === "string") return body.detail;
  return response.status >= 500
    ? "Something went wrong on our side. Please try again."
    : "Sign-in failed. Please try again.";
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<State>({ status: "loading", user: null });

  useEffect(() => {
    let active = true;
    void refreshSession().then((session) => {
      if (active) setState(session ? { status: "authenticated", user: session.user } : SIGNED_OUT);
    });
    const unsubscribe = onSessionExpired(() => setState(SIGNED_OUT));
    return () => {
      active = false;
      unsubscribe();
    };
  }, []);

  const login = useCallback(
    async (email: string, password: string, remember: boolean): Promise<LoginResult> => {
      let response: Response;
      try {
        response = await fetch(`${AUTH_BASE}/login`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          credentials: "same-origin",
          body: JSON.stringify({ email, password, remember }),
        });
      } catch {
        return {
          ok: false,
          status: 0,
          message: "Can't reach the server. Check that the API is running.",
        };
      }
      if (!response.ok) {
        return { ok: false, status: response.status, message: await errorMessage(response) };
      }
      const session = (await response.json()) as Session;
      setAccessToken(session.access_token);
      setState({ status: "authenticated", user: session.user });
      return { ok: true };
    },
    [],
  );

  const logout = useCallback(async () => {
    try {
      await fetch(`${AUTH_BASE}/logout`, { method: "POST", credentials: "same-origin" });
    } catch {
      // Signed out locally either way; the server-side session expires on its own.
    } finally {
      setAccessToken(null);
      setState(SIGNED_OUT);
    }
  }, []);

  const value = useMemo(() => ({ ...state, login, logout }), [state, login, logout]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
