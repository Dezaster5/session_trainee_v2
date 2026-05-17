import { ArrowRight, BookOpen, CalendarDays, Play, Users } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import api from "../api/client";
import EmptyState from "../components/EmptyState";
import ErrorState from "../components/ErrorState";
import LoadingState from "../components/LoadingState";
import ProgressBar from "../components/ProgressBar";
import { formatDate, formatPercent } from "../utils/format";

export default function Subjects() {
  const [subjects, setSubjects] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .get("/subjects/")
      .then((response) => setSubjects(response.data))
      .catch(() => setError("Не удалось загрузить предметы"))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <LoadingState label="Загрузка предметов" />;
  if (error) return <ErrorState title="Предметы недоступны" text={error} />;

  return (
    <div className="page-stack">
      <header className="page-header">
        <div>
          <span className="eyebrow">Subjects</span>
          <h1>Предметы</h1>
        </div>
        <Link className="secondary-button" to="/import">
          Статус импорта
        </Link>
      </header>

      {subjects.length ? (
        <section className="card-grid">
          {subjects.map((subject) => (
            <article className="subject-card" key={subject.id}>
              <div className="subject-card-top">
                <div className="card-icon">
                  <BookOpen size={22} />
                </div>
                <span>{formatPercent(subject.overall_completion_percent)}</span>
              </div>
              <h2>{subject.name}</h2>
              <div className="subject-card-metrics">
                <div>
                  <BookOpen size={17} />
                  <span>Вопросы</span>
                  <strong>{subject.question_count}</strong>
                </div>
                <div>
                  <Users size={17} />
                  <span>Студенты</span>
                  <strong>{subject.users_count}</strong>
                </div>
              </div>
              <ProgressBar value={subject.overall_completion_percent} max={100} />
              <div className="subject-card-foot">
                <CalendarDays size={16} />
                <small>{formatDate(subject.imported_at)}</small>
              </div>
              <div className="card-actions">
                <Link className="secondary-button" to={`/subjects/${subject.id}`}>
                  Детали <ArrowRight size={17} />
                </Link>
                <Link className="primary-button" to={`/subjects/${subject.id}/test`}>
                  <Play size={17} /> Тест
                </Link>
              </div>
            </article>
          ))}
        </section>
      ) : (
        <EmptyState title="Нет предметов" text="Запустите импорт из базы PDF" />
      )}
    </div>
  );
}
