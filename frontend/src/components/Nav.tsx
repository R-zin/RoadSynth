import { NavLink } from 'react-router-dom';

const LINKS = [
  { to: '/', label: 'DASHBOARD', end: true },
  { to: '/new', label: 'NEW JOB', end: false },
  { to: '/system', label: 'SYSTEM', end: false },
];

export function Nav() {
  return (
    <header className="sticky top-0 z-20 bg-bg/95 backdrop-blur border-b border-line">
      <div className="mx-auto max-w-[1200px] px-6 h-[72px] grid grid-cols-12 items-center">
        <div className="col-span-3 flex items-center gap-2">
          <span className="w-3 h-3 bg-ink" />
          <span className="font-bold tracking-tight text-ink text-lg">OSM→NS3</span>
        </div>
        <div className="col-span-6" />
        <nav className="col-span-3 flex items-center justify-end gap-6">
          {LINKS.map((l) => (
            <NavLink
              key={l.to}
              to={l.to}
              end={l.end}
              className={({ isActive }) =>
                `font-mono text-[12px] uppercase tracking-[0.15em] font-semibold ${
                  isActive ? 'text-ink' : 'text-muted hover:text-ink'
                }`
              }
            >
              {l.label}
            </NavLink>
          ))}
        </nav>
      </div>
    </header>
  );
}
