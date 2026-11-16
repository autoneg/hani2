import { icons, type LucideProps } from "lucide-react";

function pascal(name: string) {
  return name
    .split(/[-_ ]/)
    .filter(Boolean)
    .map((p) => p[0].toUpperCase() + p.slice(1))
    .join("");
}

export function Icon({ name, ...props }: { name?: string | null } & LucideProps) {
  if (!name) return null;
  const Cmp = (icons as Record<string, any>)[pascal(name)] ?? (icons as Record<string, any>)["Wrench"];
  return <Cmp size={16} strokeWidth={1.9} aria-hidden {...props} />;
}
