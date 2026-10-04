import React from 'react';

export interface IconButtonProps {
  icon: React.ReactNode;
  ariaLabel: string;
  onClick?: () => void;
  size?: 'sm' | 'md';
  className?: string;
}

/* `shrink-0` because the header lays these out in a flex row: without it the
   44px square is a shrinkable flex item and the storefront's menu control
   measured 42px wide, just under the touch floor it was written to meet. */
const sizeClasses: Record<NonNullable<IconButtonProps['size']>, string> = {
  sm: 'w-8 h-8 shrink-0',
  md: 'w-[44px] h-[44px] shrink-0',
};

/**
 * IconButton primitive — circular ghost button for header use.
 *
 * Transparent bg, rounded-full, espresso icon color.
 * Hover: bg-page. Focus ring for keyboard navigation.
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
        'bg-transparent text-ink hover:bg-recessed',
        'transition-colors duration-fade ease-out cursor-pointer',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-copper',
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

export default IconButton;
