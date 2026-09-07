import { NAV_ITEMS } from '../nav'
import type { PageId } from '../nav'

export function NavShell({ active, onSelect }: { active: PageId; onSelect: (id: PageId) => void }) {
  return (
    <nav className="nav-bar">
      {NAV_ITEMS.map((item) => (
        <button
          key={item.id}
          className={`tab-btn nav-btn ${active === item.id ? 'active' : ''}`}
          onClick={() => onSelect(item.id)}
        >
          {item.label}
        </button>
      ))}
    </nav>
  )
}
