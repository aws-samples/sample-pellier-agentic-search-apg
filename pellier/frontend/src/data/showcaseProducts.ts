/**
 * 40 showcase products for the Pellier boutique — 10 per persona.
 *
 * Fresh (1-9), Marco (11-19), Anna (21-29), Theo (31-39).
 * Zero overlap between personas. Each persona's set includes a hero
 * product, a weekend-edit featured, and 8 grid cards.
 *
 * Tag sets match the seed_boutique_catalog.py data so the backend's
 * pgvector embeddings and the frontend's tag-weight scoring stay aligned.
 */
import type {
  ReasoningChip,
  BoutiqueProduct,
} from '../services/types'
import { REASONING } from '../copy'
import {
  assignReasoningChipsCyclic,
  findAdjacentDuplicateStyleIndex,
} from '../components/ReasoningChip'

// 40 reasoning chips — cycles picked→matched→pricing→context (10 full rotations)
const AUTHORED: ReasoningChip[] = [
  // Fresh 1-9
  { style: 'picked', text: REASONING.picked('sculptural ceramics that anchor a room') },
  { style: 'matched', text: REASONING.matched('linen', 'resort', 'minimal') },
  { style: 'pricing', text: REASONING.pricing(14, 3).lead, urgentClause: REASONING.pricing(14, 3).urgent },
  { style: 'context', text: 'the scent that turns a Tuesday into a ritual' },
  { style: 'picked', text: REASONING.picked('you mentioned timeless accessories') },
  { style: 'matched', text: REASONING.matched('apothecary', 'minimal', 'warm') },
  { style: 'pricing', text: REASONING.pricing(8, 5).lead, urgentClause: REASONING.pricing(8, 5).urgent },
  { style: 'context', text: 'the set that makes staying in feel intentional' },
  { style: 'picked', text: REASONING.picked('you liked clean activewear') },
  // Marco 11-19
  { style: 'matched', text: REASONING.matched('linen', 'travel', 'resort') },
  { style: 'pricing', text: REASONING.pricing(20, 7).lead, urgentClause: REASONING.pricing(20, 7).urgent },
  { style: 'context', text: 'the wallet that outlasts every trip' },
  { style: 'picked', text: REASONING.picked('natural fibers for the road') },
  { style: 'matched', text: REASONING.matched('footwear', 'resort', 'travel') },
  { style: 'pricing', text: REASONING.pricing(12, 4).lead, urgentClause: REASONING.pricing(12, 4).urgent },
  { style: 'context', text: 'the layer that earns its spot in the bag' },
  { style: 'picked', text: REASONING.picked('full-grain leather for decades') },
  { style: 'matched', text: REASONING.matched('linen', 'everyday', 'minimal') },
  // Anna 21-29
  { style: 'pricing', text: REASONING.pricing(18, 6).lead, urgentClause: REASONING.pricing(18, 6).urgent },
  { style: 'context', text: 'arrives gift-wrapped, no extra effort' },
  { style: 'picked', text: REASONING.picked('the ring dish everyone keeps') },
  { style: 'matched', text: REASONING.matched('accessories', 'gift', 'classic') },
  { style: 'pricing', text: REASONING.pricing(10, 8).lead, urgentClause: REASONING.pricing(10, 8).urgent },
  { style: 'context', text: 'three bars, three scents, one beautiful box' },
  { style: 'picked', text: REASONING.picked('a single stem says enough') },
  { style: 'matched', text: REASONING.matched('leather', 'gift', 'classic') },
  { style: 'pricing', text: REASONING.pricing(15, 4).lead, urgentClause: REASONING.pricing(15, 4).urgent },
  // Theo 31-39
  { style: 'context', text: 'the morning ritual, elevated' },
  { style: 'picked', text: REASONING.picked('gets softer with every wash') },
  { style: 'matched', text: REASONING.matched('home', 'artisanal', 'slow') },
  { style: 'pricing', text: REASONING.pricing(22, 9).lead, urgentClause: REASONING.pricing(22, 9).urgent },
  { style: 'context', text: 'thin smoke, warm brass, no rush' },
  { style: 'picked', text: REASONING.picked('no two exactly alike') },
  { style: 'matched', text: REASONING.matched('ceramic', 'slow', 'sculptural') },
  { style: 'pricing', text: REASONING.pricing(8, 3).lead, urgentClause: REASONING.pricing(8, 3).urgent },
  { style: 'context', text: 'the kind of piece that makes a Tuesday feel intentional' },
  { style: 'picked', text: REASONING.picked('hand-dipped, 80-hour burn') },
  { style: 'matched', text: REASONING.matched('linen', 'home', 'slow') },
]

const CHIPS: ReasoningChip[] = assignReasoningChipsCyclic(AUTHORED)

if (findAdjacentDuplicateStyleIndex(CHIPS) !== -1) {
  throw new Error(
    'showcaseProducts: adjacent cards share a reasoning chip style',
  )
}

export const SHOWCASE_PRODUCTS: BoutiqueProduct[] = [
  // ─── FRESH (1-9) ───
  { id: 1, brand: 'Pellier Home', name: 'Olive Branch Vessel', color: 'Ivory', price: 185, rating: 4.9, reviewCount: 127, category: 'Home Decor', imageUrl: '/products/fresh-olive-branch-vessel.png', tags: ['ceramic', 'sculptural', 'minimal', 'warm', 'neutral', 'home', 'housewarming', 'milestone'], reasoning: CHIPS[0] },
  { id: 2, brand: 'Pellier Editions', name: 'Pellier Linen Shirt', color: 'Ivory', price: 248, rating: 4.8, reviewCount: 312, category: 'Apparel', imageUrl: '/products/fresh-pellier-linen-shirt.png', badge: 'EDITORS_PICK', tags: ['linen', 'minimal', 'resort', 'warm', 'neutral', 'everyday'], reasoning: CHIPS[1] },
  { id: 3, brand: 'Pellier Travel', name: 'Nocturne Leather Weekender', color: 'Espresso', price: 425, rating: 4.9, reviewCount: 89, category: 'Accessories', imageUrl: '/products/fresh-nocturne-leather-weekender.png', tags: ['leather', 'travel', 'classic', 'warm', 'earth', 'accessories'], reasoning: CHIPS[2] },
  { id: 4, brand: 'Pellier Home', name: 'Santal & Fig Candle', color: 'Amber', price: 92, rating: 4.7, reviewCount: 445, category: 'Home Fragrance', imageUrl: '/products/fresh-santal-fig-candle.png', tags: ['candle', 'home', 'minimal', 'warm', 'slow'], reasoning: CHIPS[3] },
  { id: 5, brand: 'Pellier Editions', name: 'Heritage Rectangular Watch', color: 'Tan', price: 420, rating: 4.8, reviewCount: 203, category: 'Watches & Jewelry', imageUrl: '/products/fresh-heritage-rectangular-watch.png', badge: 'JUST_IN', tags: ['watch', 'classic', 'minimal', 'timeless', 'accessories'], reasoning: CHIPS[4] },
  { id: 6, brand: 'Pellier Home', name: 'Neroli Apothecary Bottle', color: 'Clear', price: 78, rating: 4.6, reviewCount: 178, category: 'Beauty', imageUrl: '/products/fresh-neroli-apothecary-bottle.png', tags: ['beauty', 'apothecary', 'minimal', 'home', 'warm'], reasoning: CHIPS[5] },
  { id: 7, brand: 'Pellier Home', name: 'Solstice Woven Mat Set', color: 'Natural', price: 145, rating: 4.5, reviewCount: 92, category: 'Home Decor', imageUrl: '/products/fresh-solstice-woven-mat-set.png', tags: ['wellness', 'home', 'neutral', 'artisanal', 'slow'], reasoning: CHIPS[6] },
  { id: 8, brand: 'Pellier Editions', name: 'Alba Linen Lounge Set', color: 'Oat', price: 298, rating: 4.7, reviewCount: 156, category: 'Apparel', imageUrl: '/products/fresh-alba-linen-lounge-set.png', tags: ['linen', 'loungewear', 'neutral', 'minimal', 'everyday', 'slow'], reasoning: CHIPS[7] },
  { id: 9, brand: 'Pellier Active', name: 'Cloudform Studio Runner', color: 'Stone', price: 165, rating: 4.6, reviewCount: 234, category: 'Footwear', imageUrl: '/products/fresh-cloudform-studio-runner.png', tags: ['activewear', 'neutral', 'minimal', 'wellness', 'footwear'], reasoning: CHIPS[8] },

  // ─── MARCO (11-19) ───
  { id: 11, brand: 'Pellier Editions', name: 'Italian Linen Camp Shirt', color: 'Indigo', price: 228, rating: 4.8, reviewCount: 287, category: 'Apparel', imageUrl: '/products/marco-linen-camp-shirt-indigo.png', badge: 'BESTSELLER', tags: ['linen', 'resort', 'travel', 'warm', 'minimal', 'everyday'], reasoning: CHIPS[9] },
  { id: 12, brand: 'Pellier Travel', name: 'Canvas Dopp Kit', color: 'Olive', price: 85, rating: 4.7, reviewCount: 198, category: 'Accessories', imageUrl: '/products/marco-canvas-dopp-kit.png', tags: ['canvas', 'travel', 'classic', 'accessories', 'minimal'], reasoning: CHIPS[10] },
  { id: 13, brand: 'Pellier Editions', name: 'Leather Card Wallet', color: 'Cognac', price: 95, rating: 4.9, reviewCount: 342, category: 'Accessories', imageUrl: '/products/marco-leather-card-wallet.png', tags: ['leather', 'classic', 'minimal', 'timeless', 'accessories', 'everyday'], reasoning: CHIPS[11] },
  { id: 14, brand: 'Pellier Editions', name: 'Linen Drawstring Trousers', color: 'Oat', price: 178, rating: 4.7, reviewCount: 225, category: 'Apparel', imageUrl: '/products/marco-linen-drawstring-trousers.png', tags: ['linen', 'travel', 'resort', 'neutral', 'minimal', 'everyday'], reasoning: CHIPS[12] },
  { id: 15, brand: 'Pellier Editions', name: 'Espadrille Slides', color: 'Natural', price: 118, rating: 4.6, reviewCount: 167, category: 'Footwear', imageUrl: '/products/marco-espadrille-slides.png', tags: ['footwear', 'resort', 'travel', 'warm', 'neutral'], reasoning: CHIPS[13] },
  { id: 16, brand: 'Pellier Editions', name: 'Linen Overshirt', color: 'Sage', price: 195, rating: 4.7, reviewCount: 143, category: 'Apparel', imageUrl: '/products/marco-linen-overshirt-sage.png', badge: 'EDITORS_PICK', tags: ['linen', 'travel', 'minimal', 'neutral', 'everyday', 'warm'], reasoning: CHIPS[14] },
  { id: 17, brand: 'Pellier Travel', name: 'Leather Weekend Holdall', color: 'Tan', price: 485, rating: 4.9, reviewCount: 76, category: 'Accessories', imageUrl: '/products/marco-leather-weekend-holdall.png', tags: ['leather', 'travel', 'classic', 'warm', 'earth', 'accessories'], reasoning: CHIPS[15] },
  { id: 18, brand: 'Pellier Editions', name: 'Cotton-Linen Crew Tee', color: 'Cream', price: 68, rating: 4.5, reviewCount: 412, category: 'Apparel', imageUrl: '/products/marco-cotton-linen-tee.png', tags: ['linen', 'everyday', 'minimal', 'neutral', 'warm'], reasoning: CHIPS[16] },
  { id: 19, brand: 'Pellier Editions', name: 'Straw Panama Hat', color: 'Cream', price: 145, rating: 4.8, reviewCount: 98, category: 'Accessories', imageUrl: '/products/marco-straw-panama-hat.png', badge: 'JUST_IN', tags: ['accessories', 'travel', 'resort', 'classic', 'warm'], reasoning: CHIPS[17] },

  // ─── ANNA (21-29) ───
  { id: 21, brand: 'Pellier Home', name: 'Beeswax Taper Candles', color: 'Ivory', price: 48, rating: 4.8, reviewCount: 289, category: 'Home Decor', imageUrl: '/products/anna-beeswax-taper-candles.png', badge: 'BESTSELLER', tags: ['candle', 'home', 'gift', 'slow', 'artisanal'], reasoning: CHIPS[18] },
  { id: 22, brand: 'Pellier Home', name: 'Monogrammed Linen Napkins', color: 'White', price: 72, rating: 4.7, reviewCount: 178, category: 'Home Decor', imageUrl: '/products/anna-monogrammed-napkins.png', tags: ['linen', 'home', 'gift', 'minimal', 'artisanal'], reasoning: CHIPS[19] },
  { id: 23, brand: 'Pellier Home', name: 'Ceramic Ring Dish', color: 'Speckled Cream', price: 35, rating: 4.9, reviewCount: 412, category: 'Home Decor', imageUrl: '/products/anna-ceramic-ring-dish.png', tags: ['ceramic', 'home', 'gift', 'artisanal', 'minimal'], reasoning: CHIPS[20] },
  { id: 24, brand: 'Pellier Editions', name: 'Botanical Print Scarf', color: 'Sage', price: 128, rating: 4.6, reviewCount: 145, category: 'Accessories', imageUrl: '/products/anna-botanical-scarf.png', badge: 'EDITORS_PICK', tags: ['accessories', 'gift', 'classic', 'warm', 'earth'], reasoning: CHIPS[21] },
  { id: 25, brand: 'Pellier Home', name: 'Reed Diffuser', color: 'Black Glass', price: 62, rating: 4.7, reviewCount: 367, category: 'Home Fragrance', imageUrl: '/products/anna-reed-diffuser.png', tags: ['home', 'gift', 'minimal', 'warm', 'slow'], reasoning: CHIPS[22] },
  { id: 26, brand: 'Pellier Apothecary', name: 'Handmade Soap Set', color: 'Multi', price: 45, rating: 4.8, reviewCount: 298, category: 'Beauty', imageUrl: '/products/anna-handmade-soap-set.png', tags: ['beauty', 'gift', 'artisanal', 'home', 'slow'], reasoning: CHIPS[23] },
  { id: 27, brand: 'Pellier Home', name: 'Ceramic Bud Vase', color: 'Dusty Rose', price: 42, rating: 4.6, reviewCount: 223, category: 'Home Decor', imageUrl: '/products/anna-ceramic-bud-vase.png', tags: ['ceramic', 'home', 'gift', 'sculptural', 'minimal'], reasoning: CHIPS[24] },
  { id: 28, brand: 'Pellier Editions', name: 'Leather Journal', color: 'Chestnut', price: 58, rating: 4.9, reviewCount: 187, category: 'Accessories', imageUrl: '/products/anna-leather-journal.png', badge: 'JUST_IN', tags: ['leather', 'gift', 'classic', 'timeless', 'accessories'], reasoning: CHIPS[25] },
  { id: 29, brand: 'Pellier Home', name: 'Brass Photo Frame', color: 'Gold', price: 55, rating: 4.7, reviewCount: 156, category: 'Home Decor', imageUrl: '/products/anna-brass-photo-frame.png', tags: ['home', 'gift', 'classic', 'warm', 'accessories'], reasoning: CHIPS[26] },

  // ─── THEO (31-39) ───
  { id: 31, brand: 'Pellier Home', name: 'Stoneware Pour-Over Set', color: 'Ash Grey', price: 165, rating: 4.9, reviewCount: 134, category: 'Home Decor', imageUrl: '/products/theo-stoneware-pour-over.png', badge: 'EDITORS_PICK', tags: ['ceramic', 'home', 'slow', 'artisanal', 'minimal'], reasoning: CHIPS[27] },
  { id: 32, brand: 'Pellier Home', name: 'Raw Linen Throw', color: 'Flax', price: 195, rating: 4.8, reviewCount: 201, category: 'Home Decor', imageUrl: '/products/theo-raw-linen-throw.png', tags: ['linen', 'home', 'slow', 'neutral', 'minimal'], reasoning: CHIPS[28] },
  { id: 33, brand: 'Pellier Home', name: 'Olive Wood Cutting Board', color: 'Natural', price: 88, rating: 4.7, reviewCount: 312, category: 'Home Decor', imageUrl: '/products/theo-olive-wood-board.png', badge: 'BESTSELLER', tags: ['home', 'artisanal', 'slow', 'warm', 'earth'], reasoning: CHIPS[29] },
  { id: 34, brand: 'Pellier Home', name: 'Terracotta Planter', color: 'Earth', price: 52, rating: 4.6, reviewCount: 256, category: 'Home Decor', imageUrl: '/products/theo-terracotta-planter.png', tags: ['ceramic', 'home', 'slow', 'earth', 'artisanal'], reasoning: CHIPS[30] },
  { id: 35, brand: 'Pellier Home', name: 'Brass Incense Holder', color: 'Brass', price: 45, rating: 4.8, reviewCount: 189, category: 'Home Decor', imageUrl: '/products/theo-brass-incense-holder.png', tags: ['home', 'slow', 'minimal', 'artisanal', 'warm'], reasoning: CHIPS[31] },
  { id: 36, brand: 'Pellier Home', name: 'Ceramic Tumblers', color: 'Charcoal', price: 78, rating: 4.7, reviewCount: 245, category: 'Home Decor', imageUrl: '/products/theo-ceramic-tumblers.png', tags: ['ceramic', 'home', 'slow', 'artisanal', 'minimal'], reasoning: CHIPS[32] },
  { id: 37, brand: 'Pellier Home', name: 'Wabi-Sabi Bowl', color: 'Cream', price: 65, rating: 4.9, reviewCount: 167, category: 'Home Decor', imageUrl: '/products/theo-wabi-sabi-bowl.png', tags: ['ceramic', 'home', 'slow', 'artisanal', 'minimal', 'sculptural'], reasoning: CHIPS[33] },
  { id: 38, brand: 'Pellier Home', name: 'Beeswax Pillar Candle', color: 'Natural', price: 38, rating: 4.6, reviewCount: 334, category: 'Home Decor', imageUrl: '/products/theo-beeswax-pillar-candle.png', tags: ['candle', 'home', 'slow', 'artisanal', 'warm'], reasoning: CHIPS[34] },
  { id: 39, brand: 'Pellier Home', name: 'Linen Table Runner', color: 'Flax', price: 85, rating: 4.7, reviewCount: 178, category: 'Home Decor', imageUrl: '/products/theo-linen-table-runner.png', badge: 'JUST_IN', tags: ['linen', 'home', 'slow', 'neutral', 'artisanal'], reasoning: CHIPS[35] },
]

// NOTE: imageUrl values are stored RAW ("/products/x.png"). Base-path
// resolution for the CloudFront /ports/8000/* proxy happens once, at the
// render site, via imageSrc() (utils/assetPath) - the same single-authority
// pattern ProductArtifactCard uses. Do NOT asset()/imageSrc() here too: a
// prior eager `forEach(p => p.imageUrl = asset(p.imageUrl))` here combined
// with the render-time imageSrc() to DOUBLE-prefix ("/ports/8000/ports/8000/
// products/x.png"), which 404'd behind the proxy while passing in local dev
// (where BASE_URL="/" makes double-prefix a no-op).

// Per-persona subsets — zero overlap between personas
export const FRESH_PRODUCTS = SHOWCASE_PRODUCTS.filter(p => p.id >= 1 && p.id <= 9)
export const MARCO_PRODUCTS = SHOWCASE_PRODUCTS.filter(p => p.id >= 11 && p.id <= 19)
export const ANNA_PRODUCTS = SHOWCASE_PRODUCTS.filter(p => p.id >= 21 && p.id <= 29)
export const THEO_PRODUCTS = SHOWCASE_PRODUCTS.filter(p => p.id >= 31 && p.id <= 39)
