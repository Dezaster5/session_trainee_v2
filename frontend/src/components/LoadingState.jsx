export default function LoadingState({ label = "Загрузка" }) {
  return (
    <div className="state state-loading">
      <span className="spinner" />
      <strong>{label}</strong>
    </div>
  );
}
