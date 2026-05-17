import { Database, RefreshCw, UploadCloud } from "lucide-react";
import { useEffect, useState } from "react";

import api from "../api/client";
import EmptyState from "../components/EmptyState";
import LoadingState from "../components/LoadingState";
import { formatDate } from "../utils/format";

export default function ImportStatus() {
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");

  async function loadStatus() {
    const { data } = await api.get("/admin/import-status/");
    setStatus(data.latest);
  }

  useEffect(() => {
    loadStatus().finally(() => setLoading(false));
  }, []);

  async function runImport() {
    setRunning(true);
    setError("");
    try {
      const { data } = await api.post("/admin/import-questions/");
      setStatus(data.run);
    } catch (requestError) {
      if (requestError.response?.status === 403) {
        setError("Импорт доступен только администратору");
      } else {
        setError("Не удалось запустить импорт");
      }
    } finally {
      setRunning(false);
    }
  }

  if (loading) return <LoadingState label="Загрузка импорта" />;

  return (
    <div className="page-stack">
      <header className="page-header">
        <div>
          <span className="eyebrow">Import</span>
          <h1>Статус базы вопросов</h1>
        </div>
        <button type="button" className="primary-button" onClick={runImport} disabled={running}>
          {running ? <RefreshCw size={18} className="spin-icon" /> : <UploadCloud size={18} />}
          {running ? "Импорт" : "Запустить импорт"}
        </button>
      </header>

      {error ? <div className="form-error">{error}</div> : null}

      {status ? (
        <section className="panel">
          <div className="panel-header">
            <h2>
              <Database size={20} /> Последний импорт
            </h2>
            <strong className={`status-badge status-${status.status}`}>{status.status}</strong>
          </div>
          <div className="detail-grid">
            <div>
              <span>Предметы</span>
              <strong>{status.subjects_found}</strong>
            </div>
            <div>
              <span>PDF</span>
              <strong>{status.files_found}</strong>
            </div>
            <div>
              <span>Импортировано</span>
              <strong>{status.imported_questions}</strong>
            </div>
            <div>
              <span>Дубликаты</span>
              <strong>{status.duplicate_questions}</strong>
            </div>
            <div>
              <span>Пропущено</span>
              <strong>{status.skipped_questions}</strong>
            </div>
            <div>
              <span>Завершен</span>
              <strong>{formatDate(status.finished_at)}</strong>
            </div>
          </div>
          {status.errors?.length ? (
            <div className="error-log">
              {status.errors.map((item, index) => (
                <pre key={`${item}-${index}`}>{item}</pre>
              ))}
            </div>
          ) : null}
        </section>
      ) : (
        <EmptyState title="Импортов не было" text="Запустите management command или кнопку администратора" />
      )}
    </div>
  );
}
