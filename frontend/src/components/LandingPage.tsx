import Icon from './Icon'

export default function LandingPage({ onOpen }: { onOpen: () => void }) {
  return (
    <div className="landing-page">
      <header className="landing-nav">
        <a className="landing-brand" href="/" onClick={(event) => event.preventDefault()} aria-label="VisionCraft home">
          <span className="brand-mark"><Icon name="spark" size={19} /></span>
          <span>VisionCraft</span>
        </a>
        <button className="landing-nav-cta" type="button" onClick={onOpen}>Open studio <Icon name="arrow" size={15} /></button>
      </header>

      <main>
        <section className="landing-hero">
          <div className="landing-copy">
            <p className="eyebrow"><span className="eyebrow-mark" /> Your visual ideas, realized</p>
            <h1>From screenshot<br />to <span>something real.</span></h1>
            <p className="landing-lede">Turn any interface reference into clean, responsive HTML. Describe the details, generate a first draft, and make it yours.</p>
            <div className="landing-actions">
              <button className="btn primary landing-primary" type="button" onClick={onOpen}>Open the studio <Icon name="arrow" size={16} /></button>
              <span className="landing-note"><span className="status-dot on" /> No setup in your browser</span>
            </div>
            <div className="landing-proof">
              <span><Icon name="image" size={15} /> Screenshot in</span>
              <i />
              <span><Icon name="spark" size={15} /> AI-crafted layout</span>
              <i />
              <span><Icon name="code" size={15} /> Downloadable HTML</span>
            </div>
          </div>

          <div className="hero-art" aria-label="Preview of a generated interface" role="img">
            <div className="hero-orbit orbit-one" /><div className="hero-orbit orbit-two" />
            <div className="mock-window">
              <div className="mock-topbar"><div className="mock-dots"><i /><i /><i /></div><span>preview · studio.html</span><span className="mock-live"><i /> Live preview</span></div>
              <div className="mock-layout">
                <aside className="mock-sidebar"><div className="mock-symbol">N</div><span className="mock-line short" /><span className="mock-line" /><span className="mock-line medium" /><div className="mock-side-bottom"><span className="mock-avatar" /><span className="mock-line short" /></div></aside>
                <div className="mock-content"><div className="mock-navline"><span className="mock-line short" /><span className="mock-pill">Get started ↗</span></div><div className="mock-kicker">A BETTER WAY TO CREATE</div><div className="mock-title">Make room for<br /><em>good ideas.</em></div><div className="mock-description" /><div className="mock-description second" /><div className="mock-hero-actions"><span className="mock-button" /><span className="mock-link" /></div><div className="mock-card-row"><div className="mock-feature"><b>01</b><span /><i /></div><div className="mock-feature"><b>02</b><span /><i /></div><div className="mock-feature"><b>03</b><span /><i /></div></div></div>
              </div>
              <div className="mock-float"><span className="mock-float-icon"><Icon name="spark" size={15} /></span><span><b>Ready to make it yours?</b><small>Preview, refine, and export</small></span><Icon name="check" size={15} /></div>
            </div>
            <div className="hero-caption"><span className="caption-dot" /> A first draft, made for your next idea</div>
          </div>
        </section>

        <section className="landing-details" aria-label="How VisionCraft works">
          <div><span className="detail-number">01</span><h2>Bring a reference</h2><p>Upload, paste, or drop in a screenshot that sparks an idea.</p></div>
          <div><span className="detail-number">02</span><h2>Shape the direction</h2><p>Add a few words about what to keep, change, or bring forward.</p></div>
          <div><span className="detail-number">03</span><h2>Make it yours</h2><p>Explore a live preview, edit the code, and export one HTML file.</p></div>
        </section>
      </main>
      <footer className="landing-footer"><span>VisionCraft</span><span>Designed to get you from reference to first draft.</span></footer>
    </div>
  )
}
