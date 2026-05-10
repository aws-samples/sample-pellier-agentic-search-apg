import React, { useEffect, useRef, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { AnimatePresence, motion } from 'framer-motion';
import { colors, animation } from '../tokens';

export interface DrawerProps {
  open: boolean;
  onClose: () => void;
  side?: 'left' | 'right';
  children: React.ReactNode;
  ariaLabel: string;
  className?: string;
}

const FOCUSABLE_SELECTOR =
  'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';

/**
 * Drawer primitive — Framer Motion slide, 240ms ease-out.
 *
 * Portal to document.body. Focus trap while open.
 * Respects prefers-reduced-motion: opacity-only when reduced.
 */
export const Drawer: React.FC<DrawerProps> = ({
  open,
  onClose,
  side = 'right',
  children,
  ariaLabel,
  className = '',
}) => {
  const contentRef = useRef<HTMLDivElement>(null);

  // Focus trap
  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
        return;
      }

      if (e.key !== 'Tab') return;

      const drawer = contentRef.current;
      if (!drawer) return;

      const focusable = Array.from(
        drawer.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)
      );
      if (focusable.length === 0) return;

      const first = focusable[0];
      const last = focusable[focusable.length - 1];

      if (e.shiftKey) {
        if (document.activeElement === first) {
          e.preventDefault();
          last.focus();
        }
      } else {
        if (document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    },
    [onClose]
  );

  useEffect(() => {
    if (!open) return;

    document.addEventListener('keydown', handleKeyDown);

    const timer = setTimeout(() => {
      const drawer = contentRef.current;
      if (!drawer) return;
      const first = drawer.querySelector<HTMLElement>(FOCUSABLE_SELECTOR);
      first?.focus();
    }, 50);

    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      clearTimeout(timer);
    };
  }, [open, handleKeyDown]);

  const reducedMotion =
    typeof window !== 'undefined' &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  const isLeft = side === 'left';

  const slideVariants = reducedMotion
    ? { hidden: { opacity: 0 }, visible: { opacity: 1 }, exit: { opacity: 0 } }
    : {
        hidden: { x: isLeft ? '-100%' : '100%', opacity: 0 },
        visible: {
          x: 0,
          opacity: 1,
          transition: { duration: 0.24, ease: 'easeOut' as const },
        },
        exit: {
          x: isLeft ? '-100%' : '100%',
          opacity: 0,
          transition: { duration: 0.24, ease: 'easeOut' as const },
        },
      };

  const backdropVariants = reducedMotion
    ? { hidden: { opacity: 0 }, visible: { opacity: 1 }, exit: { opacity: 0 } }
    : {
        hidden: { opacity: 0 },
        visible: { opacity: 1, transition: { duration: 0.18, ease: 'easeOut' as const } },
        exit: { opacity: 0, transition: { duration: 0.18, ease: 'easeOut' as const } },
      };

  const positionClasses = isLeft
    ? 'left-0 top-0 bottom-0'
    : 'right-0 top-0 bottom-0';

  return createPortal(
    <AnimatePresence>
      {open && (
        <div className="fixed inset-0 z-50">
          {/* Backdrop */}
          <motion.div
            className="absolute inset-0 bg-black/35 backdrop-blur-sm"
            style={{ WebkitBackdropFilter: 'blur(4px)' }}
            variants={backdropVariants}
            initial="hidden"
            animate="visible"
            exit="exit"
            onClick={onClose}
            aria-hidden="true"
          />

          {/* Drawer content */}
          <motion.div
            ref={contentRef}
            role="dialog"
            aria-modal="true"
            aria-label={ariaLabel}
            variants={slideVariants}
            initial="hidden"
            animate="visible"
            exit="exit"
            className={[
              'fixed h-full w-[420px] max-w-[85vw] bg-cream-50 shadow-warm-xl overflow-y-auto',
              positionClasses,
              className,
            ]
              .filter(Boolean)
              .join(' ')}
          >
            {children}
          </motion.div>
        </div>
      )}
    </AnimatePresence>,
    document.body
  );
};

void colors;
void animation;

export default Drawer;
