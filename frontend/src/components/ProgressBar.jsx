export default function ProgressBar({ value, max }) {
  const percent = max ? Math.min(100, Math.round((value * 100) / max)) : 0;
  return (
    <div className="progress-track" aria-label={`${percent}%`}>
      <span style={{ width: `${percent}%` }} />
    </div>
  );
}
