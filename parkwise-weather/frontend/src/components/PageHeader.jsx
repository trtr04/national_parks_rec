export default function PageHeader({ title, children }) {
  return (
    <div className="max-w-2xl">
      <h1 className="text-4xl font-bold leading-tight text-ink sm:text-5xl">{title}</h1>
      {children && <p className="mt-3 text-lg leading-relaxed text-ink-muted">{children}</p>}
    </div>
  );
}
