import { createContext, useContext, useMemo, type ReactNode } from "react";
import { User } from "../api";
import { canWrite, isAdmin, normalizeRole } from "../utils/roles";

interface AuthContextValue {
  user: User | null;
  canWrite: boolean;
  isAdmin: boolean;
  role: string;
}

const AuthContext = createContext<AuthContextValue>({
  user: null,
  canWrite: false,
  isAdmin: false,
  role: "member",
});

export function AuthProvider({ user, children }: { user: User | null; children: ReactNode }) {
  const value = useMemo(() => {
    const role = user ? normalizeRole(user.role) : "member";
    return {
      user,
      canWrite: user ? canWrite(user.role) : false,
      isAdmin: user ? isAdmin(user.role) : false,
      role,
    };
  }, [user]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  return useContext(AuthContext);
}
