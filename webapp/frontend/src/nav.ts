export type PageId =
  | 'dashboard'
  | 'live'
  | 'attack-sim'
  | 'flashcrowd-sim'
  | 'experiments'
  | 'architecture'
  | 'dataset'

export const NAV_ITEMS: { id: PageId; label: string }[] = [
  { id: 'dashboard', label: 'Dashboard' },
  { id: 'live', label: 'Live Monitor' },
  { id: 'attack-sim', label: 'Attack Simulator' },
  { id: 'flashcrowd-sim', label: 'Flash Crowd Simulator' },
  { id: 'experiments', label: 'Experiments' },
  { id: 'architecture', label: 'Architecture' },
  { id: 'dataset', label: 'Dataset / Export' },
]

export const DEFAULT_PAGE: PageId = 'dashboard'

export function isPageId(value: string): value is PageId {
  return NAV_ITEMS.some((item) => item.id === value)
}
