const SkeletonLoader = () => {
  return (
    <div className="space-y-4">
      <div className="h-4 skeleton-shimmer rounded w-3/4"></div>
      <div className="h-4 skeleton-shimmer rounded w-1/2"></div>
      <div className="h-4 skeleton-shimmer rounded w-5/6"></div>
    </div>
  )
}

export const ProductCardSkeleton = () => {
  return (
    <div className="rounded-xl p-4" style={{ background: 'var(--input-bg)', border: '1px solid var(--border-color)' }}>
      <div className="flex gap-4">
        <div className="w-20 h-20 skeleton-shimmer rounded-lg"></div>
        <div className="flex-1 space-y-3">
          <div className="h-4 skeleton-shimmer rounded w-3/4"></div>
          <div className="h-4 skeleton-shimmer rounded w-1/2"></div>
          <div className="h-6 skeleton-shimmer rounded w-1/4"></div>
        </div>
      </div>
    </div>
  )
}

export default SkeletonLoader
