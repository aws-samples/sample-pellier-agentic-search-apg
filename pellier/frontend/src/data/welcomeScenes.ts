/** Existing editorial photography. Catalog and account facts remain live reads. */
const scenes: Record<string, { image: string; alt: string; label: string }> = {
  fresh: {
    image: '/products/landing-hero-weekender.webp',
    alt: 'A leather weekender on an oak bench beside a linen throw, a wooden bowl and a stoneware vase of olive branches',
    label: 'The weekend edit',
  },
  marco: {
    image: '/products/hero-marco.png',
    alt: 'A cognac leather holdall and a folded linen shirt on a short oak bench against a plain white wall',
    label: 'The weekend edit',
  },
  anna: {
    image: '/products/hero-anna.png',
    alt: 'A white gift box tied with a blush-pink ribbon, a blank kraft tag and a vase with one eucalyptus stem on a small oak side table',
    label: 'The gifting edit',
  },
  theo: {
    image: '/products/hero-theo.png',
    alt: 'A charcoal stoneware bowl holding a beeswax taper beside folded linen on a small oak side table',
    label: 'The everyday ritual',
  },
  jessica: {
    image: '/products/house-ivory-cashmere-throw-1122.webp',
    alt: 'Folded ivory cashmere throw on a made bed in daylight',
    label: 'The home edit',
  },
}

export function welcomeScene(personaId: string) {
  return scenes[personaId] ?? scenes.fresh
}
