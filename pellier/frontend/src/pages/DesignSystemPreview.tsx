/**
 * DesignSystemPreview — dev-only visual QA page for the design system.
 *
 * Route: `/dev/design-system` (mounted in App.tsx only when
 * `import.meta.env.DEV` is true). Production bundle never sees it.
 *
 * Renders every primitive in all variants and states, the full color
 * palette, typography samples, spacing scale, and shadow tokens.
 */
import { useState } from 'react'
import { Heart, Search, Settings, Home, Users, BarChart3, Wrench, Shield, Layers } from 'lucide-react'
import {
  Button,
  Chip,
  Card,
  Input,
  Modal,
  Drawer,
  Avatar,
  Pill,
  IconButton,
  Sidebar,
  Timeline,
} from '../design/primitives'
import type { SidebarItem, TimelineStep } from '../design/primitives'
import { colors, spacing, shadows, radii, animation, breakpoints, fluid } from '../design/tokens'
import '../design/typography.css'

// ---------------------------------------------------------------------------
// Section wrapper
// ---------------------------------------------------------------------------
function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mb-16">
      <h2 className="text-headline mb-6" style={{ color: colors.espresso }}>{title}</h2>
      {children}
    </section>
  )
}

function SubSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="mb-8">
      <h3 className="text-body font-medium mb-4" style={{ color: colors.espresso }}>{title}</h3>
      {children}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Color Palette
// ---------------------------------------------------------------------------
function ColorPalette() {
  const colorEntries = Object.entries(colors) as [string, string][]
  return (
    <Section title="Color Palette">
      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-4">
        {colorEntries.map(([name, hex]) => (
          <div key={name} className="flex flex-col items-center gap-2">
            <div
              className="w-20 h-20 rounded-lg shadow-warm-sm border border-sand"
              style={{ backgroundColor: hex }}
            />
            <span className="text-mono" style={{ color: colors.espresso }}>{name}</span>
            <span className="text-mono" style={{ color: colors.inkQuiet }}>{hex}</span>
          </div>
        ))}
      </div>
    </Section>
  )
}

// ---------------------------------------------------------------------------
// Typography Samples
// ---------------------------------------------------------------------------
function TypographySamples() {
  const samples = [
    { className: 'text-display', label: '.text-display', sample: 'The quick brown fox jumps over the lazy dog' },
    { className: 'text-headline', label: '.text-headline', sample: 'The quick brown fox jumps over the lazy dog' },
    { className: 'text-body', label: '.text-body', sample: 'The quick brown fox jumps over the lazy dog. Pack my box with five dozen liquor jugs.' },
    { className: 'text-body-sm', label: '.text-body-sm', sample: 'The quick brown fox jumps over the lazy dog. Pack my box with five dozen liquor jugs.' },
    { className: 'text-mono', label: '.text-mono', sample: 'SELECT * FROM products WHERE embedding <=> $1 ORDER BY distance LIMIT 10;' },
    { className: 'text-eyebrow', label: '.text-eyebrow', sample: 'Curated for you' },
    { className: 'text-microcopy', label: '.text-microcopy', sample: 'Preferences stored with AgentCore Memory' },
  ]

  return (
    <Section title="Typography">
      <div className="space-y-6">
        {samples.map(({ className, label, sample }) => (
          <div key={label} className="border-b border-sand pb-4">
            <span className="text-mono mb-2 block" style={{ color: colors.inkQuiet }}>{label}</span>
            <p className={className} style={{ color: colors.espresso }}>{sample}</p>
          </div>
        ))}
      </div>
    </Section>
  )
}

// ---------------------------------------------------------------------------
// Spacing Scale
// ---------------------------------------------------------------------------
function SpacingScale() {
  const spacingEntries = Object.entries(spacing) as [string, string][]
  return (
    <Section title="Spacing Scale">
      <div className="space-y-3">
        {spacingEntries.map(([name, value]) => (
          <div key={name} className="flex items-center gap-4">
            <span className="text-mono w-12 text-right" style={{ color: colors.inkQuiet }}>{name}</span>
            <div
              className="h-6 rounded"
              style={{ width: value, backgroundColor: colors.terracotta, opacity: 0.7 }}
            />
            <span className="text-mono" style={{ color: colors.espresso }}>{value}</span>
          </div>
        ))}
      </div>
    </Section>
  )
}

// ---------------------------------------------------------------------------
// Shadow Tokens
// ---------------------------------------------------------------------------
function ShadowTokens() {
  const shadowEntries = Object.entries(shadows) as [string, string][]
  return (
    <Section title="Shadow Tokens">
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
        {shadowEntries.map(([name, value]) => (
          <div
            key={name}
            className="p-6 rounded-xl flex flex-col items-center justify-center gap-2"
            style={{ backgroundColor: colors.cream, boxShadow: value }}
          >
            <span className="text-body font-medium" style={{ color: colors.espresso }}>shadow-{name}</span>
            <span className="text-mono text-center" style={{ color: colors.inkQuiet }}>{name}</span>
          </div>
        ))}
      </div>
    </Section>
  )
}

// ---------------------------------------------------------------------------
// Primitives Preview
// ---------------------------------------------------------------------------
function ButtonPreview() {
  const variants = ['primary', 'secondary', 'ghost'] as const
  const sizes = ['sm', 'md', 'lg'] as const

  return (
    <SubSection title="Button">
      <div className="space-y-4">
        {variants.map((variant) => (
          <div key={variant} className="flex flex-wrap items-center gap-3">
            <span className="text-mono w-24" style={{ color: colors.inkQuiet }}>{variant}</span>
            {sizes.map((size) => (
              <Button key={`${variant}-${size}`} variant={variant} size={size}>
                {size.toUpperCase()}
              </Button>
            ))}
            <Button variant={variant} size="md" disabled>
              Disabled
            </Button>
          </div>
        ))}
      </div>
    </SubSection>
  )
}

function ChipPreview() {
  return (
    <SubSection title="Chip">
      <div className="flex flex-wrap gap-3">
        <Chip active={false}>Inactive chip</Chip>
        <Chip active={true}>Active chip</Chip>
        <Chip active={false}>Summer walks</Chip>
        <Chip active={true}>Warm evenings</Chip>
      </div>
    </SubSection>
  )
}

function CardPreview() {
  const variants = ['default', 'product', 'recommendation', 'reasoning'] as const
  return (
    <SubSection title="Card">
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {variants.map((variant) => (
          <Card key={variant} variant={variant}>
            <div className="p-4">
              <p className="text-body font-medium" style={{ color: colors.espresso }}>{variant}</p>
              <p className="text-body-sm mt-1" style={{ color: colors.inkSoft }}>
                Card variant preview with sample content.
              </p>
            </div>
          </Card>
        ))}
      </div>
    </SubSection>
  )
}

function InputPreview() {
  const [searchVal, setSearchVal] = useState('')
  const [textVal, setTextVal] = useState('')

  return (
    <SubSection title="Input">
      <div className="space-y-4 max-w-md">
        <div>
          <span className="text-mono block mb-2" style={{ color: colors.inkQuiet }}>search</span>
          <Input variant="search" placeholder="Ask Pellier anything..." value={searchVal} onChange={setSearchVal} />
        </div>
        <div>
          <span className="text-mono block mb-2" style={{ color: colors.inkQuiet }}>text</span>
          <Input variant="text" placeholder="Enter your name" value={textVal} onChange={setTextVal} />
        </div>
      </div>
    </SubSection>
  )
}

function AvatarPreview() {
  const sizes = ['sm', 'md', 'lg'] as const
  const samples = [
    { initial: 'M', bgColor: colors.espresso },
    { initial: 'A', bgColor: colors.terracotta },
    { initial: 'B', bgColor: colors.olive },
  ]

  return (
    <SubSection title="Avatar">
      <div className="space-y-4">
        {sizes.map((size) => (
          <div key={size} className="flex items-center gap-4">
            <span className="text-mono w-8" style={{ color: colors.inkQuiet }}>{size}</span>
            {samples.map(({ initial, bgColor }) => (
              <Avatar key={`${size}-${initial}`} initial={initial} bgColor={bgColor} size={size} />
            ))}
          </div>
        ))}
      </div>
    </SubSection>
  )
}

function PillPreview() {
  return (
    <SubSection title="Pill">
      <div className="flex flex-wrap gap-3">
        <Pill variant="live">Live</Pill>
        <Pill variant="confidence">High confidence</Pill>
        <Pill variant="default">Default</Pill>
      </div>
    </SubSection>
  )
}

function IconButtonPreview() {
  return (
    <SubSection title="IconButton">
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-2">
          <span className="text-mono" style={{ color: colors.inkQuiet }}>sm</span>
          <IconButton icon={<Heart size={16} />} ariaLabel="Favorite" size="sm" />
          <IconButton icon={<Search size={16} />} ariaLabel="Search" size="sm" />
          <IconButton icon={<Settings size={16} />} ariaLabel="Settings" size="sm" />
        </div>
        <div className="flex items-center gap-2">
          <span className="text-mono" style={{ color: colors.inkQuiet }}>md</span>
          <IconButton icon={<Heart size={20} />} ariaLabel="Favorite" size="md" />
          <IconButton icon={<Search size={20} />} ariaLabel="Search" size="md" />
          <IconButton icon={<Settings size={20} />} ariaLabel="Settings" size="md" />
        </div>
      </div>
    </SubSection>
  )
}

function SidebarPreview() {
  const [darkActive, setDarkActive] = useState('sessions')
  const [lightActive, setLightActive] = useState('home')

  const sampleItems: SidebarItem[] = [
    { id: 'home', label: 'Home', icon: <Home size={18} /> },
    { id: 'sessions', label: 'Sessions', icon: <Layers size={18} />, badge: '3' },
    { id: 'agents', label: 'Agents', icon: <Users size={18} /> },
    { id: 'tools', label: 'Tools', icon: <Wrench size={18} /> },
    { id: 'analytics', label: 'Analytics', icon: <BarChart3 size={18} /> },
    { id: 'security', label: 'Security', icon: <Shield size={18} /> },
  ]

  return (
    <SubSection title="Sidebar">
      <div className="flex gap-6 overflow-x-auto">
        <div className="h-[360px] rounded-lg overflow-hidden shrink-0">
          <Sidebar
            variant="dark"
            items={sampleItems}
            activeItem={darkActive}
            onItemClick={setDarkActive}
            header={<span className="text-eyebrow" style={{ color: colors.inkQuiet }}>Dark variant</span>}
          />
        </div>
        <div className="h-[360px] rounded-lg overflow-hidden border border-sand shrink-0">
          <Sidebar
            variant="light"
            items={sampleItems}
            activeItem={lightActive}
            onItemClick={setLightActive}
            header={<span className="text-eyebrow" style={{ color: colors.inkSoft }}>Light variant</span>}
          />
        </div>
      </div>
    </SubSection>
  )
}

function TimelinePreview() {
  const steps: TimelineStep[] = [
    { number: 1, label: 'Understanding intent', status: 'complete' },
    { number: 2, label: 'Retrieving memory', status: 'in-progress' },
    { number: 3, label: 'Scanning inventory', status: 'pending' },
    { number: 4, label: 'Skipped step', status: 'skipped' },
  ]

  return (
    <SubSection title="Timeline">
      <div className="max-w-sm">
        <Timeline steps={steps} />
      </div>
    </SubSection>
  )
}

function ModalPreview() {
  const [open, setOpen] = useState(false)
  return (
    <SubSection title="Modal">
      <Button variant="secondary" onClick={() => setOpen(true)}>
        Open Modal
      </Button>
      <Modal open={open} onClose={() => setOpen(false)} ariaLabel="Demo modal">
        <div className="p-6">
          <h3 className="text-headline mb-3" style={{ color: colors.espresso }}>Demo Modal</h3>
          <p className="text-body mb-4" style={{ color: colors.inkSoft }}>
            This modal traps focus, closes on Escape, and renders via portal.
          </p>
          <Button variant="primary" onClick={() => setOpen(false)}>
            Close
          </Button>
        </div>
      </Modal>
    </SubSection>
  )
}

function DrawerPreview() {
  const [open, setOpen] = useState(false)
  return (
    <SubSection title="Drawer">
      <Button variant="secondary" onClick={() => setOpen(true)}>
        Open Drawer (right)
      </Button>
      <Drawer open={open} onClose={() => setOpen(false)} side="right" ariaLabel="Demo drawer">
        <div className="p-6 w-80">
          <h3 className="text-headline mb-3" style={{ color: colors.espresso }}>Demo Drawer</h3>
          <p className="text-body mb-4" style={{ color: colors.inkSoft }}>
            This drawer slides in from the right at 240ms ease-out.
          </p>
          <Button variant="primary" onClick={() => setOpen(false)}>
            Close
          </Button>
        </div>
      </Drawer>
    </SubSection>
  )
}

// ---------------------------------------------------------------------------
// Additional token displays
// ---------------------------------------------------------------------------
function RadiiDisplay() {
  const radiiEntries = Object.entries(radii) as [string, string][]
  return (
    <Section title="Border Radii">
      <div className="flex flex-wrap gap-4">
        {radiiEntries.map(([name, value]) => (
          <div key={name} className="flex flex-col items-center gap-2">
            <div
              className="w-16 h-16 border-2 border-espresso"
              style={{ borderRadius: value, backgroundColor: colors.sand }}
            />
            <span className="text-mono" style={{ color: colors.espresso }}>{name}</span>
            <span className="text-mono" style={{ color: colors.inkQuiet }}>{value}</span>
          </div>
        ))}
      </div>
    </Section>
  )
}

function AnimationDisplay() {
  return (
    <Section title="Animation Timing">
      <div className="space-y-2">
        <div className="flex items-center gap-4">
          <span className="text-mono w-16" style={{ color: colors.inkQuiet }}>slide</span>
          <span className="text-body" style={{ color: colors.espresso }}>{animation.slide.duration} {animation.slide.easing}</span>
        </div>
        <div className="flex items-center gap-4">
          <span className="text-mono w-16" style={{ color: colors.inkQuiet }}>fade</span>
          <span className="text-body" style={{ color: colors.espresso }}>{animation.fade.duration} {animation.fade.easing}</span>
        </div>
        <div className="flex items-center gap-4">
          <span className="text-mono w-16" style={{ color: colors.inkQuiet }}>spring</span>
          <span className="text-body" style={{ color: colors.espresso }}>stiffness: {animation.spring.stiffness}, damping: {animation.spring.damping}</span>
        </div>
      </div>
    </Section>
  )
}

function BreakpointsDisplay() {
  const bpEntries = Object.entries(breakpoints) as [string, string][]
  return (
    <Section title="Responsive Breakpoints">
      <div className="space-y-2">
        {bpEntries.map(([name, value]) => (
          <div key={name} className="flex items-center gap-4">
            <span className="text-mono w-36" style={{ color: colors.inkQuiet }}>{name}</span>
            <span className="text-body" style={{ color: colors.espresso }}>{value}</span>
          </div>
        ))}
      </div>
      <p className="text-body-sm mt-4" style={{ color: colors.inkSoft }}>
        Two breakpoints define three bands: mobile ({'<'} 768px), desktop (768px - 1440px), wide ({'>'} 1440px).
        Content is fluid within each band.
      </p>
    </Section>
  )
}

function FluidTokensDisplay() {
  const fluidEntries = Object.entries(fluid) as [string, string][]
  return (
    <Section title="Fluid Layout Tokens">
      <div className="space-y-2">
        {fluidEntries.map(([name, value]) => (
          <div key={name} className="flex items-baseline gap-4">
            <span className="text-mono w-40 shrink-0" style={{ color: colors.inkQuiet }}>{name}</span>
            <span className="text-mono" style={{ color: colors.espresso }}>{value}</span>
          </div>
        ))}
      </div>
    </Section>
  )
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------
export default function DesignSystemPreview() {
  return (
    <div className="min-h-screen" style={{ backgroundColor: colors.cream }}>
      <div className="max-w-6xl mx-auto px-container-x py-12">
        <header className="mb-12">
          <h1 className="text-display" style={{ color: colors.espresso }}>
            Pellier Design System
          </h1>
          <p className="text-body mt-3" style={{ color: colors.inkSoft }}>
            Visual QA preview of all tokens and primitives. Dev-only route.
          </p>
        </header>

        <ColorPalette />
        <TypographySamples />
        <SpacingScale />
        <ShadowTokens />
        <RadiiDisplay />
        <AnimationDisplay />
        <BreakpointsDisplay />
        <FluidTokensDisplay />

        <Section title="Primitives">
          <ButtonPreview />
          <ChipPreview />
          <CardPreview />
          <InputPreview />
          <AvatarPreview />
          <PillPreview />
          <IconButtonPreview />
          <SidebarPreview />
          <TimelinePreview />
          <ModalPreview />
          <DrawerPreview />
        </Section>
      </div>
    </div>
  )
}
