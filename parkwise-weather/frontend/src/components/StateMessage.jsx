/**
 * Shared loading / error / empty / notice panels so every page handles
 * these states the same way.
 */

const TONES = {
  neutral: "border-line bg-paper-raised text-ink",
  error: "border-alert/30 bg-alert-soft text-alert",
  notice: "border-ochre/30 bg-ochre-soft text-ink",
  info: "border-sky/25 bg-sky-soft text-ink",
};

export function Panel({ tone = "neutral", title, children, action, role }) {
  return (
    <div className={`rounded-2xl border px-5 py-4 ${TONES[tone]}`} role={role}>
      {title && <p className="font-display text-lg font-bold">{title}</p>}
      {children && <div className="mt-1 text-[15px] leading-relaxed text-ink-muted">{children}</div>}
      {action && <div className="mt-3">{action}</div>}
    </div>
  );
}

export function Loading({ label = "Loading…" }) {
  return (
    <div className="flex items-center gap-3 py-6 text-ink-muted" role="status">
      <span className="h-5 w-5 animate-spin rounded-full border-2 border-line border-t-spruce" aria-hidden="true" />
      <span>{label}</span>
    </div>
  );
}

export function ErrorMessage({ error, onRetry }) {
  return (
    <Panel
      tone="error"
      role="alert"
      title={error?.code === "network_error" ? "The API isn't responding" : "Something went wrong"}
      action={
        onRetry && (
          <button type="button" onClick={onRetry} className="rounded-lg bg-alert px-3 py-1.5 text-sm font-medium text-paper">
            Try again
          </button>
        )
      }
    >
      {error?.message || "Unknown error."}
    </Panel>
  );
}

export function EmptyState({ title, children, action }) {
  return (
    <Panel tone="neutral" title={title} action={action}>
      {children}
    </Panel>
  );
}
