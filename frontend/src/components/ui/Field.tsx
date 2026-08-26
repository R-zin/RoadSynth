import type { FieldDef } from '../../api/schema';

interface Props {
  field: FieldDef;
  value: unknown;
  onChange: (value: unknown) => void;
}

const inputCls =
  'w-full bg-white border border-line px-3 py-2 text-sm font-mono focus:border-ink outline-none rounded-none';

function Description({ id, text }: { id: string; text?: string }) {
  if (!text) return null;
  return (
    <p id={`${id}-desc`} className="mt-1 font-mono text-[10px] leading-relaxed text-muted">
      {text}
    </p>
  );
}

export function Field({ field, value, onChange }: Props) {
  const id = `f-${field.key}`;
  const labelCls = 'block label-mono mb-2';

  if (field.type === 'boolean') {
    return (
      <div>
        <label className="flex items-center gap-3 cursor-pointer select-none">
          <input
            id={id}
            type="checkbox"
            checked={!!value}
            onChange={(e) => onChange(e.target.checked)}
            className="accent-accent w-4 h-4"
          />
          <span className="font-mono text-[12px] text-ink-2">
            {field.label}
          </span>
        </label>
        <Description id={id} text={field.description} />
      </div>
    );
  }

  if (field.type === 'select') {
    return (
      <div>
        <label htmlFor={id} className={labelCls}>
          {field.label}
        </label>
        <select
          id={id}
          value={(value as string) ?? ''}
          onChange={(e) =>
            onChange(field.nullable && e.target.value === '' ? null : e.target.value)
          }
          className={inputCls}
        >
          {field.nullable && <option value="">— none —</option>}
          {field.options?.map((o) => (
            <option key={o} value={o}>
              {o}
            </option>
          ))}
        </select>
        <Description id={id} text={field.description} />
      </div>
    );
  }

  if (field.type === 'multiselect') {
    const selected = Array.isArray(value) ? (value as string[]) : [];
    const toggle = (o: string) => {
      const set = new Set(selected);
      if (set.has(o)) set.delete(o);
      else set.add(o);
      onChange([...set]);
    };
    return (
      <div>
        <label className={labelCls}>{field.label}</label>
        <div className="flex flex-wrap gap-2">
          {field.options?.map((o) => {
            const active = selected.includes(o);
            return (
              <button
                type="button"
                key={o}
                onClick={() => toggle(o)}
                className={`font-mono text-[11px] uppercase tracking-[0.1em] px-2 py-1 border ${
                  active
                    ? 'bg-ink text-bg border-ink'
                    : 'bg-white text-ink-2 border-line hover:border-ink'
                }`}
              >
                {o}
              </button>
            );
          })}
        </div>
        <Description id={id} text={field.description} />
      </div>
    );
  }

  if (field.type === 'number') {
    return (
      <div>
        <label htmlFor={id} className={labelCls}>
          {field.label}
        </label>
        <input
          id={id}
          type="number"
          value={value === null || value === undefined ? '' : (value as number)}
          min={field.min}
          max={field.max}
          step={field.step}
          placeholder={field.placeholder}
          onChange={(e) =>
            onChange(e.target.value === '' ? null : Number(e.target.value))
          }
          className={inputCls}
        />
        <Description id={id} text={field.description} />
      </div>
    );
  }

  // text
  return (
    <div>
      <label htmlFor={id} className={labelCls}>
        {field.label}
      </label>
      <input
        id={id}
        type="text"
        value={(value as string) ?? ''}
        placeholder={field.placeholder}
        onChange={(e) => onChange(e.target.value === '' ? null : e.target.value)}
        className={inputCls}
      />
      <Description id={id} text={field.description} />
    </div>
  );
}
