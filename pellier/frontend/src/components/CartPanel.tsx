/**
 * CartPanel - slide-over bag panel in the Pellier daylight palette.
 *
 * Cream background, espresso text, warm borders. Replaces the
 * Apple-dark-theme CSS vars with inline pellier values so the
 * panel matches the rest of the storefront without needing a
 * global theme class on <html>.
 *
 * Checkout triggers an in-panel confirmation state (no alert())
 * with a checkmark animation and "Continue shopping" reset.
 */
import { useEffect, useState } from 'react'
import {
  X,
  ShoppingBag,
  Plus,
  Minus,
  ChevronRight,
  Package,
  Check,
  AlertCircle,
  Clock3,
  FileCheck2,
  ShieldCheck,
} from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import { useCart } from '../contexts/CartContext'
import { useAuth } from '../contexts/AuthContext'
import { imageSrc } from '../utils/assetPath'

// Re-export CartItem for backward compatibility with existing import paths
export type { CartItem } from '../contexts/CartContext'

// --- Pellier palette tokens (inline to avoid dark-theme var fallthrough) ---
const BG = 'var(--cream-warm)'
const BG_CARD = 'color-mix(in srgb, var(--dl-ink) 4%, transparent)'
const TEXT = 'var(--ink)'
const TEXT_SOFT = 'var(--ink-soft)'
const TEXT_QUIET = 'var(--ink-quiet)'
const BORDER = 'color-mix(in srgb, var(--dl-ink) 8%, transparent)'
const GREEN = '#2d8a56'

interface CartPanelProps {
  isOpen: boolean
  onClose: () => void
}

const CartPanel = ({ isOpen, onClose }: CartPanelProps) => {
  const {
    items,
    updateQuantity,
    removeFromCart,
    handleCheckout,
    confirmAndPlaceOrder,
    checkoutStage,
    checkoutQuote,
    checkoutReceipt,
    checkoutError,
    checkoutComplete,
    resetCheckout,
    clearCart,
  } = useCart()
  const { isAuthenticated, login } = useAuth()
  const [acknowledged, setAcknowledged] = useState(false)

  const total = items.reduce((sum, item) => sum + item.price * item.quantity, 0)
  const itemCount = items.reduce((sum, item) => sum + item.quantity, 0)
  const isWorking = ['quoting', 'confirming', 'executing'].includes(checkoutStage)
  const needsSignIn =
    !isAuthenticated
    && (checkoutError?.code === 'sign_in_required'
      || checkoutError?.code === 'auth_failed')
  const quoteExpires = checkoutQuote
    ? new Date(checkoutQuote.expiresAt).toLocaleTimeString([], {
        hour: 'numeric',
        minute: '2-digit',
      })
    : null

  useEffect(() => {
    setAcknowledged(false)
  }, [checkoutQuote?.quoteId])

  return (
    <AnimatePresence>
      {isOpen && (
        <>
          {/* Backdrop */}
          <motion.div
            className="fixed inset-0 z-50"
            style={{
              background: 'rgba(31, 20, 16, 0.35)',
              backdropFilter: 'blur(8px)',
              WebkitBackdropFilter: 'blur(8px)',
            }}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.25 }}
            onClick={onClose}
          />

          {/* Panel */}
          <motion.div
            className="fixed right-0 top-0 h-full w-full sm:w-[420px] z-50 flex flex-col font-sans"
            style={{
              background: BG,
              boxShadow: '-4px 0 32px rgba(31, 20, 16, 0.15)',
            }}
            initial={{ x: '100%' }}
            animate={{ x: 0 }}
            exit={{ x: '100%' }}
            transition={{ type: 'spring', stiffness: 320, damping: 34 }}
          >
            {/* ── Header ── */}
            <div className="px-7 pt-7 pb-5">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <h2
                    className="font-display"
                    style={{
                      fontSize: '24px',
                      color: TEXT,
                      fontWeight: 400,
                      letterSpacing: '-0.01em',
                    }}
                  >
                    Your Bag
                  </h2>
                  {itemCount > 0 && !checkoutComplete && (
                    <motion.span
                      key={itemCount}
                      initial={{ scale: 0.6, opacity: 0 }}
                      animate={{ scale: 1, opacity: 1 }}
                      className="text-xs font-semibold px-2 py-0.5 rounded-full"
                      style={{ background: TEXT, color: BG }}
                    >
                      {itemCount}
                    </motion.span>
                  )}
                </div>
                <div className="flex items-center gap-1">
                  {items.length > 0 && !checkoutComplete && (
                    <button
                      onClick={clearCart}
                      className="text-xs font-medium px-3 py-1.5 rounded-full transition-all duration-200
                               hover:bg-[rgba(168,66,58,0.08)] active:scale-95"
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

            {/* ── Checkout confirmation state ── */}
            {checkoutComplete ? (
              <div className="flex-1 overflow-y-auto px-8 py-10 text-center">
                <motion.div
                  initial={{ scale: 0, opacity: 0 }}
                  animate={{ scale: 1, opacity: 1 }}
                  transition={{ type: 'spring', stiffness: 260, damping: 20 }}
                  className="w-20 h-20 rounded-full flex items-center justify-center mb-6"
                  style={{
                    background:
                      checkoutReceipt?.status === 'paid'
                        ? 'rgba(45, 138, 86, 0.12)'
                        : 'rgba(168, 66, 58, 0.10)',
                    marginLeft: 'auto',
                    marginRight: 'auto',
                  }}
                >
                  {checkoutReceipt?.status === 'paid' ? (
                    <Check className="h-9 w-9" style={{ color: GREEN }} strokeWidth={2.5} />
                  ) : (
                    <AlertCircle className="h-9 w-9" style={{ color: '#a8423a' }} strokeWidth={2.2} />
                  )}
                </motion.div>
                <motion.h3
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 0.15 }}
                  className="font-display mb-2"
                  style={{ fontSize: '26px', color: TEXT, fontWeight: 400 }}
                >
                  {checkoutReceipt?.status === 'paid'
                    ? 'Order placed.'
                    : checkoutReceipt?.status === 'payment_declined'
                      ? 'Payment was declined.'
                      : 'Payment did not complete.'}
                </motion.h3>
                <motion.p
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 0.25 }}
                  style={{ fontSize: '14px', lineHeight: 1.6, color: TEXT_SOFT }}
                >
                  {checkoutReceipt?.status === 'paid'
                    ? `${checkoutReceipt.orderNumber} is recorded with its payment and inventory evidence.`
                    : 'The order did not complete. Reserved inventory was returned to the catalog.'}
                </motion.p>
                {checkoutReceipt && (
                  <motion.div
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 0.3 }}
                    className="mt-7 w-full p-4 text-left rounded-lg"
                    style={{ border: `1px solid ${BORDER}`, background: BG_CARD }}
                  >
                    <div className="flex items-center gap-2 mb-3">
                      <FileCheck2 className="h-4 w-4" style={{ color: TEXT }} />
                      <span className="font-semibold" style={{ fontSize: '13px', color: TEXT }}>
                        Evidence receipt
                      </span>
                    </div>
                    <div className="space-y-2" style={{ fontSize: '12px', color: TEXT_SOFT }}>
                      <div className="flex justify-between gap-4">
                        <span>Confirmed total</span>
                        <span className="font-semibold" style={{ color: TEXT }}>
                          ${checkoutReceipt.amounts.total}
                        </span>
                      </div>
                      <div className="flex justify-between gap-4">
                        <span>Receipt</span>
                        <span className="font-semibold" style={{ color: TEXT }}>
                          {checkoutReceipt.receipt.verified ? 'Verified' : 'Verification failed'}
                        </span>
                      </div>
                      <div className="flex justify-between gap-4">
                        <span>Inventory</span>
                        <span className="font-semibold capitalize" style={{ color: TEXT }}>
                          {checkoutReceipt.evidence.inventory.status}
                        </span>
                      </div>
                      <div className="flex justify-between gap-4">
                        <span>Payment</span>
                        <span className="font-semibold capitalize" style={{ color: TEXT }}>
                          Sandbox {checkoutReceipt.payment.status}
                        </span>
                      </div>
                    </div>
                    <div
                      className="mt-3 pt-3 font-mono break-all"
                      style={{
                        borderTop: `1px solid ${BORDER}`,
                        fontSize: '10px',
                        lineHeight: 1.5,
                        color: TEXT_QUIET,
                      }}
                    >
                      Receipt {checkoutReceipt.receipt.receiptHash}
                    </div>
                  </motion.div>
                )}
                <motion.button
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 0.4 }}
                  onClick={resetCheckout}
                  whileHover={{ scale: 1.02 }}
                  whileTap={{ scale: 0.98 }}
                  className="mt-7 px-8 py-3 rounded-full font-medium text-[14px] tracking-wide transition-shadow duration-200"
                  style={{
                    background: TEXT,
                    color: BG,
                    border: 'none',
                    cursor: 'pointer',
                  }}
                >
                  {checkoutReceipt?.status === 'paid' ? 'Continue shopping' : 'Return to bag'}
                </motion.button>
                <motion.p
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ delay: 0.55 }}
                  className="mt-4"
                  style={{ fontSize: '11px', color: TEXT_QUIET, letterSpacing: '0.04em' }}
                >
                  Sandbox payment. No card was charged.
                </motion.p>
              </div>
            ) : (
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
                        className="font-display mb-1.5"
                        style={{ fontSize: '20px', color: TEXT }}
                      >
                        Your bag is empty
                      </p>
                      <p style={{ fontSize: '14px', lineHeight: 1.55, color: TEXT_QUIET }}>
                        Items you add from chat or the grid will appear here
                      </p>
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
                                      className="px-2.5 py-1.5 transition-colors duration-150"
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
                                      className="px-2.5 py-1.5 transition-colors duration-150"
                                      style={{ color: TEXT, background: 'transparent' }}
                                      aria-label="Increase quantity"
                                    >
                                      <Plus className="h-3 w-3" strokeWidth={2.5} />
                                    </button>
                                  </div>

                                  {/* Remove */}
                                  <button
                                    onClick={() => removeFromCart(item.productId)}
                                    className="text-[11px] font-medium px-2 py-1 rounded-md transition-all duration-200
                                             hover:bg-[rgba(168,66,58,0.08)] active:scale-95"
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
                    {checkoutError && (
                      <div
                        className="mb-4 p-3 rounded-lg flex gap-2.5"
                        style={{
                          border: '1px solid rgba(168, 66, 58, 0.22)',
                          background: 'rgba(168, 66, 58, 0.06)',
                        }}
                        role="alert"
                      >
                        <AlertCircle
                          className="h-4 w-4 mt-0.5 flex-shrink-0"
                          style={{ color: '#a8423a' }}
                        />
                        <p style={{ fontSize: '12px', lineHeight: 1.5, color: TEXT_SOFT }}>
                          {checkoutError.message}
                        </p>
                      </div>
                    )}

                    {checkoutQuote ? (
                      <>
                        <div className="space-y-2 mb-4" style={{ fontSize: '13px' }}>
                          <div className="flex justify-between">
                            <span style={{ color: TEXT_SOFT }}>Subtotal</span>
                            <span style={{ color: TEXT }}>${checkoutQuote.amounts.subtotal}</span>
                          </div>
                          <div className="flex justify-between">
                            <span style={{ color: TEXT_SOFT }}>Shipping</span>
                            <span style={{ color: TEXT }}>${checkoutQuote.amounts.shipping}</span>
                          </div>
                          <div className="flex justify-between">
                            <span style={{ color: TEXT_SOFT }}>Tax</span>
                            <span style={{ color: TEXT }}>${checkoutQuote.amounts.tax}</span>
                          </div>
                        </div>
                        <div
                          className="flex items-center justify-between mb-4 pt-4"
                          style={{ borderTop: `1px solid ${BORDER}` }}
                        >
                          <span className="font-semibold" style={{ fontSize: '16px', color: TEXT }}>
                            Confirmed total
                          </span>
                          <span className="font-bold" style={{ fontSize: '22px', color: TEXT }}>
                            ${checkoutQuote.amounts.total}
                          </span>
                        </div>
                        <label
                          className="flex items-start gap-3 mb-4 cursor-pointer"
                          style={{ fontSize: '12px', lineHeight: 1.45, color: TEXT_SOFT }}
                        >
                          <input
                            type="checkbox"
                            checked={acknowledged}
                            onChange={event => setAcknowledged(event.target.checked)}
                            className="mt-0.5 h-4 w-4 accent-[#1f1410]"
                          />
                          <span>
                            I confirm this ${checkoutQuote.amounts.total} total and authorize this
                            sandbox order.
                          </span>
                        </label>
                        <div className="flex items-center gap-2 mb-4" style={{ color: TEXT_QUIET }}>
                          <Clock3 className="h-3.5 w-3.5" />
                          <span style={{ fontSize: '11px' }}>Quote valid until {quoteExpires}</span>
                        </div>
                      </>
                    ) : (
                      <>
                        <div className="flex items-center justify-between mb-2">
                          <span style={{ fontSize: '14px', color: TEXT_SOFT }}>
                            Subtotal ({itemCount} {itemCount === 1 ? 'item' : 'items'})
                          </span>
                          <span className="font-medium" style={{ fontSize: '14px', color: TEXT }}>
                            ${total.toFixed(2)}
                          </span>
                        </div>
                        <div className="flex items-center justify-between mb-5">
                          <span style={{ fontSize: '13px', color: TEXT_SOFT }}>
                            Shipping and tax
                          </span>
                          <span style={{ fontSize: '12px', color: TEXT_QUIET }}>
                            Calculated in review
                          </span>
                        </div>
                      </>
                    )}

                    <motion.button
                      onClick={() => {
                        if (needsSignIn) {
                          login()
                        } else if (checkoutQuote) {
                          void confirmAndPlaceOrder()
                        } else {
                          void handleCheckout()
                        }
                      }}
                      disabled={isWorking || (!!checkoutQuote && !acknowledged)}
                      whileHover={{ scale: 1.015 }}
                      whileTap={{ scale: 0.98 }}
                      className="w-full py-3.5 rounded-full font-medium flex items-center justify-center gap-2 transition-shadow duration-200"
                      style={{
                        fontSize: '15px',
                        letterSpacing: '0.02em',
                        background: TEXT,
                        color: BG,
                        border: 'none',
                        cursor:
                          isWorking || (!!checkoutQuote && !acknowledged)
                            ? 'not-allowed'
                            : 'pointer',
                        opacity: isWorking || (!!checkoutQuote && !acknowledged) ? 0.55 : 1,
                        boxShadow: '0 2px 12px rgba(31, 20, 16, 0.15)',
                      }}
                    >
                      {needsSignIn
                        ? 'Sign in to continue'
                        : checkoutStage === 'quoting'
                          ? 'Checking price and availability'
                          : checkoutStage === 'confirming'
                            ? 'Recording confirmation'
                            : checkoutStage === 'executing'
                              ? 'Placing sandbox order'
                              : checkoutQuote
                                ? 'Confirm and place order'
                                : 'Review order'}
                      {checkoutQuote ? (
                        <ShieldCheck className="h-4 w-4" strokeWidth={2.3} />
                      ) : (
                        <ChevronRight className="h-4 w-4" strokeWidth={2.5} />
                      )}
                    </motion.button>

                    <p
                      className="text-center mt-3"
                      style={{
                        fontSize: '11px',
                        letterSpacing: '0.04em',
                        color: TEXT_QUIET,
                      }}
                    >
                      {checkoutQuote
                        ? 'Identity, consent, inventory, and payment state are recorded.'
                        : 'Prices and availability are verified before confirmation.'}
                    </p>
                  </motion.div>
                )}
              </>
            )}
          </motion.div>
        </>
      )}
    </AnimatePresence>
  )
}

export default CartPanel
