import { Inbox } from "lucide-react";

export default function EmptyState({ title = "Пусто", text = "Данных пока нет", action = null }) {
  return (
    <div className="state empty-state">
      <div className="state-icon">
        <Inbox size={28} />
      </div>
      <div>
        <strong>{title}</strong>
        <span>{text}</span>
      </div>
      {action}
    </div>
  );
}
