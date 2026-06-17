import Link from "next/link";
import { ThreadBrandMark } from "./thread-brand";

type TheseusShellProps = {
  children: React.ReactNode;
  subtitle?: string;
  active?: "pulse" | "workspace";
};

export function TheseusShell({ children, subtitle = "Capture command center", active = "pulse" }: TheseusShellProps) {
  return (
    <div className="min-h-screen flex flex-col">
      <header className="h-14 shrink-0 topbar-vibrant flex items-center px-5 gap-5 sticky top-0 z-40">
        <div className="flex items-center gap-2.5 min-w-[240px]">
          <div
            className="brand-tile w-10 h-10 rounded-xl flex items-center justify-center"
            title="Ariadne's Thread — Shipley capture command center"
          >
            <ThreadBrandMark />
          </div>
          <div className="leading-tight">
            <div className="text-sm font-semibold tracking-tight">
              Ariadne&apos;s Thread<span className="neon-text">.</span>
            </div>
            <div className="text-[11px] font-mono uppercase tracking-wider text-slate-500">{subtitle}</div>
          </div>
        </div>

        <nav className="flex items-center gap-2 ml-auto">
          <Link
            href="/"
            className={`topbar-pill ${active === "pulse" ? "text-neon-cyan" : ""}`}
          >
            Portfolio Pulse
          </Link>
        </nav>
      </header>

      <main className="flex-1 w-full max-w-6xl mx-auto px-6 py-8">{children}</main>
    </div>
  );
}