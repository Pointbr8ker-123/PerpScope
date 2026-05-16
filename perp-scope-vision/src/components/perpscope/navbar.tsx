import { Link, useLocation } from "@tanstack/react-router";
import { Activity, Moon, Sun, Menu, X } from "lucide-react";
import { useEffect, useState } from "react";

function ThemeToggle() {
  const [dark, setDark] = useState(true);
  useEffect(() => {
    const saved = localStorage.getItem("theme");
    const d = saved !== "light";
    setDark(d);
    document.documentElement.classList.toggle("dark", d);
    document.documentElement.classList.toggle("light", !d);
  }, []);
  function toggle() {
    const d = !dark; setDark(d);
    document.documentElement.classList.toggle("dark", d);
    document.documentElement.classList.toggle("light", !d);
    localStorage.setItem("theme", d ? "dark" : "light");
  }
  return (
    <button onClick={toggle} aria-label="Toggle theme"
      className="inline-flex h-9 w-9 items-center justify-center rounded-md border border-border bg-card/60 text-muted-foreground transition hover:text-foreground hover:border-border-strong">
      {dark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
    </button>
  );
}

function NavLink({ to, label }: { to: string; label: string }) {
  const loc = useLocation();
  const active = loc.pathname === to || (to !== "/" && loc.pathname.startsWith(to));
  return (
    <Link to={to} className="relative px-3 py-2 text-sm font-medium transition-colors"
      style={{ color: active ? "var(--foreground)" : "var(--muted-foreground)" }}>
      {label}
      {active && <span className="absolute inset-x-2 -bottom-px h-px bg-primary shadow-[0_0_12px_2px_rgba(59,130,246,0.6)]" />}
    </Link>
  );
}

export function Navbar() {
  const [open, setOpen] = useState(false);
  return (
    <header className="sticky top-0 z-40 h-14 border-b border-border bg-background/70 backdrop-blur-xl">
      <div className="mx-auto flex h-full max-w-[1440px] items-center justify-between px-4 sm:px-6 lg:px-8">
        <div className="flex items-center gap-3">
          <Link to="/" className="flex items-center gap-2">
            <span className="grid h-7 w-7 place-items-center rounded-md bg-gradient-to-br from-primary to-purple text-white">
              <Activity className="h-4 w-4" strokeWidth={2.5} />
            </span>
            <span className="text-base font-bold tracking-tight">PerpScope</span>
            <span className="rounded-md border border-primary/30 bg-primary/10 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-primary">Beta</span>
          </Link>
        </div>
        <nav className="hidden items-center gap-1 md:flex">
          <NavLink to="/" label="Dashboard" />
          <NavLink to="/research" label="Research" />
        </nav>
        <div className="flex items-center gap-2">
          <div className="hidden items-center gap-2 rounded-md border border-border bg-card/40 px-2.5 py-1 sm:flex">
            <span className="relative flex h-2 w-2">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-success opacity-60" />
              <span className="relative inline-flex h-2 w-2 rounded-full" style={{ background: "var(--color-success)" }} />
            </span>
            <span className="text-xs font-medium text-muted-foreground">Live</span>
          </div>
          <ThemeToggle />
          <button onClick={() => setOpen(true)} className="inline-flex h-9 w-9 items-center justify-center rounded-md border border-border md:hidden">
            <Menu className="h-4 w-4" />
          </button>
        </div>
      </div>
      {open && (
        <div className="fixed inset-0 z-50 bg-background/95 backdrop-blur md:hidden">
          <div className="flex h-14 items-center justify-between px-4">
            <span className="text-base font-bold">PerpScope</span>
            <button onClick={() => setOpen(false)} className="inline-flex h-9 w-9 items-center justify-center rounded-md border border-border">
              <X className="h-4 w-4" />
            </button>
          </div>
          <div className="flex flex-col gap-2 px-4 pt-6">
            <Link to="/" onClick={() => setOpen(false)} className="rounded-md px-4 py-3 text-base font-medium hover:bg-elevated">Dashboard</Link>
            <Link to="/research" onClick={() => setOpen(false)} className="rounded-md px-4 py-3 text-base font-medium hover:bg-elevated">Research</Link>
          </div>
        </div>
      )}
    </header>
  );
}
