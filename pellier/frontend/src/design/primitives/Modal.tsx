import React, { useEffect, useRef, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { AnimatePresence, motion } from 'framer-motion';
import { colors, radii, shadows, animation } from '../tokens';

export interface ModalProps {
  open: boolean;
  onClose: () => void;
  children: React.ReactNode;
  ariaLabel: string;
}

const FOCUSABLE_SELECTOR =
  'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';

/**
 * Modal primitive — focus trap, Escape close, portal to body.
 *
 * Framer Motion: AnimatePresence, fade backdrop 180ms, scale+fade content 240ms.
 * Respects prefers-reduced-motion: opacity-only when reduced.
 */
export const Modal: React.FC<ModalProps> = ({
  open,
  onClose,
  children,
  ariaLabel,
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

      const modal = contentRef.current;
      if (!modal) return;

      const focusable = Array.from(
        modal.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)
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

  // Attach/detach key listener and auto-focus
  useEffect(() => {
    if (!open) return;

    document.addEventListener('keydown', handleKeyDown);

    // Auto-focus first focusable element
    const timer = setTimeout(() => {
      const modal = contentRef.current;
      if (!modal) return;
      const first = modal.querySelector<HTMLElement>(FOCUSABLE_SELECTOR);
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

  const backdropVariants = reducedMotion
    ? { hidden: { opacity: 0 }, visible: { opacity: 1 }, exit: { opacity: 0 } }
    : {
        hidden: { opacity: 0 },
        visible: { opacity: 1, transition: { duration: 0.18, ease: 'easeOut' as const } },
        exit: { opacity: 0, transition: { duration: 0.18, ease: 'easeOut' as const } },
      };

  const contentVariants = reducedMotion
    ? { hidden: { opacity: 0 }, visible: { opacity: 1 }, exit: { opacity: 0 } }
    : {
        hidden: { opacity: 0, scale: 0.95 },
        visible: {
          opacity: 1,
          scale: 1,
          transition: { duration: 0.24, ease: 'easeOut' as const },
        },
        exit: {
          opacity: 0,
          scale: 0.95,
          transition: { duration: 0.18, ease: 'easeOut' as const },
        },
      };

  return createPortal(
    <AnimatePresence>
      {open && (
        <motion.div
          className="fixed inset-0 z-50 flex items-center justify-center"
          initial="hidden"
          animate="visible"
          exit="exit"
        >
          {/* Backdrop */}
          <motion.div
            className="absolute inset-0 bg-black/35 backdrop-blur-sm"
            style={{ WebkitBackdropFilter: 'blur(4px)' }}
            variants={backdropVariants}
            onClick={onClose}
            aria-hidden="true"
          />

          {/* Content */}
          <motion.div
            ref={contentRef}
            role="dialog"
            aria-modal="true"
            aria-label={ariaLabel}
            variants={contentVariants}
            className="relative bg-cream-50 rounded-2xl shadow-warm-xl max-w-lg w-full mx-4 p-8 z-10"
          >
            {children}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>,
    document.body
  );
};

void colors;
void radii;
void shadows;
void animation;

export default Modal;
