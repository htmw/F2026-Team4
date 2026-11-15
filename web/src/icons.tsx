// A few drawn icons in one consistent stroke, instead of text glyphs (⚠, ✕, ←, →) whose look
// depends on the font. Decorative: every use sits next to a text label.

interface IconProps {
  className?: string;
}

function Svg({ className, children }: IconProps & { children: React.ReactNode }) {
  return (
    <svg
      className={`icon${className ? ` ${className}` : ""}`}
      viewBox="0 0 16 16"
      width="16"
      height="16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {children}
    </svg>
  );
}

export function ChevronLeft(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M10 3.5 5.5 8l4.5 4.5" />
    </Svg>
  );
}

export function ChevronRight(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M6 3.5 10.5 8 6 12.5" />
    </Svg>
  );
}

export function ChevronDown(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M3.5 6 8 10.5 12.5 6" />
    </Svg>
  );
}

export function AlertIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M8 2.2 14.3 13.2H1.7Z" />
      <path d="M8 6.4v3.2" />
      <path d="M8 11.6h.01" />
    </Svg>
  );
}

export function CloseIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="m4.5 4.5 7 7M11.5 4.5l-7 7" />
    </Svg>
  );
}

// ---- Map-legend symbols: one per interest, drawn in the same 1.6 stroke as the icons above,
// so a stop's pin and the form's interest rows share one legend.

export function FoldedMapIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M2 4.2 6 2.7l4 1.5 4-1.5v9.1l-4 1.5-4-1.5-4 1.5Z" />
      <path d="M6 2.7v9.1M10 4.2v9.1" />
    </Svg>
  );
}

export function PinIcon(props: IconProps) {
  return (
    <Svg {...props}>
      <path d="M8 14s4.5-4.1 4.5-7.4a4.5 4.5 0 0 0-9 0C3.5 9.9 8 14 8 14Z" />
      <circle cx="8" cy="6.6" r="1.5" />
    </Svg>
  );
}

const INTEREST_PATHS: Record<string, React.ReactNode> = {
  // Fork and knife
  food: (
    <>
      <path d="M4.5 2v4a1.5 1.5 0 0 0 3 0V2M6 2v12" />
      <path d="M11 14V2c1.5.9 2.1 2.8 2.1 5V9H11" />
    </>
  ),
  // Classical monument
  history: (
    <>
      <path d="M2 5.6 8 2.4l6 3.2Z" />
      <path d="M4 7.6v4.8M8 7.6v4.8M12 7.6v4.8M2.5 14h11" />
    </>
  ),
  // Framed picture
  art: (
    <>
      <rect x="2.5" y="3" width="11" height="10" rx="0.5" />
      <path d="m4.5 11 2.4-2.8 1.9 1.9 1.4-1.3 1.8 2.2" />
      <circle cx="10.4" cy="5.9" r="0.9" />
    </>
  ),
  // Building with windows and a door
  architecture: (
    <>
      <path d="M3.5 14V4.2L8 2.3l4.5 1.9V14M2 14h12" />
      <path d="M6 6.3h.01M10 6.3h.01M6 8.8h.01M10 8.8h.01M7 14v-2.6h2V14" />
    </>
  ),
  // Pine tree
  nature: (
    <>
      <path d="M8 2 4.6 6.6h1.8L4 10.4h8L9.6 6.6h1.8Z" />
      <path d="M8 10.4V14" />
    </>
  ),
  // Moon and star
  nightlife: (
    <>
      <path d="M9.6 2.6a5.3 5.3 0 1 0 3.8 8.7 4.4 4.4 0 0 1-3.8-8.7Z" />
      <path d="M12.2 2.4v2M11.2 3.4h2" />
    </>
  ),
  // Shopping bag
  shopping: (
    <>
      <path d="M3.4 5.4h9.2l-.8 8.6H4.2Z" />
      <path d="M6 5.4V4.6a2 2 0 0 1 4 0v.8" />
    </>
  ),
};

/** The map-legend symbol for an interest ("food", "history"…), or a map pin for anything else. */
export function InterestIcon({ interest, className }: IconProps & { interest?: string | null }) {
  const paths = interest ? INTEREST_PATHS[interest] : undefined;
  if (!paths) return <PinIcon className={className} />;
  return <Svg className={className}>{paths}</Svg>;
}
