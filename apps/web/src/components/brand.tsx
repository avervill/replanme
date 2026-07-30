import Link from "next/link";
import { Sparkles } from "lucide-react";

export function Brand({ compact = false }: { compact?: boolean }) {
  return (
    <Link className="brand" href="/" aria-label="replanme home">
      <span className="brand-mark" aria-hidden="true">
        <Sparkles size={compact ? 16 : 18} strokeWidth={2.4} />
      </span>
      <span>replanme</span>
    </Link>
  );
}
