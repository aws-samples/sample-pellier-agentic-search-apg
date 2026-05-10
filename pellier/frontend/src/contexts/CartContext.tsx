/**
 * Cart Context — Centralizes cart state, checkout metrics, and toast notifications.
 * Replaces prop-threaded cart state from App.tsx and the window.addToCart global.
 */
import { createContext, useContext, useState, useCallback, useEffect, useRef, type ReactNode } from 'react'
import { useLayout, type WorkshopMode } from './LayoutContext'

// --- Types ---

export type CartItemOrigin = 'manual' | 'search-quick-add' | 'chat' | 'bundle' | 'memory'

export interface CartItem {
  productId: number
  name: string
  price: number
  quantity: number
  image?: string
  origin: CartItemOrigin
  addedAt: number
}

interface CartAdditionEvent {
  origin: CartItemOrigin
  timestamp: number
}

export interface CheckoutMetrics {
  searchCount: number
  productViews: number
  additions: CartAdditionEvent[]
}

interface PreviousModeSnapshot {
  mode: WorkshopMode
  totalSteps: number
}

interface CartContextValue {
  items: CartItem[]
  metrics: CheckoutMetrics
  previousModeSteps: PreviousModeSnapshot | null
  cartOpen: boolean
  setCartOpen: (open: boolean) => void
  showToast: boolean
  toastMessage: string
  dismissToast: () => void
  /** Fire a one-off toast from any consumer (e.g., "Wishlist is coming soon"). */
  notify: (message: string) => void
  addToCart: (product: { productId: number; name: string; price: number; image?: string; origin: CartItemOrigin }) => void
  addAllToCart: (products: Array<{ productId: number; name: string; price: number; image?: string }>, origin: CartItemOrigin) => void
  updateQuantity: (productId: number, quantity: number) => void
  removeFromCart: (productId: number) => void
  clearCart: () => void
  handleCheckout: () => void
  checkoutComplete: boolean
  resetCheckout: () => void
  incrementSearch: () => void
  incrementProductView: () => void
}

// --- Context + Hook ---

const CartContext = createContext<CartContextValue | undefined>(undefined)

export function useCart() {
  const ctx = useContext(CartContext)
  if (!ctx) throw new Error('useCart must be used within CartProvider')
  return ctx
}

// --- Helpers ---

const STORAGE_KEY = 'pellier-cart'
const CART_SESSION_KEY = 'pellier-cart-session'

function hydrateItems(): CartItem[] {
  try {
    // Session-scope the cart: if the browser session is fresh (no
    // session ID stored) or the session ID changed (persona switch,
    // new tab), start with an empty cart rather than resurfacing
    // phantom items from a prior persona or demo run. Items added
    // during the current session will re-persist normally.
    const currentSession = sessionStorage.getItem('pellier-session-id') || ''
    const cartSession = localStorage.getItem(CART_SESSION_KEY) || ''
    if (!currentSession || currentSession !== cartSession) {
      // Stale or first load — clear the persisted cart and record
      // the new session so subsequent navigations within the same
      // session keep their cart.
      localStorage.removeItem(STORAGE_KEY)
      if (currentSession) {
        localStorage.setItem(CART_SESSION_KEY, currentSession)
      }
      return []
    }

    const saved = localStorage.getItem(STORAGE_KEY)
    if (saved) {
      const parsed = JSON.parse(saved) as Array<Partial<CartItem>>
      return parsed.map(item => ({
        productId: item.productId ?? 0,
        name: item.name ?? '',
        price: item.price ?? 0,
        quantity: item.quantity ?? 1,
        image: item.image,
        origin: item.origin ?? 'manual',
        addedAt: item.addedAt ?? 0,
      }))
    }
  } catch { /* ignore corrupt data */ }
  return []
}

function emptyMetrics(): CheckoutMetrics {
  return { searchCount: 0, productViews: 0, additions: [] }
}

function totalSteps(m: CheckoutMetrics): number {
  return m.searchCount + m.productViews + m.additions.length
}

// --- Provider ---

export function CartProvider({ children }: { children: ReactNode }) {
  const { workshopMode } = useLayout()

  // Cart items
  const [items, setItems] = useState<CartItem[]>(hydrateItems)

  // Checkout metrics
  const [metrics, setMetrics] = useState<CheckoutMetrics>(emptyMetrics)
  const [previousModeSteps, setPreviousModeSteps] = useState<PreviousModeSnapshot | null>(null)

  // UI state
  const [cartOpen, setCartOpen] = useState(false)
  const [checkoutComplete, setCheckoutComplete] = useState(false)
  const [showToast, setShowToast] = useState(false)
  const [toastMessage, setToastMessage] = useState('')

  // Track mode changes — skip initial mount
  const prevModeRef = useRef(workshopMode)
  const isMounted = useRef(false)

  useEffect(() => {
    if (!isMounted.current) {
      isMounted.current = true
      return
    }
    // Workshop mode changed — snapshot current steps, then reset
    const prevMode = prevModeRef.current
    const steps = totalSteps(metrics)
    if (steps > 0) {
      setPreviousModeSteps({ mode: prevMode, totalSteps: steps })
    }
    setMetrics(emptyMetrics())
    prevModeRef.current = workshopMode
  }, [workshopMode]) // eslint-disable-line react-hooks/exhaustive-deps -- intentional: only fire on mode change

  // Persist cart to localStorage + stamp the session so stale carts
  // from prior sessions don't resurrect on the next page load.
  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(items))
    try {
      const sid = sessionStorage.getItem('pellier-session-id')
      if (sid) localStorage.setItem(CART_SESSION_KEY, sid)
    } catch { /* ignore */ }
  }, [items])

  // --- Cart operations ---

  const toast = useCallback((msg: string) => {
    setToastMessage(msg)
    setShowToast(true)
  }, [])

  const dismissToast = useCallback(() => {
    setShowToast(false)
  }, [])

  const addToCart = useCallback((product: { productId: number; name: string; price: number; image?: string; origin: CartItemOrigin }) => {
    const now = Date.now()
    setItems(prev => {
      const existing = prev.find(i => i.productId === product.productId)
      if (existing) {
        toast(`Updated quantity for ${product.name.substring(0, 30)}...`)
        return prev.map(i =>
          i.productId === product.productId
            ? { ...i, quantity: i.quantity + 1, origin: product.origin, addedAt: now }
            : i
        )
      }
      toast(`Added ${product.name.substring(0, 30)}... to cart`)
      return [...prev, {
        productId: product.productId,
        name: product.name,
        price: product.price,
        quantity: 1,
        image: product.image,
        origin: product.origin,
        addedAt: now,
      }]
    })
    setMetrics(prev => ({
      ...prev,
      additions: [...prev.additions, { origin: product.origin, timestamp: now }],
    }))
    setCartOpen(true)
  }, [toast])

  const addAllToCart = useCallback((products: Array<{ productId: number; name: string; price: number; image?: string }>, origin: CartItemOrigin) => {
    const now = Date.now()
    setItems(prev => {
      let updated = [...prev]
      for (const product of products) {
        const idx = updated.findIndex(i => i.productId === product.productId)
        if (idx >= 0) {
          updated = updated.map((item, i) =>
            i === idx ? { ...item, quantity: item.quantity + 1, origin, addedAt: now } : item
          )
        } else {
          updated.push({
            productId: product.productId,
            name: product.name,
            price: product.price,
            quantity: 1,
            image: product.image,
            origin,
            addedAt: now,
          })
        }
      }
      return updated
    })
    // Single event for the entire bundle
    setMetrics(prev => ({
      ...prev,
      additions: [...prev.additions, { origin, timestamp: now }],
    }))
    toast(`Added ${products.length} items to cart`)
    setCartOpen(true)
  }, [toast])

  const updateQuantity = useCallback((productId: number, quantity: number) => {
    if (quantity <= 0) {
      setItems(prev => prev.filter(item => item.productId !== productId))
    } else {
      setItems(prev =>
        prev.map(item =>
          item.productId === productId ? { ...item, quantity } : item
        )
      )
    }
  }, [])

  const removeFromCart = useCallback((productId: number) => {
    setItems(prev => prev.filter(item => item.productId !== productId))
  }, [])

  const clearCart = useCallback(() => {
    if (confirm('Are you sure you want to clear your cart?')) {
      setItems([])
      toast('Cart cleared')
    }
  }, [toast])

  const handleCheckout = useCallback(() => {
    setCheckoutComplete(true)
  }, [])

  const resetCheckout = useCallback(() => {
    setCheckoutComplete(false)
    setItems([])
    setCartOpen(false)
    toast('Order complete — demo reset')
  }, [toast])

  const incrementSearch = useCallback(() => {
    setMetrics(prev => ({ ...prev, searchCount: prev.searchCount + 1 }))
  }, [])

  const incrementProductView = useCallback(() => {
    setMetrics(prev => ({ ...prev, productViews: prev.productViews + 1 }))
  }, [])

  return (
    <CartContext.Provider value={{
      items,
      metrics,
      previousModeSteps,
      cartOpen,
      setCartOpen,
      showToast,
      toastMessage,
      dismissToast,
      notify: toast,
      addToCart,
      addAllToCart,
      updateQuantity,
      removeFromCart,
      clearCart,
      handleCheckout,
      checkoutComplete,
      resetCheckout,
      incrementSearch,
      incrementProductView,
    }}>
      {children}
    </CartContext.Provider>
  )
}
