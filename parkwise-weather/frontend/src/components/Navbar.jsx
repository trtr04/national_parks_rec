import { useEffect, useState } from "react";
import { Link, NavLink, useLocation } from "react-router-dom";

const LINKS = [
  { to: "/", label: "Explorer", end: true },
  { to: "/history", label: "History" },
  { to: "/compare", label: "Compare parks" },
  { to: "/best-time", label: "Best time to visit" },
  { to: "/model-insights", label: "Model insights" },
];

function Wordmark() {
  return (
    <Link to="/" className="flex items-center gap-2.5 text-ink" aria-label="ParkWise Weather home">
      <svg viewBox="0 0 32 32" className="h-8 w-8" aria-hidden="true">
        <rect width="32" height="32" rx="8" fill="var(--color-spruce)" />
        <circle cx="22" cy="10" r="4" fill="#E8C77E" />
        <path d="M3 26 L12 13 L17 19 L21 15 L29 26 Z" fill="var(--color-paper)" />
      </svg>
      <span className="font-display text-xl font-bold leading-none">
        ParkWise <span className="font-medium text-ink-muted">Weather</span>
      </span>
    </Link>
  );
}

export default function Navbar() {
  const [open, setOpen] = useState(false);
  const location = useLocation();

  // Close the mobile menu after navigating.
  useEffect(() => setOpen(false), [location.pathname]);

  const linkClass = ({ isActive }) =>
    `rounded-lg px-3 py-2 text-[15px] font-medium transition-colors ${
      isActive ? "bg-spruce text-paper" : "text-ink-muted hover:bg-line/60 hover:text-ink"
    }`;

  return (
    <header className="sticky top-0 z-40 border-b border-line bg-paper/90 backdrop-blur">
      <nav className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-3 sm:px-6">
        <Wordmark />

        <ul className="hidden items-center gap-1 lg:flex">
          {LINKS.map((link) => (
            <li key={link.to}>
              <NavLink to={link.to} end={link.end} className={linkClass}>
                {link.label}
              </NavLink>
            </li>
          ))}
        </ul>

        <button
          type="button"
          className="rounded-lg p-2 text-ink lg:hidden"
          aria-expanded={open}
          aria-controls="mobile-nav"
          aria-label={open ? "Close menu" : "Open menu"}
          onClick={() => setOpen((v) => !v)}
        >
          <svg viewBox="0 0 24 24" className="h-6 w-6" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
            {open ? <path d="M6 6l12 12M18 6L6 18" /> : <path d="M4 7h16M4 12h16M4 17h16" />}
          </svg>
        </button>
      </nav>

      {open && (
        <ul id="mobile-nav" className="mx-auto flex max-w-6xl flex-col gap-1 px-4 pb-4 lg:hidden">
          {LINKS.map((link) => (
            <li key={link.to}>
              <NavLink to={link.to} end={link.end} className={(s) => `block ${linkClass(s)}`}>
                {link.label}
              </NavLink>
            </li>
          ))}
        </ul>
      )}
    </header>
  );
}
