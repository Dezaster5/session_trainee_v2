import { AlertTriangle } from "lucide-react";

export default function ErrorState({ title = "Ошибка", text = "Не удалось загрузить данные", action = null }) {
  return (
    <div className="state error-state">
      <div className="state-icon">
        <AlertTriangle size={28} />
      </div>
      <div>
        <strong>{title}</strong>
        <span>{text}</span>
      </div>
      {action}
    </div>
  );
}
