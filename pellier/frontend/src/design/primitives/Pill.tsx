import React from 'react';
import { colors } from '../tokens';

export interface PillProps {
  variant?: 'live' | 'confidence' | 'default';
  children: React.ReactNode;
  className?: string;
}

/**
 * Pill primitive — small rounded-full status indicator.
 *
 * Live: pulsing terracotta dot before text.
 * Confidence: olive bg with cream text.
 * Default: sand bg with espresso text.
 */
export const Pill: React.FC<PillProps> = ({
  variant = 'default',
  children,
  className = '',
}) => {
  const baseClasses =
    'inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-sans font-medium uppercase tracking-wider';

  const variantClasses: Record<NonNullable<PillProps['variant']>, string> = {
    live: 'bg-sand text-espresso',
    confidence: 'bg-olive text-cream-50',
    default: 'bg-sand text-espresso',
  };

  return (
    <span
      className={[baseClasses, variantClasses[variant], className]
        .filter(Boolean)
        .join(' ')}
    >
      {variant === 'live' && (
        <span
          className="relative flex h-2 w-2"
          aria-hidden="true"
        >
          <span className="absolute inline-flex h-full w-full rounded-full bg-accent opacity-75 motion-safe:animate-ping" />
          <span className="relative inline-flex h-2 w-2 rounded-full bg-accent" />
        </span>
      )}
      {children}
    </span>
  );
};

void colors;

export default Pill;
