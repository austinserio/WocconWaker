export type PanelRole = "admin" | "worker" | "member" | "reviewer" | "viewer";

export function normalizeRole(role: string): PanelRole {
  if (role === "reviewer") return "worker";
  if (role === "viewer") return "member";
  return role as PanelRole;
}

export function canWrite(role: string): boolean {
  const r = normalizeRole(role);
  return r === "admin" || r === "worker";
}

export function isAdmin(role: string): boolean {
  return normalizeRole(role) === "admin";
}

export const ROLE_LABELS: Record<string, string> = {
  admin: "Admin",
  worker: "Community language worker",
  member: "Community member",
  reviewer: "Community language worker",
  viewer: "Community member",
};
