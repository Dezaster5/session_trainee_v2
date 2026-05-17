export function formatPercent(value) {
  return `${Number(value || 0).toFixed(1)}%`;
}

export function formatDate(value) {
  if (!value) return "Нет данных";
  return new Intl.DateTimeFormat("ru-RU", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

export function modeLabel(mode) {
  const labels = {
    random: "Умный микс",
    new: "Новые",
    mistakes: "Ошибки",
    hard: "Сложные",
    rare: "Редкие",
    review_all: "Повторение",
    spaced: "Spaced repetition",
  };
  return labels[mode] || mode;
}
