import { ArrowLeft, Brain, CheckCircle2, Code2, Layers3, Play, Target, XCircle } from "lucide-react";
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
        <div className="card-actions">
          <Link className="secondary-button" to={`/subjects/${subject.id}/live-coding`}>
            <Code2 size={18} /> Live coding
          </Link>
          <Link className="primary-button" to={`/subjects/${subject.id}/test`}>
            <Play size={18} /> Начать тест
          </Link>
        </div>
      </header>

      <section className="stats-grid">
        <StatCard label="Вопросов" value={subject.question_count} icon={Brain} tone="blue" />
        <StatCard label="Live coding" value={subject.live_coding_count || 0} icon={Code2} tone="amber" />
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

      <section className="panel">
        <div className="panel-header">
          <h2><Layers3 size={18} /> Темы</h2>
          <Link to={`/subjects/${subject.id}/topics`} className="ghost-link">Все темы</Link>
        </div>
        {subject.topics?.length ? (
          <div className="topic-grid">
            {subject.topics.map((topic) => (
              <article key={topic.id} className="topic-card">
                <div className="topic-head">
                  <span className={`status-badge ${topic.type === "live_coding" ? "status-running" : "status-success"}`}>
                    {topic.type === "live_coding" ? "Live coding" : "Theory"}
                  </span>
                  <small>{topic.progress?.winrate ? `Winrate ${formatPercent(topic.progress.winrate)}` : "Новая тема"}</small>
                </div>
                <h3>{topic.title}</h3>
                <div className="topic-metrics">
                  <span>{topic.question_count} вопросов</span>
                  <span>{topic.live_coding_count} задач</span>
                  <span>{topic.progress?.unique_seen || 0} встречалось</span>
                </div>
                <div className="card-actions">
                  {topic.question_count ? (
                    <Link className="secondary-button" to={`/subjects/${subject.id}/test?topic=${topic.id}`}>
                      <Play size={17} /> Theory
                    </Link>
                  ) : null}
                  {topic.live_coding_count ? (
                    <Link className="primary-button" to={`/subjects/${subject.id}/live-coding?topic=${topic.id}`}>
                      <Code2 size={17} /> Code
                    </Link>
                  ) : null}
                </div>
              </article>
            ))}
          </div>
        ) : (
          <div className="empty-state state">
            <strong>Тем пока нет</strong>
            <span>PDF-вопросы без topic продолжают работать через общий тест.</span>
          </div>
        )}
      </section>
    </div>
  );
}
