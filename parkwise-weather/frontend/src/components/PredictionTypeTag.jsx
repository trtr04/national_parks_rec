/** "Forecast" (sky) or "Climate estimate" (ochre): the two kinds of answer, always labelled. */
export default function PredictionTypeTag({ type }) {
  const forecast = type === "forecast";
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-semibold uppercase tracking-wide ${
        forecast ? "bg-sky-soft text-sky" : "bg-ochre-soft text-ochre"
      }`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${forecast ? "bg-sky" : "bg-ochre"}`} aria-hidden="true" />
      {forecast ? "Forecast" : "Climate estimate"}
    </span>
  );
}
