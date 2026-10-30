import { NAV_ITEMS } from '../nav'
import type { PageId } from '../nav'
import { StatusBar } from './StatusBar'
import type { SystemStatus } from '../types'

export function TopBar({ page, status }: { page: PageId; status: SystemStatus | null }) {
  const label = NAV_ITEMS.find((item) => item.id === page)?.label ?? 'CASCADE'
  return (
    <header className="topbar">
      <h1 className="topbar-title">{label}</h1>
      <StatusBar status={status} />
    </header>
  )
}
