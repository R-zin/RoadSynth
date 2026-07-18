export function LogBlock({
  title,
  content,
}: {
  title: string;
  content: string | null;
}) {
  return (
    <div className="border border-line">
      <div className="border-b border-line px-3 py-2 font-mono text-[11px] uppercase tracking-[0.15em] text-muted bg-surface">
        {title}
      </div>
      <pre className="p-3 font-mono text-[12px] text-ink-2 whitespace-pre-wrap break-words max-h-72 overflow-auto">
        {content ?? '— no output —'}
      </pre>
    </div>
  );
}
