import { Navigate, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import Login from "./pages/Login";
import Rules from "./pages/Rules";
import Dictionary from "./pages/Dictionary";
import Pending from "./pages/Pending";
import Upload from "./pages/Upload";
import Library from "./pages/Library";
import Commit from "./pages/Commit";
import Audit from "./pages/Audit";
import { getToken } from "./api";

function PrivateRoute({ children }: { children: React.ReactNode }) {
  if (!getToken()) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
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
        <Route path="pending" element={<Pending />} />
        <Route path="upload" element={<Upload />} />
        <Route path="library" element={<Library />} />
        <Route path="commit" element={<Commit />} />
        <Route path="audit" element={<Audit />} />
      </Route>
    </Routes>
  );
}
