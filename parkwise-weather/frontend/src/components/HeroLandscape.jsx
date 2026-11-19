/**
 * Illustrated ridgeline landscape for the hero.
 *
 * Drawn in SVG (not a photo) for Phase 1: it loads instantly, scales to any
 * screen and carries no licensing questions. Licensed park photography with
 * attribution can be layered in later (see README, "Images").
 */
export default function HeroLandscape() {
  return (
    <svg
      className="absolute inset-0 h-full w-full"
      viewBox="0 0 1440 640"
      preserveAspectRatio="xMidYMax slice"
      aria-hidden="true"
    >
      <defs>
        <linearGradient id="hero-sky" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#2E6A8E" />
          <stop offset="55%" stopColor="#8FB2C2" />
          <stop offset="100%" stopColor="#E9DFC6" />
        </linearGradient>
      </defs>

      <rect width="1440" height="640" fill="url(#hero-sky)" />
      <circle cx="1100" cy="250" r="38" fill="#F2D58E" opacity="0.85" />

      {/* Far range */}
      <path
        className="ridge"
        style={{ animationDelay: "0ms" }}
        fill="#7E9C9B"
        d="M0 360 L120 300 L220 330 L340 250 L470 320 L560 280 L700 340 L820 240 L940 300 L1060 270 L1190 330 L1310 260 L1440 310 L1440 640 L0 640 Z"
      />
      {/* Mid range */}
      <path
        className="ridge"
        style={{ animationDelay: "120ms" }}
        fill="#4F7A64"
        d="M0 430 L160 360 L300 410 L420 340 L560 420 L700 370 L840 430 L980 350 L1120 410 L1260 360 L1440 420 L1440 640 L0 640 Z"
      />
      {/* Near range */}
      <path
        className="ridge"
        style={{ animationDelay: "240ms" }}
        fill="#24503B"
        d="M0 520 L140 460 L260 500 L400 440 L540 510 L680 470 L820 520 L960 455 L1100 505 L1240 465 L1440 515 L1440 640 L0 640 Z"
      />
      {/* Foreground, blends into the page background */}
      <path
        className="ridge"
        style={{ animationDelay: "360ms" }}
        fill="#173527"
        d="M0 590 C240 560 420 600 720 575 C1000 552 1220 600 1440 572 L1440 640 L0 640 Z"
      />
    </svg>
  );
}
