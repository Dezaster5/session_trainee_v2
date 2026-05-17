import { Medal, SlidersHorizontal, Trophy } from "lucide-react";
import { useEffect, useState } from "react";

import api from "../api/client";
import EmptyState from "../components/EmptyState";
import ErrorState from "../components/ErrorState";
import LoadingState from "../components/LoadingState";
import { formatPercent } from "../utils/format";

export default function Leaderboard() {
  const [subjects, setSubjects] = useState([]);
  const [subject, setSubject] = useState("");
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    api.get("/subjects/").then((response) => setSubjects(response.data));
  }, []);

  useEffect(() => {
    setLoading(true);
    setError("");
    const suffix = subject ? `?subject=${subject}` : "";
    api
      .get(`/leaderboard/${suffix}`)
      .then((response) => setRows(response.data))
      .catch(() => setError("Не удалось загрузить рейтинг"))
      .finally(() => setLoading(false));
  }, [subject]);

  const podium = rows.slice(0, 3);

  return (
    <div className="page-stack">
      <header className="page-header">
        <div>
          <span className="eyebrow">Leaderboard</span>
          <h1>Рейтинг</h1>
        </div>
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
      </section>

      {loading ? (
        <LoadingState label="Загрузка рейтинга" />
      ) : error ? (
        <ErrorState title="Рейтинг недоступен" text={error} />
      ) : rows.length ? (
        <>
          <section className="podium-grid">
            {podium.map((row) => (
              <article key={`podium-${row.rank}-${row.username}`} className={`podium-card rank-${row.rank}`}>
                <div className="podium-rank">
                  <Trophy size={20} />
                  {row.rank}
                </div>
                <strong>{row.username}</strong>
                <span>{row.points} очков</span>
                <small>{formatPercent(row.winrate)} · {row.unique_questions_seen} уникальных</small>
              </article>
            ))}
          </section>
          <section className="panel">
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Место</th>
                    <th>Пользователь</th>
                    <th>Очки</th>
                    <th>Решено</th>
                    <th>Winrate</th>
                    <th>Уникальные</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => (
                    <tr key={`${row.rank}-${row.username}`}>
                      <td>
                        <span className="rank-cell">
                          <Medal size={17} /> {row.rank}
                        </span>
                      </td>
                      <td>
                        <strong>{row.username}</strong>
                      </td>
                      <td>{row.points}</td>
                      <td>{row.total_answered}</td>
                      <td>{formatPercent(row.winrate)}</td>
                      <td>{row.unique_questions_seen}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </>
      ) : (
        <EmptyState title="Рейтинг пуст" text="Первые очки появятся после тестов" />
      )}
    </div>
  );
}
