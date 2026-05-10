import React from 'react';
import { colors } from '../tokens';

export interface ChipProps {
  active?: boolean;
  children: React.ReactNode;
  onClick?: () => void;
  className?: string;
}

/**
 * Chip primitive — suggestion/tag chip with active/inactive states.
 *
 * Inactive: cream-50 bg, espresso text, sand border.
 * Active: espresso bg, cream-50 text, espresso border.
 * Hover (inactive): border-espresso.
 */
export const Chip: React.FC<ChipProps> = ({
  active = false,
  children,
  onClick,
  className = '',
}) => {
  const baseClasses =
    'inline-flex items-center rounded-full px-4 py-1.5 text-sm font-sans transition-colors duration-fade ease-out cursor-pointer select-none';

  const stateClasses = active
    ? 'bg-espresso text-cream-50 border border-espresso'
    : 'bg-cream-50 text-espresso border border-sand hover:border-espresso';

  const focusClasses =
    'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-espresso';

  return (
    <button
      type="button"
      role="option"
      aria-selected={active}
      onClick={onClick}
      className={[baseClasses, stateClasses, focusClasses, className]
        .filter(Boolean)
        .join(' ')}
    >
      {children}
    </button>
  );
};

void colors;

export default Chip;
