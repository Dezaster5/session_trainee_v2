import { ArrowRight, CheckCircle2, Timer, Trophy, XCircle } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import api from "../api/client";
import LoadingState from "../components/LoadingState";
import ProgressBar from "../components/ProgressBar";
import { AnswerExplanation, QuestionImage } from "../components/QuestionMedia";

export default function TestSession() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [session, setSession] = useState(null);
  const [loading, setLoading] = useState(true);
  const [selectedVariant, setSelectedVariant] = useState(null);
  const [feedback, setFeedback] = useState(null);
  const [pendingSession, setPendingSession] = useState(null);
  const [lockedQuestion, setLockedQuestion] = useState(null);
  const [startedAt, setStartedAt] = useState(Date.now());
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .get(`/tests/${id}/`)
      .then((response) => {
        if (!response.data.current_question) {
          navigate(`/tests/${id}/result`, { replace: true });
          return;
        }
        setSession(response.data);
      })
      .finally(() => setLoading(false));
  }, [id, navigate]);

  const current = lockedQuestion || session?.current_question;
  const question = current?.question;
  const progressValue = useMemo(() => {
    if (!session) return 0;
    return feedback ? session.answered_count + 1 : session.answered_count;
  }, [session, feedback]);
  const progressPercent = session?.total_questions
    ? Math.round((progressValue * 100) / session.total_questions)
    : 0;

  async function submitAnswer(variantId) {
    if (!question || feedback || submitting) return;
    setSubmitting(true);
    setError("");
    setSelectedVariant(variantId);
    try {
      const seconds = Math.round((Date.now() - startedAt) / 1000);
      const { data } = await api.post(`/tests/${id}/answer/`, {
        question_id: question.id,
        selected_variant_id: variantId,
        time_spent: seconds,
      });
      setLockedQuestion(current);
      setFeedback(data.answer);
      setPendingSession(data.session);
    } catch (requestError) {
      setSelectedVariant(null);
      setError(requestError.response?.data?.detail || "Не удалось отправить ответ");
    } finally {
      setSubmitting(false);
    }
  }

  function continueTest() {
    if (!pendingSession?.current_question) {
      navigate(`/tests/${id}/result`);
      return;
    }
    setSession(pendingSession);
    setPendingSession(null);
    setFeedback(null);
    setLockedQuestion(null);
    setSelectedVariant(null);
    setStartedAt(Date.now());
  }

  if (loading) return <LoadingState label="Загрузка теста" />;
  if (!session || !question) return <LoadingState label="Открываем результат" />;

  return (
    <div className="test-page">
      <header className="test-header">
        <div>
          <span>{session.subject.name}</span>
          <h1>
            Вопрос {current.order} из {session.total_questions}
          </h1>
        </div>
        <div className="test-metrics">
          <div className="score-pill">
            <Trophy size={17} />
            {pendingSession?.score ?? session.score}
          </div>
          <div className="score-pill neutral">
            <Timer size={17} />
            {progressPercent}%
          </div>
        </div>
      </header>

      <div className="test-progress">
        <ProgressBar value={progressValue} max={session.total_questions} />
        <span>{progressValue}/{session.total_questions}</span>
      </div>

      {error ? <div className="form-error">{error}</div> : null}

      <section className="question-panel">
        <h2>{question.text}</h2>
        <QuestionImage src={question.image} />
        <div className="answers-list">
          {question.variants.map((variant) => {
            const letter = String.fromCharCode(65 + question.variants.findIndex((item) => item.id === variant.id));
            const isSelected = selectedVariant === variant.id;
            const isCorrect = feedback?.correct_variant?.id === variant.id;
            const isWrongSelected = feedback && isSelected && !feedback.is_correct;
            const className = [
              "answer-option",
              isSelected ? "selected" : "",
              isCorrect ? "correct" : "",
              isWrongSelected ? "wrong" : "",
            ]
              .filter(Boolean)
              .join(" ");

            return (
              <button
                key={variant.id}
                type="button"
                className={className}
                onClick={() => submitAnswer(variant.id)}
                disabled={Boolean(feedback) || submitting}
              >
                <b>{letter}</b>
                <span>{variant.text}</span>
                {isCorrect ? <CheckCircle2 size={20} /> : null}
                {isWrongSelected ? <XCircle size={20} /> : null}
              </button>
            );
          })}
        </div>
      </section>

      {feedback ? (
        <>
          <section className={feedback.is_correct ? "feedback correct" : "feedback wrong"}>
            <div>
              <strong>{feedback.is_correct ? "Правильно" : "Неправильно"}</strong>
              <span>
                {feedback.points_awarded >= 0 ? "+" : ""}
                {feedback.points_awarded} очков · встречалось {feedback.question_stats?.times_seen || 0} раз
              </span>
            </div>
            <button type="button" className="primary-button" onClick={continueTest}>
              {pendingSession?.current_question ? "Следующий" : "Результат"}
              <ArrowRight size={18} />
            </button>
          </section>
          {feedback.correct_variant ? (
            <p className="correct-answer-line">
              Правильный ответ: <strong>{feedback.correct_variant.text}</strong>
            </p>
          ) : null}
          <AnswerExplanation explanation={feedback.explanation} formula={feedback.formula} />
        </>
      ) : null}
    </div>
  );
}
