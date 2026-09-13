import { useApp } from '../stores/AppProvider'
import { BORDER_GLOW_COLORS, BorderGlow } from './ui/BorderGlow'

export function InspirationPanel() {
  const { inspirations, inspirationsError } = useApp()

  return (
    <div className="inspiration-panel">
      <header className="panel-head">
        <h2>✨ 灵感</h2>
      </header>
      <div className="inspiration-list">
        {inspirationsError ? <p className="panel-error">{inspirationsError}</p> : null}
        {inspirations.map((item) => (
          <BorderGlow
            key={item.id}
            className="inspiration-glow"
            backgroundColor="#2f2f2f"
            borderRadius={14}
            glowRadius={28}
            glowColor="40 80 80"
            colors={[...BORDER_GLOW_COLORS]}
          >
            <article className="inspiration-card">
              <img
                src={item.image_url}
                alt={`${item.city}：${item.title}`}
                className="inspiration-photo"
              />
              <div className="inspiration-caption">
                <p className="inspiration-city">{item.city}</p>
                <h3>{item.title}</h3>
                <p className="inspiration-reason">{item.description}</p>
              </div>
            </article>
          </BorderGlow>
        ))}
      </div>
    </div>
  )
}
