import { Link } from "react-router-dom";

export default function NotFoundPage() {
  return (
    <div className="mx-auto max-w-6xl px-4 py-24 sm:px-6">
      <h1 className="text-5xl font-bold">This trail doesn't go anywhere</h1>
      <p className="mt-3 text-lg text-ink-muted">The page you asked for doesn't exist.</p>
      <Link to="/" className="mt-6 inline-block rounded-xl bg-spruce px-5 py-3 font-medium text-paper">
        Back to the explorer
      </Link>
    </div>
  );
}
