/** Labyrinth brand mark — from proj-theseus index.shell.html */
export function ThreadBrandMark({ className = "w-10 h-10" }: { className?: string }) {
  return (
    <svg viewBox="0 0 40 40" className={`brand-labyrinth ${className}`} xmlns="http://www.w3.org/2000/svg">
      <defs>
        <linearGradient id="thread-lab-wall" x1="0" y1="0" x2="40" y2="40">
          <stop offset="0%" stopColor="#00f0ff" />
          <stop offset="55%" stopColor="#a855f7" />
          <stop offset="100%" stopColor="#ff2bd6" />
        </linearGradient>
        <linearGradient id="thread-lab-horn" x1="0" y1="1" x2="0" y2="0">
          <stop offset="0%" stopColor="#ff2bd6" />
          <stop offset="100%" stopColor="#ffcd5e" />
        </linearGradient>
        <radialGradient id="thread-lab-core" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor="#ffffff" />
          <stop offset="45%" stopColor="#5eff9b" />
          <stop offset="100%" stopColor="#00f0ff" stopOpacity="0" />
        </radialGradient>
        <filter id="thread-lab-glow" x="-30%" y="-30%" width="160%" height="160%">
          <feGaussianBlur stdDeviation="0.55" result="b" />
          <feMerge>
            <feMergeNode in="b" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>
      <g fill="none" stroke="url(#thread-lab-horn)" strokeWidth="1.4" strokeLinecap="round" filter="url(#thread-lab-glow)">
        <path d="M5 11 C 3 7, 5 3, 9 4" />
        <path d="M35 11 C 37 7, 35 3, 31 4" />
      </g>
      <g stroke="#00f0ff" strokeWidth="0.7" fill="none" opacity="0.55" strokeLinecap="round">
        <path d="M7 7 L4 7 L4 4" />
        <path d="M33 7 L36 7 L36 4" />
        <path d="M7 33 L4 33 L4 36" />
        <path d="M33 33 L36 33 L36 36" />
        <circle cx="4" cy="4" r="0.9" fill="#00f0ff" />
        <circle cx="36" cy="4" r="0.9" fill="#00f0ff" />
        <circle cx="4" cy="36" r="0.9" fill="#00f0ff" />
        <circle cx="36" cy="36" r="0.9" fill="#00f0ff" />
      </g>
      <g
        stroke="url(#thread-lab-wall)"
        strokeWidth="1.6"
        fill="none"
        strokeLinecap="square"
        strokeLinejoin="miter"
        filter="url(#thread-lab-glow)"
      >
        <path d="M7 7 H33 V33 H22" />
        <path d="M18 33 H7 V7" />
        <path d="M10 10 H30 V30 H22" />
        <path d="M18 30 H10 V10" />
        <path d="M13 13 H27 V27 H22" />
        <path d="M18 27 H13 V13" />
      </g>
      <circle cx="20" cy="20" r="3.5" fill="url(#thread-lab-core)" filter="url(#thread-lab-glow)" />
    </svg>
  );
}