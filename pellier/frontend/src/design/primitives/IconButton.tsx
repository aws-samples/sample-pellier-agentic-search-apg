import React from 'react';
import { colors } from '../tokens';

export interface IconButtonProps {
  icon: React.ReactNode;
  ariaLabel: string;
  onClick?: () => void;
  size?: 'sm' | 'md';
  className?: string;
}

const sizeClasses: Record<NonNullable<IconButtonProps['size']>, string> = {
  sm: 'w-8 h-8',
  md: 'w-10 h-10',
};

/**
 * IconButton primitive — circular ghost button for header use.
 *
 * Transparent bg, rounded-full, espresso icon color.
 * Hover: bg-cream-50. Focus ring for keyboard navigation.
 */
export const IconButton: React.FC<IconButtonProps> = ({
  icon,
  ariaLabel,
  onClick,
  size = 'md',
  className = '',
}) => {
  return (
    <button
      type="button"
      aria-label={ariaLabel}
      onClick={onClick}
      className={[
        'inline-flex items-center justify-center rounded-full',
        'bg-transparent text-espresso hover:bg-cream-50',
        'transition-colors duration-fade ease-out cursor-pointer',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-espresso',
        sizeClasses[size],
        className,
      ]
        .filter(Boolean)
        .join(' ')}
    >
      {icon}
    </button>
  );
};

void colors;

export default IconButton;
