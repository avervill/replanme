"use client";

import Link from "next/link";
import { useState } from "react";

const pricingFeatures = {
  free: ["20 signup planning credits", "5 weekly credits", "Google Calendar connection", "Manual calendar editing", "Basic and advanced AI actions with credits"],
  pro: [
    "300 planning credits/month",
    "Weekly and monthly planning",
    "Smart rescheduling",
    "Voice-to-calendar",
    "Photo-to-calendar",
    "Energy-based scheduling",
    "Advanced optimization",
  ],
  team: ["Team availability planning", "Shared scheduling assistant", "Meeting optimization", "Role-based controls", "Team calendar insights"],
};

export default function PricingPage() {
  const [billing, setBilling] = useState<"monthly" | "yearly">("monthly");
  const isYearly = billing === "yearly";

  return (
    <main className="landing-page pricing-page">
      <header className="landing-header">
        <Link href="/#top" className="logo-link" aria-label="replanme home">
          <span className="logo-mark">r</span>
          replanme
        </Link>
        <nav className="landing-nav" aria-label="Pricing page navigation">
          <a href="/#product">Product</a>
          <a href="/#features">Features</a>
          <a href="/#faq">FAQ</a>
        </nav>
        <div className="header-actions">
          <Link href="/pricing" className="header-pricing-button" aria-current="page">
            Pricing
          </Link>
          <Link href="/login" className="header-cta">
            Sign in
          </Link>
        </div>
      </header>

      <section className="pricing-hero section-shell">
        <div className="section-intro reveal">
          <p className="section-tag">Pricing</p>
          <h1>Simple plans for calmer weeks.</h1>
          <p>Start free with planning credits, upgrade when you want a larger monthly credit balance for heavier AI planning.</p>
        </div>

        <div className="billing-toggle reveal" aria-label="Billing period">
          <button type="button" className={!isYearly ? "active" : ""} onClick={() => setBilling("monthly")}>
            Monthly
          </button>
          <button type="button" className={isYearly ? "active" : ""} onClick={() => setBilling("yearly")}>
            Yearly
          </button>
        </div>

        <div className="pricing-grid pricing-page-grid">
          <article className="pricing-card reveal">
            <h3>Free</h3>
            <p>For trying replanme and keeping manual calendar control free.</p>
            <strong>$0</strong>
            <span className="price-note">Forever</span>
            <ul>
              {pricingFeatures.free.map((feature) => (
                <li key={feature}>{feature}</li>
              ))}
            </ul>
            <Link href="/login" className="secondary-button">
              Start free
            </Link>
          </article>

          <article className="pricing-card featured-price reveal">
            <h3>Pro</h3>
            <p>For people who want AI to actively plan and optimize more of their schedule.</p>
            <strong>{isYearly ? "$10" : "$12"}</strong>
            <span className="price-note">per month</span>
            {isYearly ? <span className="annual-note">$120 paid annually</span> : null}
            <ul>
              {pricingFeatures.pro.map((feature) => (
                <li key={feature}>{feature}</li>
              ))}
            </ul>
            <Link href="/login" className="primary-button">
              Start Pro
            </Link>
          </article>

          <article className="pricing-card reveal">
            <h3>Team</h3>
            <p>For teams, managers, and founders coordinating multiple schedules.</p>
            <strong>Contact us</strong>
            <span className="price-note">Custom setup</span>
            <ul>
              {pricingFeatures.team.map((feature) => (
                <li key={feature}>{feature}</li>
              ))}
            </ul>
            <a href="mailto:hello@replanme.com?subject=replanme%20Team%20plan" className="secondary-button">
              Email us
            </a>
          </article>
        </div>
      </section>
    </main>
  );
}
