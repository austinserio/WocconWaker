import { Navigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

export default function WorkerRoute({ children }: { children: React.ReactNode }) {
  const { canWrite } = useAuth();
  if (!canWrite) return <Navigate to="/dictionary" replace />;
  return <>{children}</>;
}
