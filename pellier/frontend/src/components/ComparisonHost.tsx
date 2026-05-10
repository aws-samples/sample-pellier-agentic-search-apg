/**
 * ComparisonHost — root-level mount for ProductComparison.
 *
 * Lives alongside the other modal hosts (AuthModal, PreferencesModal,
 * ConciergeModal) so the comparison surface survives route changes and is
 * decoupled from whichever chat surface triggered it. Reads payload and
 * active-modal state from UIContext.
 *
 * Closing ProductComparison delegates to `closeModal`, which knows to
 * restore the concierge singleton when closing from 'comparison'.
 */
import { useUI } from '../contexts/UIContext'
import ProductComparison from './ProductComparison'
import type { ChatProduct } from '../services/chat'

export default function ComparisonHost() {
  const { activeModal, comparisonProducts, closeModal } = useUI()
  if (activeModal !== 'comparison') return null
  if (!comparisonProducts || comparisonProducts.length === 0) return null
  return (
    <ProductComparison
      products={comparisonProducts as ChatProduct[]}
      onClose={closeModal}
    />
  )
}
