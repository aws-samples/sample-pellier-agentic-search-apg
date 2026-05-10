import React from 'react';
import { Mic } from 'lucide-react';
import { colors } from '../tokens';

export interface InputProps {
  variant?: 'search' | 'text';
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  disabled?: boolean;
  className?: string;
  onKeyDown?: React.KeyboardEventHandler<HTMLInputElement>;
}

/**
 * Input primitive — search bar and text input variants.
 *
 * Search variant: larger padding, mic icon, ⌘K hint badge.
 * Text variant: standard input styling.
 * Both: cream-50 bg, rounded-xl, sand border, espresso focus ring.
 */
export const Input: React.FC<InputProps> = ({
  variant = 'text',
  value,
  onChange,
  placeholder,
  disabled = false,
  className = '',
  onKeyDown,
}) => {
  const isSearch = variant === 'search';

  const baseClasses = [
    'w-full bg-cream-50 border border-sand rounded-xl font-sans text-espresso',
    'placeholder:text-ink-quiet',
    'focus:border-espresso focus:ring-2 focus:ring-espresso focus:outline-none',
    'transition-colors duration-fade ease-out',
    disabled ? 'opacity-50 cursor-not-allowed' : '',
  ].join(' ');

  const paddingClasses = isSearch ? 'pl-4 pr-20 py-3.5 text-base' : 'px-4 py-2.5 text-sm';

  return (
    <div className={['relative', className].filter(Boolean).join(' ')}>
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={onKeyDown}
        placeholder={placeholder}
        disabled={disabled}
        aria-label={placeholder}
        className={[baseClasses, paddingClasses].join(' ')}
      />
      {isSearch && (
        <div className="absolute right-3 top-1/2 -translate-y-1/2 flex items-center gap-2">
          <button
            type="button"
            aria-label="Voice search"
            className="text-ink-quiet hover:text-espresso transition-colors duration-fade ease-out p-1"
          >
            <Mic size={18} />
          </button>
          <kbd className="hidden sm:inline-flex items-center gap-0.5 rounded-md bg-sand/50 px-1.5 py-0.5 text-xs font-mono text-ink-quiet">
            ⌘K
          </kbd>
        </div>
      )}
    </div>
  );
};

void colors;

export default Input;
