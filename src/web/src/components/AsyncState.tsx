export function LoadingState({ label = "Loading" }: { label?: string }) {
  return (
    <div className="state-card" role="status">
      <span className="spinner" aria-hidden="true" />
      {label}
    </div>
  );
}

export function ErrorState({
  error,
  retry,
}: {
  error: unknown;
  retry?: () => void;
}) {
  const message = error instanceof Error ? error.message : "Unexpected failure";
  return (
    <div className="state-card state-error" role="alert">
      <strong>Unable to load evidence</strong>
      <span>{message}</span>
      {retry ? <button onClick={retry}>Retry</button> : null}
    </div>
  );
}

export function EmptyState({ children }: { children: React.ReactNode }) {
  return <div className="state-card state-empty">{children}</div>;
}

export function Badge({ value }: { value: string }) {
  return (
    <span className={`badge badge-${value.toLowerCase().replaceAll("_", "-")}`}>
      {value.replaceAll("_", " ")}
    </span>
  );
}
