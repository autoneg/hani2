import { useEffect } from "react";
import {
  Bot,
  BrainCircuit,
  Briefcase,
  Building2,
  Compass,
  Factory,
  Feather,
  Globe,
  Landmark,
  Lightbulb,
  Sparkles,
  Store,
  UserRound,
  WandSparkles,
  type LucideIcon,
  type LucideProps,
} from "lucide-react";
import { useStore } from "../store";

/**
 * A different look for the Assistant and the opponent in each negotiation
 * (env.json → interface.vary_appearance; the server picks it, see hani2.appearance).
 * The colours are CSS variables (--assistant, --opponent) switched by data attributes on <html>,
 * so every Assistant and opponent mark (portals and popups included) follows; the icons are below.
 */
const ICONS: Record<string, LucideIcon> = {
  bot: Bot,
  sparkles: Sparkles,
  "brain-circuit": BrainCircuit,
  lightbulb: Lightbulb,
  "wand-sparkles": WandSparkles,
  compass: Compass,
  feather: Feather,
  briefcase: Briefcase,
  "building-2": Building2,
  store: Store,
  landmark: Landmark,
  factory: Factory,
  globe: Globe,
};

/** Put this negotiation's colours on the page (call once, from the negotiation page). */
export function useLookColors() {
  const look = useStore((s) => s.state?.interface?.appearance ?? null);
  const a = look?.assistant?.color ?? "";
  const o = look?.opponent?.color ?? "";
  useEffect(() => {
    const el = document.documentElement;
    const set = (k: string, v: string) => (v ? el.setAttribute(k, v) : el.removeAttribute(k));
    set("data-look-assistant", a);
    set("data-look-opponent", o);
    return () => {
      el.removeAttribute("data-look-assistant");
      el.removeAttribute("data-look-opponent");
    };
  }, [a, o]);
}

/** Whether the Assistant has a colour of its own in this negotiation. */
export function useAssistantLooks(): boolean {
  return useStore((s) => !!s.state?.interface?.appearance?.assistant);
}

/** The Assistant's icon in this negotiation (the robot unless it varies). */
export function AssistantIcon(props: LucideProps) {
  const key = useStore((s) => s.state?.interface?.appearance?.assistant?.icon);
  const I = (key && ICONS[key]) || Bot;
  return <I {...props} />;
}

/** The opponent's icon: a person for a human opponent, else the AI opponent's icon in this negotiation. */
export function OpponentIcon({ human, ...props }: LucideProps & { human?: boolean }) {
  const key = useStore((s) => s.state?.interface?.appearance?.opponent?.icon);
  const I = human ? UserRound : (key && ICONS[key]) || Bot;
  return <I {...props} />;
}
