import React from 'react'
import { createRoot } from 'react-dom/client'
import './styles.css'

const navItems = ['Alert Queue', 'Investigations', 'Transactions', 'Settings']

function DashboardPage() {
  return (
    <main className="flex min-h-screen bg-[#F5F6F4] text-[#263331]">
      <aside className="flex w-[200px] min-h-screen flex-col border-r border-[#d8dddc] bg-[#FFFFFF]">
        <header className="px-[14px] pb-[10px] pt-[12px]">
          <p className="font-display text-[24px] font-semibold leading-none tracking-[-0.04em] text-[#1f2a29]">Underlock</p>
        </header>

        <nav className="pt-[8px]" aria-label="Primary navigation">
          {navItems.map((item, index) => (
            <button
              key={item}
              type="button"
              className={`flex w-full items-center text-left text-[12px] text-[#4a504e] no-underline ${index === 2 ? 'mx-[8px] rounded-[4px] bg-[#ececeb] px-[10px] py-[8px] font-medium text-[#1f2a29]' : 'px-[16px] py-[8px] hover:bg-[#f1f3f2]'}`}
              style={{ fontFamily: 'Inter, sans-serif' }}
            >
              {item}
            </button>
          ))}
        </nav>

        <div className="mt-auto bg-[#fafbfa] px-[12px] py-[10px]">
          <div className="pb-[8px]">
            <div className="flex items-center gap-[8px] font-mono text-[11px] text-[#66716e]">
              <div className="flex h-[24px] w-[24px] items-center justify-center rounded-full bg-[#dfe3e2] text-[9px] font-medium text-[#4d5a57]">
                A
              </div>
              <span>Analyst: AN-8902</span>
            </div>
          </div>

          <div className="h-px w-full bg-[#e2e6e5]" aria-hidden="true" />

          <div className="pt-[8px] flex items-center justify-between gap-[6px] whitespace-nowrap font-mono text-[10.5px] text-[#66716e]">
            <div className="flex items-center gap-[6px]">
              <span className="inline-block h-[6px] w-[6px] rounded-full bg-[#2f9d67]" />
              <span>NODE_04: LIVE</span>
            </div>
            <span>Latency: 14ms</span>
          </div>
        </div>
      </aside>

      <section aria-label="Secure workspace" className="flex-1 min-h-screen bg-[#F5F6F4]" />
    </main>
  )
}

createRoot(document.getElementById('dashboard-root')).render(<DashboardPage />)
