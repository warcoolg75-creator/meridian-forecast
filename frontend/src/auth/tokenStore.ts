/**
 * The access token lives here, in memory only: never localStorage, sessionStorage or a
 * script-readable cookie. A reload drops it; the httpOnly refresh cookie restores it.
 */
let accessToken: string | null = null;

export function getAccessToken(): string | null {
  return accessToken;
}

export function setAccessToken(token: string | null): void {
  accessToken = token;
}
