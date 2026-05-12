"use client";

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/lib/auth';
import { CreditsBadge } from '@/components/credits-badge';
import { LowCreditsWarning } from '@/components/low-credits-warning';

type NavbarProps = {
    onSettingsClick?: () => void;
};

export function Navbar({ onSettingsClick }: NavbarProps) {
    const { user, logout } = useAuth();
    const router = useRouter();

    const handleSignOut = () => {
        logout();
        router.replace("/login");
    };

    return (
        <header className="dashboard-header">
            <Link href="/dashboard" className="dashboard-brand" aria-label="replanme dashboard">
                <span className="logo-mark">r</span>
                <span>replanme</span>
            </Link>
            <nav className="dashboard-nav" aria-label="Dashboard navigation">
                {user && (
                    <>
                        <CreditsBadge plan={user.plan} credits={user.planning_credits} />
                        <LowCreditsWarning credits={user.planning_credits} />
                    </>
                )}
                <button type="button" onClick={onSettingsClick}>Settings</button>
                <Link href="/pricing" className="dashboard-pricing-link">Pricing</Link>
                <button type="button" onClick={handleSignOut}>Sign out</button>
            </nav>
        </header>
    );
}
