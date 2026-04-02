// Mots-clés pour détecter le contenu français dans les noms de catégories
// Portés depuis le code Python original

export const FRENCH_KEYWORDS = [
  'fr |', '| fr', 'french', 'français', 'francais',
  'vf', 'vff', 'vf |', '| vf',
  'vostfr', 'vostfr |', '| vostfr',
  'franco', 'belgique', 'québec', 'quebec',
]

export function isFrench(categoryName) {
  if (!categoryName) return false
  const lower = categoryName.toLowerCase()
  return FRENCH_KEYWORDS.some(kw => lower.includes(kw))
}
