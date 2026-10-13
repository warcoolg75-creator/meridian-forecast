import type { Session } from "../auth/types";
import { getAccessToken, setAccessToken } from "../auth/tokenStore";

export const AUTH_BASE = "/api/v1/auth";
// A 401 from these means "not signed in" itself; refreshing and retrying makes no sense.
const NO_RETRY = new Set([`${AUTH_BASE}/login`, `${AUTH_BASE}/refresh`, `${AUTH_BASE}/logout`]);

const expiredListeners = new Set<() => void>();

/** Called when a refresh fails mid-session: the user is signed out. Returns an unsubscribe. */
export function onSessionExpired(listener: () => void): () => void {
  expiredListeners.add(listener);
  return () => expiredListeners.delete(listener);
}

let refreshing: Promise<Session | null> | null = null;

/**
 * Exchange the httpOnly refresh cookie for a new session (and a rotated cookie).
 * Concurrent callers share one request: each refresh token works once, so two parallel
 * refreshes would look like a replayed token and end the session (React's StrictMode
 * runs the start-up effect twice in development).
 */
export function refreshSession(): Promise<Session | null> {
  refreshing ??= (async () => {
    try {
      const response = await fetch(`${AUTH_BASE}/refresh`, {
        method: "POST",
        credentials: "same-origin",
      });
      if (!response.ok) {
        setAccessToken(null);
        return null;
      }
      const session = (await response.json()) as Session;
      setAccessToken(session.access_token);
      return session;
    } catch {
      setAccessToken(null);
      return null;
    } finally {
      refreshing = null;
    }
  })();
  return refreshing;
}

/** fetch for the API: sends the access token and, on a 401, refreshes once and retries. */
export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const send = () => {
    const headers = new Headers(init.headers);
    const token = getAccessToken();
    if (token) headers.set("Authorization", `Bearer ${token}`);
    return fetch(path, { ...init, headers, credentials: "same-origin" });
  };
  const response = await send();
  if (response.status !== 401 || NO_RETRY.has(path)) return response;
  const session = await refreshSession();
  if (!session) {
    for (const listener of expiredListeners) listener();
    return response;
  }
  return send();
}
