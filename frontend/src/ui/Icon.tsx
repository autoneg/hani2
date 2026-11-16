import type { LucideProps } from "lucide-react";
import { DynamicIcon, iconNames, type IconName } from "lucide-react/dynamic";

const known = new Set<string>(iconNames as readonly string[]);

/** Any lucide icon by kebab-case name (loaded on demand). Unknown names fall back to a wrench. */
export function Icon({ name, size = 16, ...props }: { name?: string | null } & LucideProps) {
  if (!name) return null;
  const n = (known.has(name) ? name : "wrench") as IconName;
  return <DynamicIcon name={n} size={size} strokeWidth={1.9} aria-hidden {...(props as any)} />;
}
