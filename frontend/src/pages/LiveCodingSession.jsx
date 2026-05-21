import { ArrowLeft, CheckCircle2, Code2, Play, Send, Trophy } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import api from "../api/client";
import ErrorState from "../components/ErrorState";
import LoadingState from "../components/LoadingState";
import ProgressBar from "../components/ProgressBar";
import { formatPercent } from "../utils/format";

const statusLabels = {
  excellent: "Excellent",
  good: "Good",
  needs_practice: "Needs practice",
  wrong: "Needs review",
};

export default function LiveCodingSession() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [session, setSession] = useState(null);
  const [code, setCode] = useState("");
  const [attempt, setAttempt] = useState(null);
  const [loading, setLoading] = useState(true);
  const [checking, setChecking] = useState(false);
  const [error, setError] = useState("");
  const [startedAt, setStartedAt] = useState(Date.now());

  useEffect(() => {
    api
      .get(`/live-coding/${id}/`)
      .then((response) => {
        setSession(response.data);
        setStartedAt(Date.now());
      })
      .catch(() => setError("Не удалось открыть live coding session"))
      .finally(() => setLoading(false));
  }, [id]);

  const current = session?.current_task;
  const task = current?.task;
  const progress = useMemo(() => {
    if (!session?.total_tasks) return 0;
    return (session.answered_count * 100) / session.total_tasks;
  }, [session]);

  async function submitAnswer() {
    if (!task) return;
    setChecking(true);
    setError("");
    try {
      const { data } = await api.post(`/live-coding/${id}/submit/`, {
        task_id: task.id,
        submitted_code: code,
        time_spent: Math.round((Date.now() - startedAt) / 1000),
      });
      setAttempt(data.attempt);
      setSession(data.session);
    } catch (requestError) {
      setError(requestError.response?.data?.detail || "Не удалось проверить ответ");
    } finally {
      setChecking(false);
    }
  }

  function nextTask() {
    if (session?.current_task) {
      setCode("");
      setAttempt(null);
      setStartedAt(Date.now());
      return;
    }
    navigate(`/live-coding/${id}/result`);
  }

  if (loading) return <LoadingState label="Загрузка задачи" />;
  if (error && !session) return <ErrorState title="Live coding недоступен" text={error} />;
  if (!task && !attempt) {
    return (
      <ErrorState
        title="Задач нет"
        text="В этой сессии нет доступной следующей задачи"
        action={<Link className="primary-button" to={`/live-coding/${id}/result`}>К результату</Link>}
      />
    );
  }

  const visibleTask = attempt?.task || task;
  const similarity = attempt?.similarity_score || 0;

  return (
    <div className="page-stack live-session">
      <header className="test-header">
        <div>
          <Link to={`/subjects/${session.subject.id}/live-coding`} className="back-link">
            <ArrowLeft size={17} /> Live coding
          </Link>
          <h1>{session.subject.name}</h1>
          <span>
            Задача {current?.order || session.answered_count} из {session.total_tasks}
          </span>
        </div>
        <div className="test-metrics">
          <span className="score-pill neutral">
            <Trophy size={17} /> {session.score} pts
          </span>
          <span className="score-pill">
            <CheckCircle2 size={17} /> {formatPercent(session.average_similarity)}
          </span>
        </div>
      </header>

      <div className="test-progress">
        <ProgressBar value={progress} max={100} />
        <span>{session.answered_count}/{session.total_tasks}</span>
      </div>

      {error ? <div className="form-error">{error}</div> : null}

      <section className="live-coding-grid">
        <article className="panel live-task-panel">
          <div className="task-badges">
            <span>{visibleTask.topic?.title || "General"}</span>
            <span>{visibleTask.language}</span>
            {visibleTask.difficulty ? <span>{visibleTask.difficulty}</span> : null}
          </div>
          <h2>{visibleTask.title}</h2>
          <p>{visibleTask.prompt}</p>
        </article>

        <article className="panel editor-panel">
          <div className="panel-header">
            <h2><Code2 size={18} /> Ответ</h2>
          </div>
          <textarea
            className="code-editor"
            value={code}
            onChange={(event) => setCode(event.target.value)}
            spellCheck="false"
            placeholder="Напишите команду или код здесь..."
            disabled={Boolean(attempt)}
          />
          <button type="button" className="primary-button wide-action" onClick={submitAnswer} disabled={checking || Boolean(attempt)}>
            <Send size={18} />
            {checking ? "Проверка" : "Check answer"}
          </button>
        </article>
      </section>

      {attempt ? (
        <section className={`feedback live-feedback ${attempt.status}`}>
          <div>
            <strong>{statusLabels[attempt.status] || attempt.status}</strong>
            <span>{attempt.feedback}</span>
            <span>Similarity: {formatPercent(similarity)} · Points: {attempt.points_awarded}</span>
          </div>
          <button type="button" className="primary-button" onClick={nextTask}>
            <Play size={18} /> {session.current_task ? "Next task" : "Finish session"}
          </button>
        </section>
      ) : null}

      {attempt ? (
        <section className="comparison-grid">
          <div className="panel">
            <div className="panel-header">
              <h2>Submitted</h2>
            </div>
            <pre className="code-block">{attempt.submitted_code || "No answer"}</pre>
          </div>
          <div className="panel">
            <div className="panel-header">
              <h2>Expected solution</h2>
            </div>
            <pre className="code-block">{attempt.expected_solution}</pre>
          </div>
        </section>
      ) : null}
    </div>
  );
}
