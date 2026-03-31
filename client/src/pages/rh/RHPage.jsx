// src/pages/rh/RHPage.jsx
import { useState } from 'react'
import { Users, Building2, CalendarOff } from 'lucide-react'
import clsx from 'clsx'
import UsersTab  from './tabs/UsersTab'
import OrgTab    from './tabs/OrgTab'
import LeavesTab from './tabs/LeavesTab'

const TABS = [
  { id: 'leaves', label: 'Congés',        icon: CalendarOff },
  { id: 'users',  label: 'Utilisateurs',  icon: Users       },
  { id: 'org',    label: 'Organisation',  icon: Building2   },
]

export default function RHPage() {
  const [active, setActive] = useState('leaves')

  return (
    <div className="flex flex-col h-full">
      {/* Tab bar */}
      <div className="flex items-center gap-1 px-6 pt-4 border-b border-slate-100 bg-white shrink-0">
        {TABS.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            onClick={() => setActive(id)}
            className={clsx(
              'flex items-center gap-2 px-4 py-2.5 text-sm font-medium rounded-t-xl transition-colors -mb-px border-b-2',
              active === id
                ? 'text-navy border-cyan bg-cyan/5'
                : 'text-slate-400 border-transparent hover:text-slate-600 hover:bg-slate-50',
            )}
          >
            <Icon size={15} />
            {label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div className="flex-1 overflow-auto bg-slate-50/50">
        {active === 'leaves' && <LeavesTab />}
        {active === 'users'  && <UsersTab  />}
        {active === 'org'    && <OrgTab    />}
      </div>
    </div>
  )
}
