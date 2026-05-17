import { CalendarDays, CheckCircle2, Trophy, User, XCircle } from "lucide-react";
import { useEffect, useState } from "react";

import api from "../api/client";
import LoadingState from "../components/LoadingState";
import ProgressBar from "../components/ProgressBar";
import StatCard from "../components/StatCard";
import { formatDate, formatPercent } from "../utils/format";

export default function Profile() {
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .get("/progress/summary/")
      .then((response) => setSummary(response.data))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <LoadingState label="Загрузка профиля" />;

  const totals = summary.totals;

  return (
    <div className="page-stack">
      <header className="page-header">
        <div>
          <span className="eyebrow">Profile</span>
          <h1>{summary.user.username}</h1>
          <span className="subtle">Регистрация: {formatDate(summary.user.date_joined)}</span>
        </div>
      </header>

      <section className="stats-grid">
        <StatCard label="Решено" value={totals.total_answered} icon={User} tone="blue" />
        <StatCard label="Правильно" value={totals.correct_answers} icon={CheckCircle2} tone="green" />
        <StatCard label="Ошибки" value={totals.wrong_answers} icon={XCircle} tone="red" />
        <StatCard label="Winrate" value={formatPercent(totals.winrate)} icon={CalendarDays} tone="amber" />
        <StatCard label="Очки" value={totals.points} icon={Trophy} tone="teal" />
      </section>

      <section className="panel">
        <div className="panel-header">
          <h2>Предметы</h2>
        </div>
        <div className="subject-progress-list">
          {summary.subjects.map((subject) => (
            <div key={subject.subject_id} className="subject-row static">
              <div>
                <strong>{subject.subject_name}</strong>
                <span>
                  {subject.total_answered} ответов · {subject.points} очков
                </span>
              </div>
              <div className="subject-row-progress">
                <ProgressBar value={subject.unique_questions_seen} max={subject.question_count} />
                <small>{formatPercent(subject.completion_percent)}</small>
              </div>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
