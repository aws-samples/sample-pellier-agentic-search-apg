/** Honest empty state for catalog entries that have no product photograph. */
export default function ProductPhotoUnavailable() {
  return (
    <span className="flex h-full min-h-24 w-full items-center justify-center px-6 text-center text-sm text-muted">
      Photo not available
    </span>
  )
}
