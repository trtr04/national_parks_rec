import BackendStatus from "./BackendStatus.jsx";

export default function Footer() {
  return (
    <footer className="border-t border-line bg-paper-raised">
      <div className="mx-auto flex max-w-6xl flex-col gap-4 px-4 py-8 sm:px-6 md:flex-row md:items-end md:justify-between">
        <div className="max-w-xl space-y-2">
          <BackendStatus />
          <p className="text-sm text-ink-muted">
            Weather data from Open-Meteo. Park information from the National Park Service.
            Suitability scores are planning guidance, not safety advice: check NPS alerts and
            trail conditions before you go.
          </p>
        </div>
        <p className="text-sm text-ink-muted">ParkWise, an AI Collective project</p>
      </div>
    </footer>
  );
}
