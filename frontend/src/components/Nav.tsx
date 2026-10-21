import { useState } from 'react';
import { NavLink } from 'react-router-dom';
import { getApiKey, setApiKey } from '../api/client';

const LINKS = [
  { to: '/', label: 'DASHBOARD', end: true },
  { to: '/new', label: 'NEW JOB', end: false },
  { to: '/system', label: 'SYSTEM', end: false },
];

function ApiKeyInput() {
  const [key, setKey] = useState(getApiKey());
  return (
    <div className="flex items-center gap-2">
      <input
        type="password"
        value={key}
        onChange={(e) => {
          setKey(e.target.value);
          setApiKey(e.target.value);
        }}
        placeholder="API KEY (IF ENABLED)"
        className="font-mono text-[11px] uppercase tracking-[0.1em] bg-white border border-line px-2 py-1.5 w-44 focus:border-ink outline-none rounded-none placeholder:text-muted"
      />
      {key && (
        <button
          type="button"
          onClick={() => {
            setKey('');
            setApiKey('');
          }}
          className="font-mono text-[10px] uppercase tracking-[0.15em] text-muted hover:text-status-failed"
        >
          Clear
        </button>
      )}
    </div>
  );
}

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
          <ApiKeyInput />
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
