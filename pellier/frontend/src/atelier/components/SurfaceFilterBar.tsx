/**
 * SurfaceFilterBar — pill filters shared across Understand / Measure surfaces.
 */
export interface FilterOption<T extends string> {
  id: T;
  label: string;
}

export interface SurfaceFilterBarProps<T extends string> {
  label?: string;
  filter: T;
  counts: Record<T, number>;
  options: FilterOption<T>[];
  onChange: (id: T) => void;
}

export function SurfaceFilterBar<T extends string>({
  label = 'Filter',
  filter,
  counts,
  options,
  onChange,
}: SurfaceFilterBarProps<T>) {
  return (
    <div
      style={{
        display: 'flex',
        flexWrap: 'wrap',
        gap: '8px',
        marginBottom: '16px',
        alignItems: 'center',
      }}
    >
      <span
        style={{
          fontFamily: 'var(--at-mono)',
          fontSize: '11px',
          letterSpacing: '0.14em',
          textTransform: 'uppercase',
          color: 'var(--at-ink-3)',
          marginRight: '4px',
        }}
      >
        {label}
      </span>
      {options.map((opt) => {
        const active = filter === opt.id;
        return (
          <button
            key={opt.id}
            type="button"
            onClick={() => onChange(opt.id)}
            style={{
              fontFamily: 'var(--at-mono)',
              fontSize: '12px',
              padding: '5px 12px',
              borderRadius: '999px',
              border: active ? '1px solid var(--at-ink-1)' : '1px solid var(--at-rule-2)',
              background: active ? 'var(--at-ink-1)' : 'var(--at-cream-2)',
              color: active ? 'var(--at-cream-1)' : 'var(--at-ink-2)',
              cursor: 'pointer',
            }}
          >
            {opt.label} ({counts[opt.id] ?? 0})
          </button>
        );
      })}
    </div>
  );
}
