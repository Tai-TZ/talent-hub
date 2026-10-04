export function Skeleton({ lines = 3 }: { lines?: number }) {
  return (
    <div className="skeleton-stack" aria-hidden="true">
      <div className="th-skeleton th-skeleton--title" />
      {Array.from({ length: lines }, (_, i) => (
        <div key={i} className="th-skeleton" style={{ width: `${90 - i * 12}%` }} />
      ))}
    </div>
  );
}
