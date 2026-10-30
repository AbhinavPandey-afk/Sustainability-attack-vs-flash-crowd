import { NAV_GROUP_LABELS, NAV_ITEMS } from '../nav'
import type { NavGroup, PageId } from '../nav'

const GROUPS: NavGroup[] = ['research', 'data', 'system']

export function NavShell({ active, onSelect }: { active: PageId; onSelect: (id: PageId) => void }) {
  return (
    <nav className="sidebar" aria-label="Primary">
      <div className="sidebar-brand">
        <span className="sidebar-brand-mark">C</span>
        <div>
          <div className="sidebar-brand-name">CASCADE</div>
          <div className="sidebar-brand-sub">Research Console</div>
        </div>
      </div>

      {GROUPS.map((group) => {
        const items = NAV_ITEMS.filter((item) => item.group === group)
        if (items.length === 0) return null
        return (
          <div key={group} className="sidebar-group">
            <div className="sidebar-group-label">{NAV_GROUP_LABELS[group]}</div>
            <div className="sidebar-nav">
              {items.map((item) => (
                <button
                  key={item.id}
                  className={`sidebar-link ${active === item.id ? 'active' : ''}`}
                  aria-current={active === item.id ? 'page' : undefined}
                  onClick={() => onSelect(item.id)}
                >
                  {item.label}
                </button>
              ))}
            </div>
          </div>
        )
      })}
    </nav>
  )
}
