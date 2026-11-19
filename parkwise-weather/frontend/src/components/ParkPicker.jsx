import { useId, useMemo, useRef, useState } from "react";

/**
 * Searchable park selector (an accessible combobox).
 * Type to filter by name, state or park code; arrow keys + Enter to choose.
 *
 * Props: parks (array from /api/parks), value (park_code or ""), onChange(park_code),
 *        label, disabled
 */
export default function ParkPicker({ parks = [], value, onChange, label = "National park", disabled }) {
  const id = useId();
  const listId = `${id}-list`;
  const selected = parks.find((p) => p.park_code === value);
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const inputRef = useRef(null);

  const matches = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return parks;
    return parks.filter(
      (p) =>
        p.park_name.toLowerCase().includes(q) ||
        p.state.toLowerCase().includes(q) ||
        p.park_code.toLowerCase() === q,
    );
  }, [parks, query]);

  function choose(park) {
    onChange(park.park_code);
    setQuery("");
    setOpen(false);
  }

  function onKeyDown(event) {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setOpen(true);
      setActive((i) => Math.min(i + 1, matches.length - 1));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActive((i) => Math.max(i - 1, 0));
    } else if (event.key === "Enter" && open && matches[active]) {
      event.preventDefault();
      choose(matches[active]);
    } else if (event.key === "Escape") {
      setOpen(false);
      setQuery("");
    }
  }

  return (
    <div className="relative">
      <label htmlFor={id} className="mb-1.5 block text-sm font-medium text-ink">
        {label}
      </label>
      <input
        id={id}
        ref={inputRef}
        type="text"
        role="combobox"
        autoComplete="off"
        disabled={disabled}
        aria-expanded={open}
        aria-controls={listId}
        aria-activedescendant={open && matches[active] ? `${listId}-${matches[active].park_code}` : undefined}
        placeholder={disabled ? "Loading parks…" : "Search by park or state"}
        value={open ? query : selected ? `${selected.park_name}, ${selected.state}` : query}
        onChange={(e) => {
          setQuery(e.target.value);
          setActive(0);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 120)}
        onKeyDown={onKeyDown}
        className="w-full rounded-xl border border-line bg-paper-raised px-4 py-3 text-[15px] text-ink placeholder:text-ink-muted/70 disabled:opacity-60"
      />
      {open && (
        <ul
          id={listId}
          role="listbox"
          className="absolute z-30 mt-1 max-h-72 w-full overflow-auto rounded-xl border border-line bg-paper-raised py-1 shadow-lg shadow-spruce-deep/10"
        >
          {matches.length === 0 && (
            <li className="px-4 py-3 text-sm text-ink-muted">No parks match “{query}”.</li>
          )}
          {matches.map((park, index) => (
            <li
              key={park.park_code}
              id={`${listId}-${park.park_code}`}
              role="option"
              aria-selected={park.park_code === value}
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => choose(park)}
              onMouseEnter={() => setActive(index)}
              className={`flex cursor-pointer items-baseline justify-between gap-3 px-4 py-2.5 text-[15px] ${
                index === active ? "bg-sky-soft" : ""
              }`}
            >
              <span>{park.park_name}</span>
              <span className="text-sm text-ink-muted">{park.state}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
