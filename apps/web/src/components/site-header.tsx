"use client";

import Link from "next/link";
import { ArrowRight, Menu, X } from "lucide-react";
import { useState } from "react";
import { Brand } from "@/components/brand";

export function SiteHeader() {
  const [open, setOpen] = useState(false);
  return (
    <header className="site-header">
      <div className="shell header-inner">
        <Brand />
        <nav className={open ? "nav-links is-open" : "nav-links"} aria-label="Main navigation">
          <Link href="/#workflows" onClick={() => setOpen(false)}>How it works</Link>
          <Link href="/demo" onClick={() => setOpen(false)}>Live demo</Link>
          <Link href="/#security" onClick={() => setOpen(false)}>Security</Link>
          <Link className="nav-cta" href="/login" onClick={() => setOpen(false)}>
            Plan my week <ArrowRight size={16} />
          </Link>
        </nav>
        <button
          type="button"
          className="icon-button mobile-menu"
          aria-label={open ? "Close navigation" : "Open navigation"}
          aria-expanded={open}
          onClick={() => setOpen((value) => !value)}
        >
          {open ? <X size={20} /> : <Menu size={20} />}
        </button>
      </div>
    </header>
  );
}
