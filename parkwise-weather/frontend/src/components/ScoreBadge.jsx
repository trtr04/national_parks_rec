/**
 * Suitability score (0–100) with its label. Colours follow the label so a score
 * reads the same on every page.
 */

export const LABEL_STYLES = {
  Excellent: { badge: "bg-spruce text-paper", bar: "var(--color-spruce)", text: "text-spruce" },
  Good: { badge: "bg-lichen text-spruce-deep", bar: "var(--color-lichen)", text: "text-spruce" },
  Fair: { badge: "bg-ochre-soft text-ochre", bar: "var(--color-ochre)", text: "text-ochre" },
  Poor: { badge: "bg-alert-soft text-alert", bar: "var(--color-alert)", text: "text-alert" },
};

// Must match LABELS in backend/app/services/suitability.py.
export function labelFor(score) {
  if (score >= 80) return "Excellent";
  if (score >= 65) return "Good";
  if (score >= 45) return "Fair";
  return "Poor";
}

export default function ScoreBadge({ score, label = labelFor(score), size = "md" }) {
  const style = LABEL_STYLES[label] ?? LABEL_STYLES.Fair;
  if (size === "lg") {
    return (
      <div className="flex items-baseline gap-3">
        <span className={`font-display text-6xl font-bold leading-none ${style.text}`}>{Math.round(score)}</span>
        <span className="text-sm text-ink-muted">/ 100</span>
        <span className={`rounded-full px-3 py-1 text-sm font-semibold ${style.badge}`}>{label}</span>
      </div>
    );
  }
  return (
    <span className={`inline-flex items-baseline gap-1.5 rounded-full px-2.5 py-0.5 text-sm font-semibold ${style.badge}`}>
      <span className="tabular-nums">{Math.round(score)}</span>
      <span className="font-medium">{label}</span>
    </span>
  );
}
