import * as React from 'react';
import * as ToggleGroupPrimitive from '@radix-ui/react-toggle-group';
import { cn } from '../../lib/utils';

const ToggleGroup = React.forwardRef<
  React.ElementRef<typeof ToggleGroupPrimitive.Root>,
  React.ComponentPropsWithoutRef<typeof ToggleGroupPrimitive.Root>
>(({ className, children, ...props }, ref) => (
  <ToggleGroupPrimitive.Root
    ref={ref}
    className={cn(
      'inline-flex overflow-hidden rounded-md border border-[var(--obs-rule-1)] bg-[var(--obs-cream-2)] p-0.5',
      className,
    )}
    {...props}
  >
    {children}
  </ToggleGroupPrimitive.Root>
));
ToggleGroup.displayName = ToggleGroupPrimitive.Root.displayName;

const ToggleGroupItem = React.forwardRef<
  React.ElementRef<typeof ToggleGroupPrimitive.Item>,
  React.ComponentPropsWithoutRef<typeof ToggleGroupPrimitive.Item>
>(({ className, children, ...props }, ref) => (
  <ToggleGroupPrimitive.Item
    ref={ref}
    className={cn(
      [
        'inline-flex min-h-8 flex-1 items-center justify-center rounded-[4px] px-2.5',
        'font-sans text-xs font-semibold text-[var(--obs-ink-3)] transition-colors',
        'hover:text-[var(--obs-ink-1)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-copper',
        'data-[state=on]:bg-[var(--obs-cream-elev)] data-[state=on]:text-ink-2 data-[state=on]:shadow-sm',
        'disabled:pointer-events-none disabled:opacity-50',
      ],
      className,
    )}
    {...props}
  >
    {children}
  </ToggleGroupPrimitive.Item>
));
ToggleGroupItem.displayName = ToggleGroupPrimitive.Item.displayName;

export { ToggleGroup, ToggleGroupItem };
