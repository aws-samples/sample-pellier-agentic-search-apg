import React from 'react';
import { colors, animation } from '../tokens';

export interface ButtonProps {
  variant: 'primary' | 'secondary' | 'ghost';
  size?: 'sm' | 'md' | 'lg';
  disabled?: boolean;
  children: React.ReactNode;
  onClick?: () => void;
  className?: string;
  type?: 'button' | 'submit';
}

const variantClasses: Record<ButtonProps['variant'], string> = {
  primary:
    'bg-espresso text-cream-50 hover:bg-dusk',
  secondary:
    'bg-transparent border border-espresso text-espresso hover:bg-cream-50',
  ghost:
    'bg-transparent text-espresso hover:bg-cream-50',
};

const sizeClasses: Record<NonNullable<ButtonProps['size']>, string> = {
  sm: 'px-4 py-1.5 text-sm',
  md: 'px-6 py-2.5 text-sm',
  lg: 'px-8 py-3 text-base',
};

/**
 * Button primitive — primary, secondary, and ghost variants.
 *
 * Consumes design tokens via Tailwind utility classes.
 * Visible focus ring for keyboard navigation (WCAG AA).
 */
export const Button: React.FC<ButtonProps> = ({
  variant,
  size = 'md',
  disabled = false,
  children,
  onClick,
  className = '',
  type = 'button',
}) => {
  return (
    <button
      type={type}
      disabled={disabled}
      onClick={onClick}
      className={[
        'inline-flex items-center justify-center rounded-full font-sans font-medium',
        'transition-colors duration-fade ease-out',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-espresso',
        variantClasses[variant],
        sizeClasses[size],
        disabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer',
        className,
      ]
        .filter(Boolean)
        .join(' ')}
    >
      {children}
    </button>
  );
};

// Suppress unused import warning — tokens imported as source-of-truth reference
void colors;
void animation;

export default Button;
