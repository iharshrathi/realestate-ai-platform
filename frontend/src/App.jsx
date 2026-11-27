import { Navigate, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import { Spinner } from "./components/ui";
import { useAuth } from "./context/AuthContext";
import Analytics from "./pages/Analytics";
import Chatbot from "./pages/Chatbot";
import Dashboard from "./pages/Dashboard";
import FollowUps from "./pages/FollowUps";
import LeadDetail from "./pages/LeadDetail";
import Leads from "./pages/Leads";
import Login from "./pages/Login";
import Properties from "./pages/Properties";

/** Everything except /login needs a signed-in user. */
function RequireAuth({ managerOnly = false, children }) {
  const { user, loading, isManager } = useAuth();
  if (loading) return <Spinner label="Restoring session…" />;
  if (!user) return <Navigate to="/login" replace />;
  if (managerOnly && !isManager) return <Navigate to="/" replace />;
  return children;
}

export default function App() {
  const { user } = useAuth();
  return (
    <Routes>
      <Route path="/login" element={user ? <Navigate to="/" replace /> : <Login />} />
      <Route
        element={
          <RequireAuth>
            <Layout />
          </RequireAuth>
        }
      >
        <Route index element={<Dashboard />} />
        <Route path="leads" element={<Leads />} />
        <Route path="leads/:id" element={<LeadDetail />} />
        <Route path="follow-ups" element={<FollowUps />} />
        <Route path="properties" element={<Properties />} />
        <Route path="chatbot" element={<Chatbot />} />
        <Route
          path="analytics"
          element={
            <RequireAuth managerOnly>
              <Analytics />
            </RequireAuth>
          }
        />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
