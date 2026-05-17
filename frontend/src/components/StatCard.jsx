export default function StatCard({ label, value, hint, icon: Icon, tone = "neutral" }) {
  return (
    <div className={`stat-card tone-${tone}`}>
      <div>
        <span>{label}</span>
        <strong>{value}</strong>
        {hint ? <small>{hint}</small> : null}
      </div>
      {Icon ? (
        <div className="stat-icon">
          <Icon size={21} />
        </div>
      ) : null}
    </div>
  );
}
