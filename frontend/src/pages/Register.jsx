import { UserPlus } from "lucide-react";
import { useState } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";

import { useAuth } from "../context/AuthContext";

export default function Register() {
  const { register, isAuthenticated } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState({
    username: "",
    email: "",
    password: "",
    password2: "",
  });
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  if (isAuthenticated) return <Navigate to="/" replace />;

  async function handleSubmit(event) {
    event.preventDefault();
    setSubmitting(true);
    setError("");
    try {
      await register(form);
      navigate("/", { replace: true });
    } catch (requestError) {
      const data = requestError.response?.data;
      setError(data ? JSON.stringify(data) : "Не удалось создать аккаунт");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="auth-page">
      <section className="auth-panel">
        <div className="auth-brand">
          <UserPlus size={26} />
          <div>
            <strong>Exam Forge</strong>
            <span>Личный прогресс и статистика</span>
          </div>
        </div>

        <form onSubmit={handleSubmit} className="auth-form">
          <h1>Регистрация</h1>
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
            Email
            <input
              type="email"
              value={form.email}
              onChange={(event) => setForm({ ...form, email: event.target.value })}
              autoComplete="email"
            />
          </label>
          <label>
            Пароль
            <input
              type="password"
              value={form.password}
              onChange={(event) => setForm({ ...form, password: event.target.value })}
              autoComplete="new-password"
              required
            />
          </label>
          <label>
            Повтор пароля
            <input
              type="password"
              value={form.password2}
              onChange={(event) => setForm({ ...form, password2: event.target.value })}
              autoComplete="new-password"
              required
            />
          </label>
          <button className="primary-button" type="submit" disabled={submitting}>
            <UserPlus size={18} />
            {submitting ? "Создаем" : "Создать аккаунт"}
          </button>
        </form>

        <p className="auth-switch">
          Уже есть аккаунт? <Link to="/login">Войти</Link>
        </p>
      </section>
    </main>
  );
}
