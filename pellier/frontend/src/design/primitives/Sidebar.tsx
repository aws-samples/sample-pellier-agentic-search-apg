import React from 'react';
import { colors } from '../tokens';

export interface SidebarItem {
  id: string;
  label: string;
  icon?: React.ReactNode;
  badge?: string;
}

export interface SidebarProps {
  variant: 'dark' | 'light';
  items: SidebarItem[];
  activeItem?: string;
  onItemClick: (id: string) => void;
  header?: React.ReactNode;
  footer?: React.ReactNode;
}

/**
 * Sidebar primitive — dark (espresso) and light variants.
 *
 * Dark: bg espresso-dark (#1F1410), text cream-50, active item cream/10 highlight.
 * Light: bg cream-50, text espresso, active item espresso/10 highlight.
 * Fixed width: w-[260px]. Semantic: aside > nav, role="navigation".
 */
export const Sidebar: React.FC<SidebarProps> = ({
  variant,
  items,
  activeItem,
  onItemClick,
  header,
  footer,
}) => {
  const isDark = variant === 'dark';

  const containerClasses = isDark
    ? 'bg-espresso-dark text-cream-50'
    : 'bg-cream-50 text-espresso';

  const activeClasses = isDark
    ? 'bg-cream-50/10'
    : 'bg-espresso/10';

  const hoverClasses = isDark
    ? 'hover:bg-cream-50/5'
    : 'hover:bg-espresso/5';

  return (
    <aside
      className={[
        'w-[260px] h-full flex flex-col shrink-0',
        containerClasses,
      ].join(' ')}
    >
      {header && <div className="px-4 py-4">{header}</div>}

      <nav role="navigation" className="flex-1 px-3 py-2 overflow-y-auto">
        <ul className="space-y-0.5">
          {items.map((item) => {
            const isActive = activeItem === item.id;
            return (
              <li key={item.id}>
                <button
                  type="button"
                  onClick={() => onItemClick(item.id)}
                  className={[
                    'w-full flex items-center gap-3 py-2.5 px-4 rounded-lg text-sm font-sans',
                    'transition-colors duration-fade ease-out cursor-pointer',
                    'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset',
                    isDark ? 'focus-visible:ring-cream-50' : 'focus-visible:ring-espresso',
                    isActive ? activeClasses : hoverClasses,
                  ].join(' ')}
                  aria-current={isActive ? 'page' : undefined}
                >
                  {item.icon && (
                    <span className="shrink-0 w-5 h-5 flex items-center justify-center">
                      {item.icon}
                    </span>
                  )}
                  <span className="flex-1 text-left truncate">{item.label}</span>
                  {item.badge && (
                    <span
                      className={[
                        'inline-flex items-center justify-center rounded-full px-2 py-0.5 text-xs font-medium',
                        isDark
                          ? 'bg-cream-50/15 text-cream-50'
                          : 'bg-espresso/10 text-espresso',
                      ].join(' ')}
                    >
                      {item.badge}
                    </span>
                  )}
                </button>
              </li>
            );
          })}
        </ul>
      </nav>

      {footer && <div className="px-4 py-4 mt-auto">{footer}</div>}
    </aside>
  );
};

void colors;

export default Sidebar;
