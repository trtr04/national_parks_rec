export const ACTIVITIES = [
  { value: "hiking", label: "Hiking" },
  { value: "camping", label: "Camping" },
  { value: "sightseeing", label: "Sightseeing" },
  { value: "wildlife", label: "Wildlife watching" },
];

export const activityLabel = (value) => ACTIVITIES.find((a) => a.value === value)?.label ?? value;

// Comfortable daytime high (°C) per activity. Must match COMFORT_BAND_C in
// backend/app/services/suitability.py.
export const COMFORT_BAND_C = {
  hiking: [12, 24],
  camping: [15, 27],
  sightseeing: [10, 28],
  wildlife: [5, 22],
};

export default function ActivityPicker({ value, onChange, name = "activity" }) {
  return (
    <fieldset>
      <legend className="mb-1.5 text-sm font-medium text-ink">Activity</legend>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {ACTIVITIES.map((a) => (
          <label
            key={a.value}
            className={`cursor-pointer rounded-xl border px-3 py-2.5 text-center text-[15px] transition-colors has-[:focus-visible]:outline has-[:focus-visible]:outline-3 has-[:focus-visible]:outline-sky ${
              value === a.value
                ? "border-spruce bg-spruce text-paper"
                : "border-line bg-paper-raised text-ink hover:border-lichen"
            }`}
          >
            <input
              type="radio"
              name={name}
              value={a.value}
              checked={value === a.value}
              onChange={() => onChange(a.value)}
              className="sr-only"
            />
            {a.label}
          </label>
        ))}
      </div>
    </fieldset>
  );
}
