import { NavLink, Outlet } from "react-router-dom";
import { api } from "../api/client";
import { useAuth } from "../context/AuthContext";
import { useAsync } from "../hooks/useAsync";

const NAV = [
  { to: "/", label: "Dashboard", icon: "▦", end: true },
  { to: "/leads", label: "Leads", icon: "☰" },
  { to: "/follow-ups", label: "Follow-ups", icon: "✉" },
  { to: "/properties", label: "Properties", icon: "⌂" },
  { to: "/chatbot", label: "AI chatbot", icon: "✦" },
  { to: "/analytics", label: "Analytics", icon: "▤", managerOnly: true },
];

export default function Layout() {
  const { user, logout, isManager } = useAuth();
  const overview = useAsync(() => api.overview(), []);
  const hasSynthetic = overview.data?.synthetic_leads > 0;

  return (
    <div className="flex min-h-screen">
      <aside className="hidden w-60 shrink-0 flex-col border-r border-slate-200 bg-white md:flex">
        <div className="px-5 py-5">
          <p className="text-lg font-semibold text-brand-700">EstateIQ</p>
          <p className="text-xs text-slate-500">AI sales intelligence</p>
        </div>
        <nav className="flex-1 space-y-1 px-3">
          {NAV.filter((item) => !item.managerOnly || isManager).map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                `flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition ${
                  isActive ? "bg-brand-50 text-brand-700" : "text-slate-600 hover:bg-slate-100"
                }`
              }
            >
              <span aria-hidden className="w-4 text-center">{item.icon}</span>
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="border-t border-slate-200 p-4 text-sm">
          <p className="font-medium text-slate-800">{user.full_name}</p>
          <p className="mb-2 text-xs capitalize text-slate-500">{user.role}</p>
          <button onClick={logout} className="text-xs font-medium text-brand-600 hover:underline">
            Sign out
          </button>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        {/* compact navigation on small screens */}
        <nav className="flex gap-1 overflow-x-auto border-b border-slate-200 bg-white px-3 py-2 md:hidden">
          {NAV.filter((item) => !item.managerOnly || isManager).map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) => `whitespace-nowrap rounded-md px-3 py-1.5 text-xs font-medium ${isActive ? "bg-brand-50 text-brand-700" : "text-slate-600"}`}
            >
              {item.label}
            </NavLink>
          ))}
          <button onClick={logout} className="ml-auto whitespace-nowrap px-3 text-xs text-brand-600">
            Sign out
          </button>
        </nav>

        {hasSynthetic && (
          <div className="border-b border-fuchsia-200 bg-fuchsia-50 px-6 py-2 text-xs text-fuchsia-800">
            <strong>Demo data:</strong> {overview.data.synthetic_leads} of {overview.data.total_leads} leads are
            synthetic (generated, not real customers). Metrics and predictions here are not real business performance.
          </div>
        )}
        <main className="mx-auto w-full max-w-7xl flex-1 p-4 md:p-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
