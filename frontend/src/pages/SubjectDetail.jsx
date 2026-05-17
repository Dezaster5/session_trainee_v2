import { ArrowLeft, Brain, CheckCircle2, Play, Target, XCircle } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import api from "../api/client";
import LoadingState from "../components/LoadingState";
import ProgressBar from "../components/ProgressBar";
import StatCard from "../components/StatCard";
import { formatPercent } from "../utils/format";

export default function SubjectDetail() {
  const { id } = useParams();
  const [subject, setSubject] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .get(`/subjects/${id}/`)
      .then((response) => setSubject(response.data))
      .finally(() => setLoading(false));
  }, [id]);

  if (loading) return <LoadingState label="Загрузка предмета" />;

  const stats = subject.user_stats || {};
  const completion = subject.question_count
    ? (stats.unique_questions_seen * 100) / subject.question_count
    : 0;

  return (
    <div className="page-stack">
      <header className="page-header">
        <div>
          <Link to="/subjects" className="back-link">
            <ArrowLeft size={17} /> Предметы
          </Link>
          <h1>{subject.name}</h1>
        </div>
        <Link className="primary-button" to={`/subjects/${subject.id}/test`}>
          <Play size={18} /> Начать тест
        </Link>
      </header>

      <section className="stats-grid">
        <StatCard label="Вопросов" value={subject.question_count} icon={Brain} tone="blue" />
        <StatCard label="Встречалось" value={stats.unique_questions_seen || 0} icon={Target} tone="teal" />
        <StatCard label="Правильно" value={stats.correct_answers || 0} icon={CheckCircle2} tone="green" />
        <StatCard label="Ошибки" value={stats.wrong_answers || 0} icon={XCircle} tone="red" />
      </section>

      <section className="panel">
        <div className="panel-header">
          <h2>Личный прогресс</h2>
          <strong>{formatPercent(completion)}</strong>
        </div>
        <ProgressBar value={stats.unique_questions_seen || 0} max={subject.question_count} />
        <div className="detail-grid">
          <div>
            <span>Ответов всего</span>
            <strong>{stats.total_answered || 0}</strong>
          </div>
          <div>
            <span>Winrate</span>
            <strong>{formatPercent(stats.winrate)}</strong>
          </div>
          <div>
            <span>Очки</span>
            <strong>{stats.points || 0}</strong>
          </div>
          <div>
            <span>Осталось новых</span>
            <strong>{Math.max((subject.question_count || 0) - (stats.unique_questions_seen || 0), 0)}</strong>
          </div>
        </div>
      </section>
    </div>
  );
}
