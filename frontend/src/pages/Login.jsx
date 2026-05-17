import { LogIn } from "lucide-react";
import { useState } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";

import { useAuth } from "../context/AuthContext";

export default function Login() {
  const { login, isAuthenticated } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [form, setForm] = useState({ username: "", password: "" });
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  if (isAuthenticated) return <Navigate to="/" replace />;

  async function handleSubmit(event) {
    event.preventDefault();
    setSubmitting(true);
    setError("");
    try {
      await login(form.username, form.password);
      navigate(location.state?.from?.pathname || "/", { replace: true });
    } catch {
      setError("Неверный логин или пароль");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="auth-page">
      <section className="auth-panel">
        <div className="auth-brand">
          <LogIn size={26} />
          <div>
            <strong>Exam Forge</strong>
            <span>Подготовка к экзаменам</span>
          </div>
        </div>

        <form onSubmit={handleSubmit} className="auth-form">
          <h1>Вход</h1>
          {error ? <div className="form-error">{error}</div> : null}
          <label>
            Username
            <input
              value={form.username}
              onChange={(event) => setForm({ ...form, username: event.target.value })}
              autoComplete="username"
              required
            />
          </label>
          <label>
            Пароль
            <input
              type="password"
              value={form.password}
              onChange={(event) => setForm({ ...form, password: event.target.value })}
              autoComplete="current-password"
              required
            />
          </label>
          <button className="primary-button" type="submit" disabled={submitting}>
            <LogIn size={18} />
            {submitting ? "Входим" : "Войти"}
          </button>
        </form>

        <p className="auth-switch">
          Нет аккаунта? <Link to="/register">Создать</Link>
        </p>
      </section>
    </main>
  );
}
