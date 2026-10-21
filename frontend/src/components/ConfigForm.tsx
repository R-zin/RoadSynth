import { useState } from 'react';
import type { SectionDef } from '../api/schema';
import type { ConversionRequest } from '../api/types';
import { Field } from './ui/Field';

interface Props {
  sections: SectionDef[];
  value: ConversionRequest;
  onChange: (section: keyof ConversionRequest, key: string, val: unknown) => void;
}

export function ConfigForm({ sections, value, onChange }: Props) {
  const [open, setOpen] = useState<Record<string, boolean>>({});

  return (
    <div className="flex flex-col">
      {sections.map((section, idx) => {
        const secVal = value[section.key as keyof ConversionRequest] ?? {};
        const keyFields = section.fields.filter((f) => f.group === 'key');
        const advFields = section.fields.filter((f) => f.group === 'advanced');
        const isOpen = open[section.key];

        return (
          <section
            key={section.key}
            className={`pt-6 mt-6 ${idx === 0 ? 'mt-0 pt-0' : 'border-t border-line'}`}
          >
            <h3 className="font-mono text-[13px] uppercase tracking-[0.15em] text-ink mb-5">
              {section.title}
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-x-8 gap-y-5">
              {keyFields.map((f) => (
                <Field
                  key={f.key}
                  field={f}
                  value={secVal[f.key]}
                  onChange={(v) => onChange(section.key as keyof ConversionRequest, f.key, v)}
                />
              ))}
            </div>

            {advFields.length > 0 && (
              <div className="mt-5">
                <button
                  type="button"
                  onClick={() =>
                    setOpen((o) => ({ ...o, [section.key]: !o[section.key] }))
                  }
                  className="font-mono text-[11px] uppercase tracking-[0.2em] text-muted hover:text-ink border-b border-line pb-1"
                >
                  {isOpen ? '− Hide' : '+ Advanced'} parameters
                </button>
                {isOpen && (
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-x-8 gap-y-5 mt-5">
                    {advFields.map((f) => (
                      <Field
                        key={f.key}
                        field={f}
                        value={secVal[f.key]}
                        onChange={(v) =>
                          onChange(section.key as keyof ConversionRequest, f.key, v)
                        }
                      />
                    ))}
                  </div>
                )}
              </div>
            )}
          </section>
        );
      })}
    </div>
  );
}
