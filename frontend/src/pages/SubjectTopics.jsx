import { ArrowLeft, Code2, Layers3, Play } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import api from "../api/client";
import EmptyState from "../components/EmptyState";
import ErrorState from "../components/ErrorState";
import LoadingState from "../components/LoadingState";
import { formatPercent } from "../utils/format";

export default function SubjectTopics() {
  const { id } = useParams();
  const [subject, setSubject] = useState(null);
  const [topics, setTopics] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([api.get(`/subjects/${id}/`), api.get(`/subjects/${id}/topics/`)])
      .then(([subjectResponse, topicsResponse]) => {
        setSubject(subjectResponse.data);
        setTopics(topicsResponse.data);
      })
      .catch(() => setError("Не удалось загрузить темы"))
      .finally(() => setLoading(false));
  }, [id]);

  if (loading) return <LoadingState label="Загрузка тем" />;
  if (error) return <ErrorState title="Темы недоступны" text={error} />;

  return (
    <div className="page-stack">
      <header className="page-header">
        <div>
          <Link to={`/subjects/${id}`} className="back-link">
            <ArrowLeft size={17} /> {subject?.name || "Предмет"}
          </Link>
          <h1>Темы</h1>
          <span className="subtle">{topics.length} направлений для практики</span>
        </div>
      </header>

      {topics.length ? (
        <section className="topic-grid">
          {topics.map((topic) => (
            <article key={topic.id} className="topic-card">
              <div className="topic-head">
                <span className={`status-badge ${topic.type === "live_coding" ? "status-running" : "status-success"}`}>
                  {topic.type === "live_coding" ? "Live coding" : "Theory"}
                </span>
                <small>{formatPercent(topic.progress?.winrate || 0)}</small>
              </div>
              <h3>
                <Layers3 size={18} /> {topic.title}
              </h3>
              <div className="topic-metrics">
                <span>{topic.question_count} theory</span>
                <span>{topic.live_coding_count} coding</span>
                <span>{topic.progress?.unique_seen || 0} seen</span>
              </div>
              <div className="card-actions">
                {topic.question_count ? (
                  <Link className="secondary-button" to={`/subjects/${id}/test?topic=${topic.id}`}>
                    <Play size={17} /> Practice theory
                  </Link>
                ) : null}
                {topic.live_coding_count ? (
                  <Link className="primary-button" to={`/subjects/${id}/live-coding?topic=${topic.id}`}>
                    <Code2 size={17} /> Live coding
                  </Link>
                ) : null}
              </div>
            </article>
          ))}
        </section>
      ) : (
        <EmptyState title="Тем нет" text="Для PDF-баз без тем используйте общий тест предмета" />
      )}
    </div>
  );
}
