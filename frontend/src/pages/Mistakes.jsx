import { Check, Code2, Play, SlidersHorizontal, Target } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import api from "../api/client";
import EmptyState from "../components/EmptyState";
import ErrorState from "../components/ErrorState";
import LoadingState from "../components/LoadingState";
import { AnswerExplanation, QuestionImage } from "../components/QuestionMedia";
import { formatDate, formatPercent } from "../utils/format";

export default function Mistakes() {
  const navigate = useNavigate();
  const [subjects, setSubjects] = useState([]);
  const [mistakes, setMistakes] = useState([]);
  const [liveWeak, setLiveWeak] = useState([]);
  const [activeTab, setActiveTab] = useState("theory");
  const [subject, setSubject] = useState("");
  const [ordering, setOrdering] = useState("-last_wrong_at");
  const [loading, setLoading] = useState(true);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    api.get("/subjects/").then((response) => setSubjects(response.data));
  }, []);

  useEffect(() => {
    setLoading(true);
    setError("");
    const params = new URLSearchParams();
    if (subject) params.set("subject", subject);
    if (ordering) params.set("ordering", ordering);
    api
      .get(`/progress/mistakes/?${params.toString()}`)
      .then((response) => setMistakes(response.data))
      .catch(() => setError("Не удалось загрузить ошибки"))
      .finally(() => setLoading(false));
  }, [subject, ordering]);

  useEffect(() => {
    const params = new URLSearchParams();
    if (subject) params.set("subject", subject);
    params.set("ordering", ordering === "-last_wrong_at" ? "-last_attempt_at" : ordering);
    api
      .get(`/progress/live-coding/mistakes/?${params.toString()}`)
      .then((response) => setLiveWeak(response.data))
      .catch(() => setLiveWeak([]));
  }, [subject, ordering]);

  async function markMastered(questionId) {
    try {
      await api.post(`/progress/questions/${questionId}/mark-mastered/`);
      setMistakes((items) =>
        items.map((item) =>
          item.question.id === questionId ? { ...item, is_mastered: true, personal_weight: 0.35 } : item
        )
      );
    } catch {
      setError("Не удалось отметить вопрос как усвоенный");
    }
  }

  async function startMistakes() {
    if (!subject) return;
    if (activeTab === "live") {
      navigate(`/subjects/${subject}/live-coding?mode=mistakes`);
      return;
    }
    setStarting(true);
    setError("");
    try {
      const { data } = await api.post("/tests/start/", {
        subject_id: subject,
        mode: "mistakes",
        question_count: "20",
      });
      navigate(`/tests/${data.id}`);
    } catch (requestError) {
      setError(requestError.response?.data?.detail || "Не удалось запустить тест по ошибкам");
    } finally {
      setStarting(false);
    }
  }

  return (
    <div className="page-stack">
      <header className="page-header">
        <div>
          <span className="eyebrow">Mistakes</span>
          <h1>Работа над ошибками</h1>
          <span className="subtle">
            {mistakes.length} theory · {liveWeak.length} live coding
          </span>
        </div>
        <button type="button" className="primary-button" onClick={startMistakes} disabled={!subject || starting}>
          <Play size={18} />
          {starting ? "Запуск" : activeTab === "live" ? "Live coding" : "Тест по ошибкам"}
        </button>
      </header>

      <section className="toolbar">
        <SlidersHorizontal size={18} />
        <select value={subject} onChange={(event) => setSubject(event.target.value)}>
          <option value="">Все предметы</option>
          {subjects.map((item) => (
            <option key={item.id} value={item.id}>
              {item.name}
            </option>
          ))}
        </select>
        <select value={ordering} onChange={(event) => setOrdering(event.target.value)}>
          <option value="-last_wrong_at">Последняя ошибка</option>
          <option value="-times_wrong">Больше ошибок</option>
          <option value="-personal_weight">Сложность</option>
        </select>
      </section>

      <section className="segmented tabs">
        <button type="button" className={activeTab === "theory" ? "active" : ""} onClick={() => setActiveTab("theory")}>
          Theory mistakes
        </button>
        <button type="button" className={activeTab === "live" ? "active" : ""} onClick={() => setActiveTab("live")}>
          Live coding weak tasks
        </button>
      </section>

      {loading ? (
        <LoadingState label="Загрузка ошибок" />
      ) : error ? (
        <ErrorState title="Ошибки недоступны" text={error} />
      ) : activeTab === "theory" && mistakes.length ? (
        <section className="mistake-list">
          {mistakes.map((item) => (
            <article key={item.question.id} className="mistake-card">
              <div className="mistake-head">
                <Target size={19} />
                <span>{item.subject}</span>
                {item.is_mastered ? <b>Усвоен</b> : null}
              </div>
              <h2>{item.question.text}</h2>
              <QuestionImage src={item.question.image} />
              <AnswerExplanation
                explanation={item.question.explanation}
                formula={item.question.formula}
              />
              <div className="mistake-meta">
                <span>Ошибки: {item.times_wrong}</span>
                <span>Winrate: {formatPercent(item.personal_winrate)}</span>
                <span>Последняя: {formatDate(item.last_wrong_at)}</span>
              </div>
              <div className="card-actions">
                <Link className="secondary-button" to={`/subjects/${item.subject_id}/test?mode=mistakes`}>
                  <Play size={17} /> Практика
                </Link>
                <button type="button" className="secondary-button" onClick={() => markMastered(item.question.id)}>
                  <Check size={17} /> Усвоен
                </button>
              </div>
            </article>
          ))}
        </section>
      ) : activeTab === "live" && liveWeak.length ? (
        <section className="mistake-list">
          {liveWeak.map((item) => (
            <article key={item.task.id} className="mistake-card">
              <div className="mistake-head">
                <Code2 size={19} />
                <span>{item.subject}</span>
                {item.is_solved ? <b>Solved</b> : null}
              </div>
              <h2>{item.task.title}</h2>
              <p className="subtle">{item.task.prompt}</p>
              <div className="mistake-meta">
                <span>Best: {formatPercent(item.best_similarity)}</span>
                <span>Last: {formatPercent(item.last_similarity)}</span>
                <span>Attempts: {item.attempts_count}</span>
              </div>
              <div className="card-actions">
                <Link
                  className="primary-button"
                  to={`/subjects/${item.subject_id}/live-coding?mode=mistakes${item.topic?.id ? `&topic=${item.topic.id}` : ""}`}
                >
                  <Play size={17} /> Repeat
                </Link>
              </div>
            </article>
          ))}
        </section>
      ) : (
        <EmptyState
          title={activeTab === "theory" ? "Ошибок нет" : "Слабых live coding задач нет"}
          text={activeTab === "theory" ? "Ошибочные вопросы появятся после тестов" : "Live coding задачи появятся после попыток ниже solved-порога"}
        />
      )}
    </div>
  );
}
