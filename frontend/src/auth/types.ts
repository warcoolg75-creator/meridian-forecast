export type Role = "admin" | "planner" | "analyst" | "viewer";

export interface User {
  id: number;
  email: string;
  full_name: string;
  role: Role;
  last_login_at: string | null;
}

/** POST /api/v1/auth/login and /refresh. The refresh token is an httpOnly cookie, not here. */
export interface Session {
  access_token: string;
  token_type: "bearer";
  expires_in: number;
  user: User;
}
