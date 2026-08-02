import { Navigate, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import WorkerRoute from "./components/WorkerRoute";
import AdminRoute from "./components/AdminRoute";
import Login from "./pages/Login";
import AcceptInvite from "./pages/AcceptInvite";
import ForgotPassword from "./pages/ForgotPassword";
import ResetPassword from "./pages/ResetPassword";
import Rules from "./pages/Rules";
import Dictionary from "./pages/Dictionary";
import Pending from "./pages/Pending";
import Upload from "./pages/Upload";
import Library from "./pages/Library";
import Comparative from "./pages/Comparative";
import Commit from "./pages/Commit";
import Audit from "./pages/Audit";
import Users from "./pages/Users";
import { getToken } from "./api";

function PrivateRoute({ children }: { children: React.ReactNode }) {
  if (!getToken()) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/accept-invite" element={<AcceptInvite />} />
      <Route path="/forgot-password" element={<ForgotPassword />} />
      <Route path="/reset-password" element={<ResetPassword />} />
      <Route
        path="/"
        element={
          <PrivateRoute>
            <Layout />
          </PrivateRoute>
        }
      >
        <Route index element={<Navigate to="/rules" replace />} />
        <Route path="rules" element={<Rules />} />
        <Route path="dictionary" element={<Dictionary />} />
        <Route
          path="pending"
          element={
            <WorkerRoute>
              <Pending />
            </WorkerRoute>
          }
        />
        <Route
          path="upload"
          element={
            <WorkerRoute>
              <Upload />
            </WorkerRoute>
          }
        />
        <Route path="library" element={<Library />} />
        <Route path="comparative" element={<Comparative />} />
        <Route
          path="commit"
          element={
            <AdminRoute>
              <Commit />
            </AdminRoute>
          }
        />
        <Route
          path="audit"
          element={
            <AdminRoute>
              <Audit />
            </AdminRoute>
          }
        />
        <Route
          path="users"
          element={
            <AdminRoute>
              <Users />
            </AdminRoute>
          }
        />
      </Route>
    </Routes>
  );
}
