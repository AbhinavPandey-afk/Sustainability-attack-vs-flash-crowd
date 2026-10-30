export type PageId =
  | 'overview'
  | 'experiments'
  | 'compare'
  | 'detection'
  | 'analysis'
  | 'dataset'
  | 'architecture'
  | 'system'

export type NavGroup = 'research' | 'data' | 'system'

export const NAV_ITEMS: { id: PageId; label: string; group: NavGroup }[] = [
  { id: 'overview', label: 'Overview', group: 'research' },
  { id: 'experiments', label: 'Experiments', group: 'research' },
  { id: 'compare', label: 'Compare', group: 'research' },
  { id: 'detection', label: 'Detection', group: 'research' },
  { id: 'analysis', label: 'Analysis', group: 'research' },
  { id: 'dataset', label: 'Dataset', group: 'data' },
  { id: 'architecture', label: 'Architecture', group: 'system' },
  { id: 'system', label: 'System Monitor', group: 'system' },
]

export const NAV_GROUP_LABELS: Record<NavGroup, string> = {
  research: 'Research',
  data: 'Data',
  system: 'System',
}

export const DEFAULT_PAGE: PageId = 'overview'

// Old hash ids kept resolving to their replacement page — see
// currentPageFromHash() in App.tsx — so any old bookmark/link still works
// instead of 404ing.
const LEGACY_PAGE_REDIRECTS: Record<string, PageId> = {
  dashboard: 'overview',
  live: 'system',
  simulator: 'compare',
  'attack-sim': 'compare',
  'flashcrowd-sim': 'compare',
}

export function isPageId(value: string): value is PageId {
  return NAV_ITEMS.some((item) => item.id === value)
}

export function resolvePageId(value: string): PageId {
  if (isPageId(value)) return value
  return LEGACY_PAGE_REDIRECTS[value] ?? DEFAULT_PAGE
}
