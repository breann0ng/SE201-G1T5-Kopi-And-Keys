// Vector recreation of the Kopi & Keys logo (original raster: src/assets/logo-original.png).
// Inline SVG so it stays sharp at any size and uses the page's "Baloo 2" font.
// Colours come from the theme tokens in index.css.

const NAVY = "var(--logo-navy)";
const BG = "var(--logo-bg)";
const CORAL = "var(--color-coral-500)";
const KOPI = "var(--color-kopi-500)";

/** Full logo: cup + K² + key + house, with the "KOPI & KEYS" wordmark. */
export function Logo({ className = "", title = "Kopi & Keys" }: { className?: string; title?: string }) {
  return (
    <svg viewBox="0 0 240 190" className={className} role="img" aria-label={title}>
      <title>{title}</title>
      <LogoMark />
      <text
        x="120"
        y="178"
        textAnchor="middle"
        fontFamily="'Baloo 2', ui-rounded, system-ui, sans-serif"
        fontWeight="800"
        fontSize="34"
        letterSpacing="1"
      >
        <tspan fill={NAVY}>KOPI </tspan>
        <tspan fill={CORAL}>&amp;</tspan>
        <tspan fill={NAVY}> KEYS</tspan>
      </text>
    </svg>
  );
}

/** Icon only (no wordmark), for small spaces. */
export function LogoIcon({ className = "", title = "Kopi & Keys" }: { className?: string; title?: string }) {
  return (
    <svg viewBox="20 0 200 140" className={className} role="img" aria-label={title}>
      <title>{title}</title>
      <LogoMark />
    </svg>
  );
}

function LogoMark() {
  return (
    <g strokeLinecap="round" strokeLinejoin="round">
      {/* K */}
      <text
        x="58"
        y="130"
        fontFamily="'Baloo 2', ui-rounded, system-ui, sans-serif"
        fontWeight="800"
        fontSize="150"
        fill={NAVY}
      >
        K
      </text>
      {/* superscript 2 */}
      <text
        x="142"
        y="44"
        fontFamily="'Baloo 2', ui-rounded, system-ui, sans-serif"
        fontWeight="800"
        fontSize="44"
        fill={NAVY}
      >
        2
      </text>
      {/* sparks */}
      <g stroke={CORAL} strokeWidth="4.5">
        <path d="M172 20l7-11" />
        <path d="M182 33l13-6" />
        <path d="M184 47l13 2" />
      </g>
      {/* steam */}
      <g fill="none" stroke={KOPI} strokeWidth="4">
        <path d="M38 76c-6-7 6-11 0-19s4-12 0-18" />
        <path d="M51 72c-5-6 5-9 0-16" />
      </g>
      {/* cup, drawn in front of the K's stem */}
      <path d="M22 92h66c0 22-14 38-33 38S22 114 22 92z" fill={BG} stroke={NAVY} strokeWidth="7" />
      <ellipse cx="55" cy="92" rx="33" ry="9" fill={KOPI} stroke={NAVY} strokeWidth="6" />
      <path d="M40 108c2 9 8 14 16 15" fill="none" stroke={NAVY} strokeWidth="6" />
      {/* key: bow hooked on the K's arm, blade down-right with teeth */}
      <circle cx="140" cy="82" r="11" fill="none" stroke={CORAL} strokeWidth="7" />
      <path d="M147 91l22 30" fill="none" stroke={CORAL} strokeWidth="9" />
      <path d="M160 109l-8 6M166 117l-7 5" fill="none" stroke={CORAL} strokeWidth="7" />
      {/* house: filled, with a four-pane window */}
      <path d="M176 128V104l17-15 17 15v24z" fill={NAVY} stroke={NAVY} strokeWidth="4" />
      <g fill={BG}>
        <rect x="187" y="108" width="5" height="5" />
        <rect x="194" y="108" width="5" height="5" />
        <rect x="187" y="115" width="5" height="5" />
        <rect x="194" y="115" width="5" height="5" />
      </g>
    </g>
  );
}
