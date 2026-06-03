import { FunctionSquare, Lightbulb } from "lucide-react";

export function QuestionImage({ src, alt = "Иллюстрация к вопросу" }) {
  if (!src) return null;
  return (
    <figure className="question-image">
      <img src={src} alt={alt} loading="lazy" />
    </figure>
  );
}

export function AnswerExplanation({ explanation, formula }) {
  if (!explanation && !formula) return null;
  return (
    <div className="answer-review">
      {explanation ? (
        <div className="explanation-block">
          <span className="review-label">
            <Lightbulb size={16} /> Пояснение
          </span>
          <p>{explanation}</p>
        </div>
      ) : null}
      {formula ? (
        <div className="formula-block">
          <span className="review-label">
            <FunctionSquare size={16} /> Формула
          </span>
          <code>{formula}</code>
        </div>
      ) : null}
    </div>
  );
}
