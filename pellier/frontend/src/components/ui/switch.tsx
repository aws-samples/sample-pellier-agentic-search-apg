import * as React from 'react';
import * as SwitchPrimitive from '@radix-ui/react-switch';
import { cn } from '../../lib/utils';

const Switch = React.forwardRef<
  React.ElementRef<typeof SwitchPrimitive.Root>,
  React.ComponentPropsWithoutRef<typeof SwitchPrimitive.Root>
>(({ className, ...props }, ref) => (
  <SwitchPrimitive.Root
    className={cn(
      [
        'peer inline-flex h-[18px] w-8 shrink-0 cursor-pointer items-center rounded-full',
        'border border-transparent bg-[var(--obs-ink-5)] transition-colors',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-copper focus-visible:ring-offset-2',
        'data-[state=checked]:bg-ink disabled:cursor-not-allowed disabled:opacity-45',
      ],
      className,
    )}
    {...props}
    ref={ref}
  >
    <SwitchPrimitive.Thumb
      className={[
        'pointer-events-none block size-3.5 rounded-full bg-[var(--obs-cream-elev)] shadow-sm',
        'transition-transform data-[state=checked]:translate-x-[14px] data-[state=unchecked]:translate-x-px',
      ].join(' ')}
    />
  </SwitchPrimitive.Root>
));
Switch.displayName = SwitchPrimitive.Root.displayName;

export { Switch };
