import { ArrowLeft, CheckCircle2, Clock3, RotateCcw, Trophy, XCircle } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import api from "../api/client";
import EmptyState from "../components/EmptyState";
import ErrorState from "../components/ErrorState";
import LoadingState from "../components/LoadingState";
import StatCard from "../components/StatCard";
import { AnswerExplanation, QuestionImage } from "../components/QuestionMedia";
import { formatPercent, modeLabel } from "../utils/format";

export default function TestResult() {
  const { id } = useParams();
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .get(`/tests/${id}/result/`)
      .then((response) => setResult(response.data))
      .catch(() => setError("Не удалось загрузить результат"))
      .finally(() => setLoading(false));
  }, [id]);

  if (loading) return <LoadingState label="Загрузка результата" />;
  if (error) return <ErrorState title="Результат недоступен" text={error} />;
  if (!result) return <EmptyState title="Результат не найден" text="Сессия недоступна" />;

  const answered = result.correct_count + result.wrong_count;
  const resultTone = result.winrate >= 80 ? "strong" : result.winrate >= 55 ? "steady" : "review";

  return (
    <div className="page-stack">
      <header className={`result-hero result-${resultTone}`}>
        <div>
          <Link to="/" className="back-link">
            <ArrowLeft size={17} /> Dashboard
          </Link>
          <h1>Результат теста</h1>
          <span className="subtle">
            {modeLabel(result.mode)} · {answered}/{result.total_questions} ответов
          </span>
        </div>
        <Link className="primary-button" to={`/subjects/${result.subject}/test`}>
          <RotateCcw size={18} /> Повторить
        </Link>
      </header>

      <section className="stats-grid">
        <StatCard label="Очки" value={result.score} icon={Trophy} tone="teal" />
        <StatCard label="Правильно" value={result.correct_count} icon={CheckCircle2} tone="green" />
        <StatCard label="Ошибки" value={result.wrong_count} icon={XCircle} tone="red" />
        <StatCard label="Winrate" value={formatPercent(result.winrate)} icon={CheckCircle2} tone="blue" />
        <StatCard label="Вопросы" value={`${answered}/${result.total_questions}`} icon={Clock3} tone="amber" />
      </section>

      <section className="panel">
        <div className="panel-header">
          <h2>Ответы</h2>
        </div>
        <div className="result-list">
          {result.answers.length ? result.answers.map((answer, index) => {
            const correct = answer.question.variants.find((variant) => variant.is_correct);
            return (
              <article key={answer.id} className={answer.is_correct ? "result-item ok" : "result-item bad"}>
                <div className="result-index">{index + 1}</div>
                <div>
                  <h3>{answer.question.text}</h3>
                  <QuestionImage src={answer.question.image} />
                  <p>Ваш ответ: {answer.selected_variant?.text || "Нет ответа"}</p>
                  {correct ? <p>Правильный ответ: {correct.text}</p> : null}
                  <AnswerExplanation
                    explanation={answer.question.explanation}
                    formula={answer.question.formula}
                  />
                  <small>{answer.points_awarded} очков</small>
                </div>
              </article>
            );
          }) : <EmptyState title="Ответов нет" text="В этой сессии не было отправленных ответов" />}
        </div>
      </section>
    </div>
  );
}
