import React from 'react';
import { colors, radii, shadows } from '../tokens';

export interface CardProps {
  variant?: 'product' | 'recommendation' | 'reasoning' | 'default';
  children: React.ReactNode;
  className?: string;
}

const variantClasses: Record<NonNullable<CardProps['variant']>, string> = {
  default: 'bg-cream-50 rounded-xl shadow-warm-sm',
  product:
    'bg-cream-50 rounded-xl shadow-warm-sm hover:shadow-warm-md hover:-translate-y-0.5 transition-all duration-slide ease-out',
  recommendation:
    'bg-cream-50 rounded-xl shadow-warm-sm border-l-2 border-l-accent',
  reasoning: 'bg-cream-50 rounded-xl shadow-warm-sm',
};

/**
 * Card primitive — borderless, warm-tinted soft shadows.
 *
 * Variants:
 * - default: cream bg, rounded-xl, shadow-warm-sm
 * - product: same + hover lift effect
 * - recommendation: same + left terracotta accent border
 * - reasoning: same + numbered step indicator area
 */
export const Card: React.FC<CardProps> = ({
  variant = 'default',
  children,
  className = '',
}) => {
  return (
    <div
      className={[variantClasses[variant], className].filter(Boolean).join(' ')}
    >
      {children}
    </div>
  );
};

void colors;
void radii;
void shadows;

export default Card;
