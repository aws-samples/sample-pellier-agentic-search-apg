/**
 * Barrel export — the two primitives the storefront header actually mounts.
 *
 * Nine more once lived here (Button, Card, Chip, Input, Modal, Drawer, Pill,
 * Sidebar, Timeline). Every one was exported, none was imported: the surfaces
 * had each grown its own control vocabulary in CSS, and the module described a
 * design system that no rendered pixel came from. A component tree nobody
 * mounts is not a system, it is a second answer to questions already settled
 * elsewhere, so it has been removed rather than deprecated. Shared visual
 * contracts live in `operator/styles/operator.css`, `styles/`, and `shared/`.
 */

export { Avatar, type AvatarProps } from './Avatar'
export { IconButton, type IconButtonProps } from './IconButton'
