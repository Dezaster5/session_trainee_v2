import { ArrowLeft, BookOpen, Brain, CheckCircle2, Clock3, Play, Shuffle, Target, Zap } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";

import api from "../api/client";
import LoadingState from "../components/LoadingState";

const modes = [
  ["random", "Умный микс", Shuffle, "Баланс новых, сложных и обычных вопросов"],
  ["new", "Новые", Zap, "Только вопросы, которые еще не встречались"],
  ["mistakes", "Ошибки", Target, "Вопросы с неправильными ответами"],
  ["hard", "Сложные", Brain, "Низкий личный winrate и высокий вес"],
  ["rare", "Редкие", Clock3, "Вопросы, которые попадались редко"],
  ["spaced", "Повторение", CheckCircle2, "Приоритет прошлых ошибок и веса"],
  ["review_all", "Вся база", BookOpen, "Свободное повторение предмета"],
];

const modeValues = new Set(modes.map(([value]) => value));

const counts = ["5", "10", "20", "50", "all", "custom"];

export default function TestSetup() {
  const { id } = useParams();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const [subject, setSubject] = useState(null);
  const requestedMode = searchParams.get("mode") || "random";
  const [mode, setMode] = useState(modeValues.has(requestedMode) ? requestedMode : "random");
  const [count, setCount] = useState("10");
  const [customCount, setCustomCount] = useState("30");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [starting, setStarting] = useState(false);

  useEffect(() => {
    api
      .get(`/subjects/${id}/`)
      .then((response) => setSubject(response.data))
      .catch(() => setError("Предмет не найден или недоступен"))
      .finally(() => setLoading(false));
  }, [id]);

  async function startTest() {
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
      const { data } = await api.post("/tests/start/", {
        subject_id: Number(id),
        mode,
        question_count: count === "custom" ? customCount : count,
      });
      navigate(`/tests/${data.id}`);
    } catch (requestError) {
      setError(requestError.response?.data?.detail || "Не удалось начать тест");
    } finally {
      setStarting(false);
    }
  }

  if (loading) return <LoadingState label="Подготовка теста" />;
  if (!subject) {
    return (
      <div className="page-stack">
        <div className="form-error">{error || "Предмет недоступен"}</div>
      </div>
    );
  }

  return (
    <div className="page-stack">
      <header className="page-header">
        <div>
          <Link to={`/subjects/${id}`} className="back-link">
            <ArrowLeft size={17} /> {subject.name}
          </Link>
          <h1>Настройка теста</h1>
        </div>
        <div className="setup-summary">
          <strong>{subject.question_count}</strong>
          <span>вопросов в базе</span>
        </div>
      </header>

      <section className="setup-grid">
        <div className="panel setup-panel">
          <div className="panel-header">
            <h2>Количество</h2>
          </div>
          <div className="segmented">
            {counts.map((item) => (
              <button
                key={item}
                type="button"
                className={count === item ? "active" : ""}
                onClick={() => setCount(item)}
              >
                {item === "all" ? "Все" : item === "custom" ? "Свое" : item}
              </button>
            ))}
          </div>
          {count === "custom" ? (
            <label className="field-inline">
              Свое количество
              <input
                type="number"
                min="1"
                max="200"
                value={customCount}
                onChange={(event) => setCustomCount(event.target.value)}
              />
            </label>
          ) : null}
        </div>

        <div className="panel setup-panel">
          <div className="panel-header">
            <h2>Режим</h2>
          </div>
          <div className="mode-list">
            {modes.map(([value, label, Icon, description]) => (
              <button
                key={value}
                type="button"
                className={mode === value ? "mode-item active" : "mode-item"}
                onClick={() => setMode(value)}
              >
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

      <button type="button" className="primary-button wide-action" onClick={startTest} disabled={starting}>
        <Play size={19} />
        {starting ? "Запускаем" : "Начать"}
      </button>
    </div>
  );
}
