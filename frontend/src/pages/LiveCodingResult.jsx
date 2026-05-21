import { ArrowLeft, CheckCircle2, Code2, RotateCcw, Trophy } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import api from "../api/client";
import ErrorState from "../components/ErrorState";
import LoadingState from "../components/LoadingState";
import StatCard from "../components/StatCard";
import { formatPercent } from "../utils/format";

const statusLabels = {
  excellent: "Excellent",
  good: "Good",
  needs_practice: "Needs practice",
  wrong: "Needs review",
};

export default function LiveCodingResult() {
  const { id } = useParams();
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .get(`/live-coding/${id}/result/`)
      .then((response) => setResult(response.data))
      .catch(() => setError("Не удалось загрузить результат"))
      .finally(() => setLoading(false));
  }, [id]);

  if (loading) return <LoadingState label="Загрузка результата" />;
  if (error) return <ErrorState title="Результат недоступен" text={error} />;

  const solved = result.attempts.filter((item) => item.similarity_score >= 80).length;

  return (
    <div className="page-stack">
      <header className="result-hero result-strong">
        <div>
          <Link to={`/subjects/${result.subject.id}`} className="back-link">
            <ArrowLeft size={17} /> {result.subject.name}
          </Link>
          <h1>Live coding result</h1>
          <p>{solved}/{result.total_tasks} задач достигли solved-порога</p>
        </div>
        <div className="quick-start-card">
          <strong>{formatPercent(result.average_similarity)}</strong>
          <span>Средняя similarity</span>
          <Link className="primary-button" to={`/subjects/${result.subject.id}/live-coding?mode=spaced`}>
            <RotateCcw size={18} /> Повторить
          </Link>
        </div>
      </header>

      <section className="stats-grid">
        <StatCard label="Score" value={result.score} icon={Trophy} tone="teal" />
        <StatCard label="Attempts" value={result.attempts.length} icon={Code2} tone="blue" />
        <StatCard label="Solved" value={solved} icon={CheckCircle2} tone="green" />
      </section>

      <section className="panel">
        <div className="panel-header">
          <h2>Детализация</h2>
        </div>
        <div className="result-list">
          {result.attempts.map((attempt, index) => (
            <article key={attempt.id} className={`result-item ${attempt.similarity_score >= 80 ? "ok" : "bad"}`}>
              <span className="result-index">{index + 1}</span>
              <div>
                <h3>{attempt.task.title}</h3>
                <p>{statusLabels[attempt.status]} · {formatPercent(attempt.similarity_score)} · {attempt.points_awarded} pts</p>
                <p>{attempt.feedback}</p>
                <details>
                  <summary>Expected solution</summary>
                  <pre className="code-block">{attempt.expected_solution}</pre>
                </details>
              </div>
            </article>
          ))}
        </div>
      </section>
    </div>
  );
}
