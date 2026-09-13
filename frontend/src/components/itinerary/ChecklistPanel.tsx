import { useState } from 'react'
import type { ChecklistItemPublic } from '../../services/itineraryService'

export function ChecklistPanel({ items }: { items: ChecklistItemPublic[] }) {
  const [checked, setChecked] = useState<Record<string, boolean>>({})
  const visible = items.filter(
    (item) => item.relevant && !/护照|签证/.test(item.text),
  )

  return (
    <section className="report-section" aria-labelledby="checklist-title">
      <h2 id="checklist-title">🎒 行前清单</h2>
      <ul className="checklist">
        {visible.map((item) => (
          <li key={item.id}>
            <label>
              <input
                type="checkbox"
                checked={Boolean(checked[item.id])}
                onChange={() =>
                  setChecked((current) => ({ ...current, [item.id]: !current[item.id] }))
                }
              />
              <span>{item.text}</span>
            </label>
          </li>
        ))}
      </ul>
    </section>
  )
}
