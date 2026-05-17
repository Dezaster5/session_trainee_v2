import {
  Activity,
  ArrowRight,
  CheckCircle2,
  Clock3,
  Play,
  Sparkles,
  Target,
  TrendingUp,
  Trophy,
  XCircle,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import api from "../api/client";
import EmptyState from "../components/EmptyState";
import ErrorState from "../components/ErrorState";
import LoadingState from "../components/LoadingState";
import ProgressBar from "../components/ProgressBar";
import StatCard from "../components/StatCard";
import { formatDate, formatPercent, modeLabel } from "../utils/format";

export default function Dashboard() {
  const navigate = useNavigate();
  const [summary, setSummary] = useState(null);
  const [subjects, setSubjects] = useState([]);
  const [leaders, setLeaders] = useState([]);
  const [selectedSubject, setSelectedSubject] = useState("");
  const [loading, setLoading] = useState(true);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState("");
  const [loadError, setLoadError] = useState("");

  useEffect(() => {
    setLoadError("");
    Promise.all([
      api.get("/progress/summary/"),
      api.get("/subjects/"),
      api.get("/leaderboard/"),
    ])
      .then(([summaryResponse, subjectsResponse, leaderboardResponse]) => {
        setSummary(summaryResponse.data);
        setSubjects(subjectsResponse.data);
        setLeaders(leaderboardResponse.data.slice(0, 5));
        const preferred = summaryResponse.data.last_subject?.id || subjectsResponse.data[0]?.id || "";
        setSelectedSubject(preferred);
      })
      .catch(() => setLoadError("Не удалось загрузить dashboard"))
      .finally(() => setLoading(false));
  }, []);

  const totals = summary?.totals || {};
  const chartData = useMemo(
    () =>
      (summary?.activity || []).map((item) => ({
        day: new Date(item.day).toLocaleDateString("ru-RU", { day: "2-digit", month: "2-digit" }),
        correct: item.correct_answers,
        wrong: item.wrong_answers,
        points: item.points,
      })),
    [summary]
  );
  const bestSubject = useMemo(() => {
    const rows = summary?.subjects || [];
    return [...rows].sort((a, b) => b.completion_percent - a.completion_percent)[0];
  }, [summary]);
  const repeatCount = summary?.today_better_repeat?.length || 0;

  async function quickStart() {
    if (!selectedSubject) return;
    setStarting(true);
    setError("");
    try {
      const { data } = await api.post("/tests/start/", {
        subject_id: selectedSubject,
        mode: "random",
        question_count: "10",
      });
      navigate(`/tests/${data.id}`);
    } catch (requestError) {
      setError(requestError.response?.data?.detail || "Не удалось запустить быстрый тест");
    } finally {
      setStarting(false);
    }
  }

  if (loading) return <LoadingState label="Загрузка dashboard" />;
  if (loadError) {
    return (
      <ErrorState
        title="Dashboard недоступен"
        text={loadError}
        action={
          <button type="button" className="secondary-button" onClick={() => window.location.reload()}>
            Повторить
          </button>
        }
      />
    );
  }

  return (
    <div className="page-stack">
      <header className="dashboard-hero">
        <div>
          <span className="eyebrow">Dashboard</span>
          <h1>Привет, {summary?.user?.username}</h1>
          <p>
            {bestSubject
              ? `${bestSubject.subject_name}: ${formatPercent(bestSubject.completion_percent)} базы уже встречалось`
              : "Выберите предмет и начните первую тренировку"}
          </p>
        </div>
        <div className="quick-start-card">
          <div className="quick-start-title">
            <Sparkles size={18} />
            <strong>Быстрый старт</strong>
          </div>
          <div className="quick-start">
            <select value={selectedSubject} onChange={(event) => setSelectedSubject(event.target.value)}>
              {subjects.map((subject) => (
                <option key={subject.id} value={subject.id}>
                  {subject.name}
                </option>
              ))}
            </select>
            <button type="button" className="primary-button" onClick={quickStart} disabled={!selectedSubject || starting}>
              <Play size={18} />
              {starting ? "Запуск" : "10 вопросов"}
            </button>
          </div>
          <span>{repeatCount ? `${repeatCount} вопросов лучше повторить сегодня` : "Нет срочных повторений"}</span>
        </div>
      </header>

      <section className="stats-grid">
        <StatCard label="Решено" value={totals.total_answered || 0} hint="ответов всего" icon={Activity} tone="blue" />
        <StatCard label="Правильно" value={totals.correct_answers || 0} hint="точных ответов" icon={CheckCircle2} tone="green" />
        <StatCard label="Ошибки" value={totals.wrong_answers || 0} hint="для повторения" icon={XCircle} tone="red" />
        <StatCard label="Winrate" value={formatPercent(totals.winrate)} hint="личная точность" icon={TrendingUp} tone="amber" />
        <StatCard label="Очки" value={totals.points || 0} hint="рейтинг" icon={Trophy} tone="teal" />
      </section>

      {error ? <div className="form-error">{error}</div> : null}

      <section className="dashboard-grid">
        <div className="panel span-2">
          <div className="panel-header">
            <h2>Прогресс по предметам</h2>
            <Link to="/subjects" className="ghost-link">
              Все <ArrowRight size={16} />
            </Link>
          </div>
          {summary?.subjects?.length ? (
            <div className="subject-progress-list">
              {summary.subjects.map((subject) => (
                <Link key={subject.subject_id} to={`/subjects/${subject.subject_id}`} className="subject-row">
                  <div>
                    <strong>{subject.subject_name}</strong>
                    <span>
                      {subject.unique_questions_seen}/{subject.question_count} вопросов
                    </span>
                  </div>
                  <div className="subject-row-progress">
                    <ProgressBar value={subject.unique_questions_seen} max={subject.question_count} />
                    <small>{formatPercent(subject.completion_percent)}</small>
                  </div>
                </Link>
              ))}
            </div>
          ) : (
            <EmptyState
              title="Предметов нет"
              text="Импортируйте базу вопросов"
              action={<Link className="secondary-button" to="/import">Импорт</Link>}
            />
          )}
        </div>

        <div className="panel">
          <div className="panel-header">
            <h2>Сегодня повторить</h2>
            <Link to="/mistakes" className="ghost-link">
              Ошибки <ArrowRight size={16} />
            </Link>
          </div>
          {summary?.today_better_repeat?.length ? (
            <div className="compact-list">
              {summary.today_better_repeat.map((item) => (
                <Link key={item.question.id} to={`/subjects/${item.subject_id}/test?mode=spaced`} className="compact-item">
                  <Target size={17} />
                  <span>{item.question.text}</span>
                  <small>{item.times_wrong} ошибок</small>
                </Link>
              ))}
            </div>
          ) : (
            <EmptyState title="Нет срочных повторений" text="Можно пройти новые вопросы" />
          )}
        </div>

        <div className="panel span-2">
          <div className="panel-header">
            <h2>Активность</h2>
          </div>
          <div className="chart-box">
            {chartData.length ? (
              <ResponsiveContainer width="100%" height={240}>
                <AreaChart data={chartData}>
                  <defs>
                    <linearGradient id="correct" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#0f9f8f" stopOpacity={0.26} />
                      <stop offset="95%" stopColor="#0f9f8f" stopOpacity={0} />
                    </linearGradient>
                    <linearGradient id="wrong" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#d64545" stopOpacity={0.22} />
                      <stop offset="95%" stopColor="#d64545" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="day" tickLine={false} axisLine={false} />
                  <YAxis tickLine={false} axisLine={false} allowDecimals={false} />
                  <Tooltip />
                  <Area type="monotone" dataKey="correct" stroke="#0f9f8f" fill="url(#correct)" />
                  <Area type="monotone" dataKey="wrong" stroke="#d64545" fill="url(#wrong)" />
                </AreaChart>
              </ResponsiveContainer>
            ) : (
              <EmptyState title="История пустая" text="Пройдите первый тест" />
            )}
          </div>
        </div>

        <div className="panel">
          <div className="panel-header">
            <h2>Mini leaderboard</h2>
            <Link to="/leaderboard" className="ghost-link">
              Рейтинг <ArrowRight size={16} />
            </Link>
          </div>
          {leaders.length ? (
            <div className="leader-list">
              {leaders.map((leader) => (
                <div key={`${leader.rank}-${leader.username}`} className="leader-row">
                  <b>{leader.rank}</b>
                  <span>{leader.username}</span>
                  <strong>{leader.points}</strong>
                  <small>{formatPercent(leader.winrate)}</small>
                </div>
              ))}
            </div>
          ) : (
            <EmptyState title="Рейтинг пуст" text="Очки появятся после ответов" />
          )}
        </div>

        <div className="panel">
          <div className="panel-header">
            <h2>Последние результаты</h2>
          </div>
          {summary?.recent_sessions?.length ? (
            <div className="compact-list">
              {summary.recent_sessions.map((session) => (
                <Link key={session.id} to={`/tests/${session.id}/result`} className="compact-item">
                  <Clock3 size={17} />
                  <span>
                    {session.subject} · {modeLabel(session.mode)}
                  </span>
                  <small>{formatDate(session.started_at)}</small>
                </Link>
              ))}
            </div>
          ) : (
            <EmptyState title="Тестов нет" text="Начните с быстрого теста" />
          )}
        </div>
      </section>
    </div>
  );
}
