import { ArrowLeft, Brain, CheckCircle2, Clock3, Code2, Play, Shuffle, Target, Zap } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";

import api from "../api/client";
import LoadingState from "../components/LoadingState";

const modes = [
  ["random", "Умный микс", Shuffle, "Новые, слабые и обычные задачи"],
  ["new", "Новые", Zap, "Только задачи без попыток"],
  ["mistakes", "Слабые", Target, "Best similarity ниже порога"],
  ["hard", "Сложные", Brain, "Задачи с низким лучшим результатом"],
  ["rare", "Редкие", Clock3, "Задачи с минимумом попыток"],
  ["spaced", "Повторение", CheckCircle2, "Вернуть слабые задачи в работу"],
];

const counts = ["5", "10", "20", "50", "all", "custom"];

export default function LiveCodingSetup() {
  const { id } = useParams();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const requestedTopicId = Number(searchParams.get("topic"));
  const requestedMode = searchParams.get("mode") || "random";
  const [subject, setSubject] = useState(null);
  const [mode, setMode] = useState(modes.some(([value]) => value === requestedMode) ? requestedMode : "random");
  const [count, setCount] = useState("10");
  const [customCount, setCustomCount] = useState("10");
  const [selectedTopics, setSelectedTopics] = useState(
    Number.isInteger(requestedTopicId) && requestedTopicId > 0 ? [requestedTopicId] : []
  );
  const [loading, setLoading] = useState(true);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .get(`/subjects/${id}/`)
      .then((response) => setSubject(response.data))
      .catch(() => setError("Предмет не найден или недоступен"))
      .finally(() => setLoading(false));
  }, [id]);

  function toggleTopic(topicId) {
    setSelectedTopics((items) =>
      items.includes(topicId) ? items.filter((item) => item !== topicId) : [...items, topicId]
    );
  }

  async function startSession() {
    if (count === "custom") {
      const parsedCount = Number(customCount);
      if (!Number.isInteger(parsedCount) || parsedCount < 1 || parsedCount > 200) {
        setError("Укажите количество от 1 до 200");
        return;
      }
    }

    setStarting(true);
    setError("");
    try {
      const { data } = await api.post("/live-coding/start/", {
        subject_id: Number(id),
        mode,
        task_count: count === "custom" ? customCount : count,
        topic_ids: selectedTopics,
      });
      navigate(`/live-coding/${data.id}`);
    } catch (requestError) {
      setError(requestError.response?.data?.detail || "Не удалось начать live coding");
    } finally {
      setStarting(false);
    }
  }

  if (loading) return <LoadingState label="Подготовка live coding" />;
  const liveTopics = (subject?.topics || []).filter((topic) => topic.type === "live_coding" && topic.live_coding_count > 0);

  return (
    <div className="page-stack">
      <header className="page-header">
        <div>
          <Link to={`/subjects/${id}`} className="back-link">
            <ArrowLeft size={17} /> {subject?.name || "Предмет"}
          </Link>
          <h1>Live coding</h1>
          <span className="subtle">{subject?.live_coding_count || 0} задач с similarity-проверкой</span>
        </div>
      </header>

      <section className="setup-grid">
        <div className="panel setup-panel">
          <div className="panel-header">
            <h2>Количество</h2>
          </div>
          <div className="segmented">
            {counts.map((item) => (
              <button key={item} type="button" className={count === item ? "active" : ""} onClick={() => setCount(item)}>
                {item === "all" ? "Все" : item === "custom" ? "Свое" : item}
              </button>
            ))}
          </div>
          {count === "custom" ? (
            <label className="field-inline">
              Свое количество
              <input min="1" max="200" type="number" value={customCount} onChange={(event) => setCustomCount(event.target.value)} />
            </label>
          ) : null}
        </div>

        <div className="panel setup-panel">
          <div className="panel-header">
            <h2>Темы</h2>
            {selectedTopics.length ? (
              <button type="button" className="ghost-link" onClick={() => setSelectedTopics([])}>
                Сбросить
              </button>
            ) : null}
          </div>
          {liveTopics.length ? (
            <div className="topic-picker">
              {liveTopics.map((topic) => (
                <button
                  key={topic.id}
                  type="button"
                  className={selectedTopics.includes(topic.id) ? "topic-chip active" : "topic-chip"}
                  onClick={() => toggleTopic(topic.id)}
                >
                  <strong>{topic.title}</strong>
                  <span>{topic.live_coding_count} задач</span>
                </button>
              ))}
            </div>
          ) : (
            <div className="empty-state state compact-state">
              <strong>Live coding задач нет</strong>
              <span>Импортируйте JSON-базу с секцией liveCoding.</span>
            </div>
          )}
        </div>

        <div className="panel setup-panel">
          <div className="panel-header">
            <h2>Режим</h2>
          </div>
          <div className="mode-list">
            {modes.map(([value, label, Icon, description]) => (
              <button key={value} type="button" className={mode === value ? "mode-item active" : "mode-item"} onClick={() => setMode(value)}>
                <Icon size={18} />
                <span>
                  <strong>{label}</strong>
                  <small>{description}</small>
                </span>
              </button>
            ))}
          </div>
        </div>
      </section>

      {error ? <div className="form-error">{error}</div> : null}

      <button type="button" className="primary-button wide-action" onClick={startSession} disabled={starting || !subject?.live_coding_count}>
        <Code2 size={19} />
        {starting ? "Запускаем" : "Начать live coding"}
      </button>
    </div>
  );
}
