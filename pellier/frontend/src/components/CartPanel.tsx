/**
 * CartPanel - slide-over bag panel.
 *
 * Every color is a Daylight token, so the panel follows the light and
 * dark themes with the rest of the storefront. Filled controls are ink
 * with on-ink text.
 *
 * The bag is a list of pieces the shopper liked. Pellier is a workshop
 * store and places no orders, so the panel has no checkout.
 */
import { useEffect, useRef } from 'react'
import { createPortal } from 'react-dom'
import { X, ShoppingBag, Plus, Minus, Package } from 'lucide-react'
import { motion, AnimatePresence, useReducedMotion } from 'motion/react'
import { useCart } from '../contexts/CartContext'
import { imageSrc } from '../utils/assetPath'
import { useFocusTrap } from '../shared/useFocusTrap'

// Re-export CartItem for backward compatibility with existing import paths
export type { CartItem } from '../contexts/CartContext'

// --- Theme tokens for the inline styles below ---
const BG = 'var(--cream-warm)'
const BG_CARD = 'var(--dl-paper-2)'
const TEXT = 'var(--ink)'
const TEXT_SOFT = 'var(--ink-soft)'
const TEXT_QUIET = 'var(--ink-quiet)'
const BORDER = 'var(--dl-line)'
const ON_TEXT = 'var(--dl-on-ink)'

interface CartPanelProps {
  isOpen: boolean
  onClose: () => void
}

const CartPanel = ({ isOpen, onClose }: CartPanelProps) => {
  const { items, updateQuantity, removeFromCart, clearCart } = useCart()
  const panelRef = useRef<HTMLDivElement>(null)
  const reducedMotion = useReducedMotion()
  useFocusTrap({ containerRef: panelRef, active: isOpen, onClose })

  useEffect(() => {
    if (!isOpen) return
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => { document.body.style.overflow = previousOverflow }
  }, [isOpen])

  const total = items.reduce((sum, item) => sum + item.price * item.quantity, 0)
  const itemCount = items.reduce((sum, item) => sum + item.quantity, 0)

  return createPortal(
    <AnimatePresence>
      {isOpen && (
        <>
          {/* Backdrop */}
          <motion.div
            className="fixed inset-0 z-[60]"
            style={{
              background: 'var(--dl-scrim)',
              backdropFilter: 'blur(8px)',
              WebkitBackdropFilter: 'blur(8px)',
            }}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: reducedMotion ? 0 : 0.25 }}
            onClick={onClose}
          />

          {/* Panel */}
          <motion.div
            ref={panelRef}
            role="dialog"
            aria-modal="true"
            aria-labelledby="shopping-bag-title"
            className="fixed right-0 top-0 h-dvh w-full sm:w-[420px] z-[61] flex flex-col font-sans"
            style={{
              background: BG,
              boxShadow: 'var(--dl-sh-deep)',
            }}
            initial={reducedMotion ? false : { x: '100%' }}
            animate={{ x: 0 }}
            exit={{ x: '100%' }}
            transition={reducedMotion ? { duration: 0 } : { type: 'spring', stiffness: 320, damping: 34 }}
          >
            {/* ── Header ── */}
            <div className="px-7 pt-7 pb-5">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <h2
                    id="shopping-bag-title"
                    className="font-sans"
                    style={{
                      fontSize: '24px',
                      color: TEXT,
                      fontWeight: 400,
                      letterSpacing: '-0.01em',
                    }}
                  >
                    Your bag
                  </h2>
                  {itemCount > 0 && (
                    <motion.span
                      key={itemCount}
                      initial={{ scale: 0.6, opacity: 0 }}
                      animate={{ scale: 1, opacity: 1 }}
                      className="text-xs font-semibold px-2 py-0.5 rounded-full"
                      style={{ background: TEXT, color: ON_TEXT }}
                    >
                      {itemCount}
                    </motion.span>
                  )}
                </div>
                <div className="flex items-center gap-1">
                  {items.length > 0 && (
                    <button
                      onClick={clearCart}
                      className="text-xs font-medium px-3 py-1.5 rounded-full transition-all duration-200
                               hover:bg-err-tint active:scale-95"
                      style={{ color: TEXT_QUIET }}
                    >
                      Clear all
                    </button>
                  )}
                  <button
                    onClick={onClose}
                    className="p-2 rounded-full transition-all duration-200 hover:scale-105 active:scale-95"
                    style={{ background: BG_CARD }}
                    aria-label="Close bag"
                  >
                    <X className="h-4 w-4" style={{ color: TEXT_SOFT }} strokeWidth={2.5} />
                  </button>
                </div>
              </div>
            </div>

            {/* Divider */}
            <div className="mx-7" style={{ height: '1px', background: BORDER }} />

            <>
                {/* ── Cart Items ── */}
                <div className="flex-1 overflow-y-auto">
                  {items.length === 0 ? (
                    <div className="flex flex-col items-center justify-center h-full text-center px-8">
                      <motion.div
                        initial={{ scale: 0.8, opacity: 0 }}
                        animate={{ scale: 1, opacity: 1 }}
                        transition={{ delay: 0.15, type: 'spring', stiffness: 200 }}
                        className="w-20 h-20 rounded-full flex items-center justify-center mb-5"
                        style={{ background: BG_CARD }}
                      >
                        <ShoppingBag className="h-8 w-8" style={{ color: TEXT_QUIET }} strokeWidth={1.5} />
                      </motion.div>
                      <p
                        className="font-sans mb-1.5"
                        style={{ fontSize: '20px', color: TEXT }}
                      >
                        Your bag is empty
                      </p>
                      <p style={{ fontSize: '14px', lineHeight: 1.55, color: TEXT_QUIET }}>
                        Pieces you add from the collection or a conversation will appear here.
                      </p>
                      <button type="button" onClick={onClose} className="mt-6 min-h-11 rounded-full px-6 py-3 text-sm font-medium focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2" style={{ background: TEXT, color: ON_TEXT }}>
                        Continue browsing
                      </button>
                    </div>
                  ) : (
                    <div className="px-7 py-5">
                      <AnimatePresence initial={false}>
                        {items.map((item, index) => (
                          <motion.div
                            key={item.productId}
                            layout
                            initial={{ opacity: 0, y: 12 }}
                            animate={{ opacity: 1, y: 0 }}
                            exit={{ opacity: 0, x: 60, transition: { duration: 0.2 } }}
                            transition={{ duration: 0.25, delay: index * 0.03 }}
                          >
                            <div className="flex gap-4 py-4">
                              {/* Product Image */}
                              <div
                                className="w-[72px] h-[72px] rounded-[var(--pellier-image-radius-sm)] flex-shrink-0 overflow-hidden flex items-center justify-center"
                                style={{ background: BG_CARD }}
                              >
                                {item.image ? (
                                  <img
                                    src={imageSrc(item.image)}
                                    alt={item.name}
                                    className="w-full h-full object-cover"
                                  />
                                ) : (
                                  <Package className="h-6 w-6" style={{ color: TEXT_QUIET }} strokeWidth={1.5} />
                                )}
                              </div>

                              {/* Product Details */}
                              <div className="flex-1 min-w-0 flex flex-col justify-between">
                                <div>
                                  <h3
                                    className="font-medium leading-snug line-clamp-2 mb-1"
                                    style={{ fontSize: '13px', color: TEXT }}
                                  >
                                    {item.name}
                                  </h3>
                                  <div className="flex items-center gap-2">
                                    <span
                                      className="font-semibold"
                                      style={{ fontSize: '15px', color: TEXT }}
                                    >
                                      ${(item.price * item.quantity).toFixed(2)}
                                    </span>
                                    {item.quantity > 1 && (
                                      <span style={{ fontSize: '11px', color: TEXT_QUIET }}>
                                        ${item.price.toFixed(2)} each
                                      </span>
                                    )}
                                  </div>
                                </div>

                                {/* Quantity + Remove */}
                                <div className="flex items-center justify-between mt-2.5">
                                  {/* Pill Stepper */}
                                  <div
                                    className="inline-flex items-center gap-0 rounded-full overflow-hidden"
                                    style={{ border: `1px solid ${BORDER}` }}
                                  >
                                    <button
                                      onClick={() =>
                                        updateQuantity(item.productId, Math.max(1, item.quantity - 1))
                                      }
                                      type="button"
                                      className="inline-flex h-11 w-11 items-center justify-center transition-colors duration-150"
                                      style={{
                                        color: item.quantity <= 1 ? TEXT_QUIET : TEXT,
                                        background: 'transparent',
                                      }}
                                      aria-label="Decrease quantity"
                                    >
                                      <Minus className="h-3 w-3" strokeWidth={2.5} />
                                    </button>
                                    <motion.span
                                      key={item.quantity}
                                      initial={{ scale: 0.7, opacity: 0 }}
                                      animate={{ scale: 1, opacity: 1 }}
                                      className="text-xs font-semibold w-7 text-center tabular-nums"
                                      style={{ color: TEXT }}
                                    >
                                      {item.quantity}
                                    </motion.span>
                                    <button
                                      onClick={() => updateQuantity(item.productId, item.quantity + 1)}
                                      type="button"
                                      className="inline-flex h-11 w-11 items-center justify-center transition-colors duration-150"
                                      style={{ color: TEXT, background: 'transparent' }}
                                      aria-label="Increase quantity"
                                    >
                                      <Plus className="h-3 w-3" strokeWidth={2.5} />
                                    </button>
                                  </div>

                                  {/* Remove */}
                                  <button
                                    onClick={() => removeFromCart(item.productId)}
                                    type="button"
                                    className="inline-flex min-h-11 items-center rounded-md px-3 text-[13px] font-medium transition-all duration-200
                                             hover:bg-err-tint active:scale-95"
                                    style={{ color: TEXT_QUIET }}
                                  >
                                    Remove
                                  </button>
                                </div>
                              </div>
                            </div>

                            {/* Divider between items */}
                            {index < items.length - 1 && (
                              <div style={{ height: '1px', background: BORDER }} />
                            )}
                          </motion.div>
                        ))}
                      </AnimatePresence>
                    </div>
                  )}
                </div>

                {/* ── Footer ── */}
                {items.length > 0 && (
                  <motion.div
                    className="px-7 pb-7 pt-5"
                    style={{ borderTop: `1px solid ${BORDER}` }}
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 0.1 }}
                  >
                    <div className="flex items-center justify-between">
                      <span style={{ fontSize: '14px', color: TEXT_SOFT }}>
                        Subtotal ({itemCount} {itemCount === 1 ? 'item' : 'items'})
                      </span>
                      <span className="font-medium" style={{ fontSize: '14px', color: TEXT }}>
                        ${total.toFixed(2)}
                      </span>
                    </div>
                    <p className="mt-3" style={{ fontSize: '12px', lineHeight: 1.5, color: TEXT_QUIET }}>
                      Pellier is a workshop store, so your bag keeps a list and places no order.
                    </p>
                  </motion.div>
                )}
            </>
          </motion.div>
        </>
      )}
    </AnimatePresence>,
    document.body,
  )
}

export default CartPanel
