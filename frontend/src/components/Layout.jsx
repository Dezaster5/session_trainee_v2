import {
  BarChart3,
  BookOpen,
  ClipboardList,
  LogOut,
  Medal,
  Settings,
  Target,
  User,
} from "lucide-react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";

import { useAuth } from "../context/AuthContext";

const nav = [
  { to: "/", label: "Dashboard", icon: BarChart3 },
  { to: "/subjects", label: "Предметы", icon: BookOpen },
  { to: "/mistakes", label: "Ошибки", icon: Target },
  { to: "/leaderboard", label: "Leaderboard", icon: Medal },
  { to: "/profile", label: "Профиль", icon: User },
  { to: "/import", label: "Импорт", icon: Settings },
];

export default function Layout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  async function handleLogout() {
    await logout();
    navigate("/login");
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <ClipboardList size={24} />
          <div>
            <strong>Exam Forge</strong>
            <span>Question training by Miras</span>
          </div>
        </div>

        <nav>
          {nav.map((item) => {
            const Icon = item.icon;
            return (
              <NavLink key={item.to} to={item.to} end={item.to === "/"}>
                <Icon size={18} />
                <span>{item.label}</span>
              </NavLink>
            );
          })}
        </nav>

        <button type="button" className="user-chip" onClick={handleLogout}>
          <span>{user?.username?.[0]?.toUpperCase() || "U"}</span>
          <div>
            <strong>{user?.username}</strong>
            <small>Выйти</small>
          </div>
          <LogOut size={17} />
        </button>
      </aside>

      <main className="content">
        <Outlet />
      </main>
    </div>
  );
}
