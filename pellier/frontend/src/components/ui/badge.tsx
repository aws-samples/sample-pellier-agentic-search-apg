import * as React from 'react';
import { cva, type VariantProps } from 'class-variance-authority';
import { cn } from '../../lib/utils';

const badgeVariants = cva(
  'inline-flex min-h-6 items-center gap-1.5 rounded-md border px-2 py-0.5 font-sans text-[11px] font-semibold leading-none',
  {
    variants: {
      variant: {
        default: 'border-line bg-copper-tint text-ink-2',
        neutral:
          'border-[var(--obs-rule-1)] bg-[var(--obs-cream-2)] text-[var(--obs-ink-3)]',
        success: 'border-green-800/20 bg-green-900/10 text-green-800',
        warning: 'border-amber-700/20 bg-amber-700/10 text-amber-800',
        destructive: 'border-red-700/20 bg-red-700/10 text-red-800',
      },
    },
    defaultVariants: {
      variant: 'default',
    },
  },
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return (
    <span className={cn(badgeVariants({ variant }), className)} {...props} />
  );
}

export { Badge, badgeVariants };
