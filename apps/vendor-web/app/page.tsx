import Link from "next/link";

function BoltMark() {
  return <span className="public-brand-mark" aria-hidden="true">ϟ</span>;
}

function RouteArtwork() {
  return (
    <div className="public-route-art" aria-label="Illustrated NH-16 route from Srikakulam to Vijayawada">
      <div className="route-art-topline">
        <span className="route-art-badge">NH-16 PILOT CORRIDOR</span>
        <span className="route-art-label">ILLUSTRATIVE ROUTE</span>
      </div>
      <svg className="route-art-map" viewBox="0 0 620 420" role="img" aria-label="A route line crossing the Andhra Pradesh coastline">
        <defs>
          <pattern id="map-grid" width="36" height="36" patternUnits="userSpaceOnUse">
            <path d="M36 0H0V36" fill="none" stroke="rgba(222,244,222,.08)" strokeWidth="1" />
          </pattern>
          <linearGradient id="route-line" x1="0" x2="1" y1="1" y2="0">
            <stop offset="0" stopColor="#c7e987" />
            <stop offset="1" stopColor="#75e2ae" />
          </linearGradient>
        </defs>
        <rect width="620" height="420" fill="url(#map-grid)" />
        <path d="M-20 325c78-35 111-16 175-49 61-31 85-86 158-90 84-4 95 65 165 54 48-7 71-47 157-70" fill="none" stroke="rgba(226,241,223,.18)" strokeWidth="2" />
        <path d="M-10 264c74-10 109 20 164-5 48-22 53-74 121-91 84-20 114 31 179 10 52-17 89-72 169-75" fill="none" stroke="rgba(226,241,223,.13)" strokeWidth="2" />
        <path d="M38 370c38-56 71-89 111-112 68-39 100-2 157-39 44-28 63-94 130-103 48-7 79 16 145-24" fill="none" stroke="url(#route-line)" strokeWidth="6" strokeLinecap="round" strokeDasharray="1 0" />
        <path d="M38 370c38-56 71-89 111-112 68-39 100-2 157-39 44-28 63-94 130-103 48-7 79 16 145-24" fill="none" stroke="#fff" strokeOpacity=".32" strokeWidth="1.5" strokeLinecap="round" strokeDasharray="4 11" />
        <circle cx="38" cy="370" r="14" fill="#183e32" stroke="#d8f4a1" strokeWidth="5" />
        <circle cx="581" cy="92" r="14" fill="#183e32" stroke="#7de3b1" strokeWidth="5" />
        <circle cx="306" cy="219" r="8" fill="#b7dc68" stroke="#183e32" strokeWidth="4" />
        <circle cx="436" cy="116" r="5" fill="#fff" fillOpacity=".88" />
        <circle cx="149" cy="258" r="5" fill="#fff" fillOpacity=".88" />
      </svg>
      <div className="route-charge-stop" aria-label="Partner-listed charging stop">
        <span aria-hidden="true">ϟ</span>
        <small>PARTNER STOP</small>
      </div>
      <div className="route-city route-city-start"><span>STARTING POINT</span><strong>Srikakulam</strong></div>
      <div className="route-city route-city-end"><span>DESTINATION</span><strong>Vijayawada</strong></div>
      <div className="route-art-note"><span className="route-note-icon">ϟ</span><span><strong>Plan around the journey</strong><small>Charging · food · places to stay</small></span></div>
    </div>
  );
}

const journeySteps = [
  { number: "01", title: "Choose your stretch", description: "Start anywhere along the NH-16 pilot corridor, not only at the two endpoints." },
  { number: "02", title: "Shape your route", description: "Use your EV details and current battery charge to see a practical energy estimate." },
  { number: "03", title: "Pick a good pause", description: "Browse partner-listed charging, food and stay options before you set off." },
];

export default function HomePage() {
  return (
    <main className="public-home">
      <header className="public-header">
        <Link className="public-brand" href="/" aria-label="VoltStop home"><BoltMark /><span>VOLT<span>STOP</span><small>JOURNEYS, MADE EASIER</small></span></Link>
        <nav className="public-navigation" aria-label="Main navigation">
          <a href="#how-it-works">How it works</a>
          <a href="#corridor">NH-16 corridor</a>
          <a href="#partners">For partners</a>
        </nav>
        <div className="public-header-actions">
          <Link className="public-signin" href="/login">Sign in</Link>
          <Link className="public-button public-button-small" href="/vendor/login">Become a partner <span aria-hidden="true">↗</span></Link>
        </div>
      </header>

      <section className="public-hero" id="corridor">
        <div className="public-hero-copy">
          <div className="public-eyebrow"><span /> ANDHRA PRADESH · NH-16</div>
          <h1>Go farther.<br /><em>Pause better.</em></h1>
          <p className="public-hero-lede">A more considered way to plan your EV journey. Browse partner-listed charging, good food and places to rest along the Srikakulam–Vijayawada corridor.</p>
          <div className="public-hero-actions">
            <a className="public-button" href="#corridor">Explore pilot towns <span aria-hidden="true">↓</span></a>
            <Link className="public-text-link" href="/vendor/login">Become a partner <span aria-hidden="true">↗</span></Link>
          </div>
          <div className="public-trust-row"><span className="public-trust-icon">⌁</span><span><strong>Made for the open road</strong><small>Useful stops, thoughtfully brought together.</small></span></div>
        </div>
        <RouteArtwork />
      </section>

      <section className="public-corridor-strip" id="corridor" aria-label="NH-16 pilot corridor towns">
        <div className="corridor-town-heading"><span className="corridor-caption">NH-16 · ANDHRA PRADESH</span><strong>Choose any stretch</strong><p>Start or finish in a listed pilot town. Route estimates are available in the VoltStop mobile app.</p></div>
        <div className="corridor-town-list" aria-label="Pilot towns, north to south">
          {["Srikakulam", "Vizianagaram", "Visakhapatnam", "Anakapalle", "Tuni", "Annavaram", "Rajahmundry", "Eluru", "Vijayawada"].map((town) => <span className="corridor-town" key={town}>{town}</span>)}
        </div>
      </section>

      <section className="public-section public-value-section" id="how-it-works">
        <div className="public-section-heading">
          <p className="public-eyebrow">YOUR JOURNEY, IN BETTER RHYTHM</p>
          <h2>Good journeys are made<br className="desktop-break" /> of good stops.</h2>
          <p>VoltStop brings the things you need between here and there into one calmer trip-planning experience.</p>
        </div>
        <div className="journey-steps">
          {journeySteps.map((step) => <article className="journey-step" key={step.number}>
            <span className="journey-step-number">{step.number}</span><span className="journey-step-icon" aria-hidden="true">{step.number === "01" ? "⌖" : step.number === "02" ? "↗" : "ϟ"}</span>
            <h3>{step.title}</h3><p>{step.description}</p>
          </article>)}
        </div>
        <p className="public-data-note"><span aria-hidden="true">ⓘ</span> Charging points shown are partner listings. Live connector availability appears only when a charging network provides current data.</p>
      </section>

      <section className="public-partner-band" id="partners">
        <div className="partner-band-copy"><p className="public-eyebrow">FOR LOCAL BUSINESSES</p><h2>Be the stop they<br />remember.</h2><p>Bring your charging, dining or stay experience to EV travellers on the NH-16 corridor. Manage your listing, services and bookings in one partner workspace.</p><Link className="public-button public-button-light" href="/vendor/login">Join the partner network <span aria-hidden="true">→</span></Link></div>
        <div className="partner-band-art" aria-hidden="true"><span className="partner-orbit partner-orbit-one"/><span className="partner-orbit partner-orbit-two"/><span className="partner-bolt">ϟ</span><span className="partner-art-label">LOCAL, ALONG THE WAY</span></div>
      </section>

      <footer className="public-footer">
        <Link className="public-brand" href="/"><BoltMark /><span>VOLT<span>STOP</span><small>NH-16 · ANDHRA PRADESH</small></span></Link>
        <p>Better stops for the miles ahead.</p>
        <div><Link href="/login">Sign in</Link><Link href="/vendor/login">Partner portal</Link><Link href="/admin/login">Operations</Link></div>
      </footer>
    </main>
  );
}
