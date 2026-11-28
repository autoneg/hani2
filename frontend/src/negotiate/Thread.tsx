import { useEffect, useRef } from "react";
import { CircleCheck, CircleX, Clock3, UserRound } from "lucide-react";
import { useStore } from "../store";
import type { HistoryItem } from "../types";
import { Anchor } from "../ui/Anchor";
import { Gauge } from "../ui/Gauge";
import { fmtValue, showValue } from "../ui/format";
import { Markdown } from "../ui/Markdown";
import { Renderer, STATIC_CTX } from "../ui/Renderer";
import { OpponentIcon } from "./look";

function OfferChips({ offer, tone }: { offer: Record<string, any>; tone: "you" | "opponent" }) {
  const issues = useStore((s) => s.state?.scenario?.issues);
  return (
    <div className="flex flex-wrap gap-1">
      {Object.entries(offer).map(([k, v]) => (
        <span key={k} className={`inline-flex items-baseline gap-1 rounded-md px-1.5 py-0.5 text-xs ${tone === "you" ? "bg-you/10" : "bg-opponent/10"}`}>
          <span className="text-muted">{k}</span>
          <b className="tnum font-semibold">{showValue(issues?.find((i) => i.name === k), v)}</b>
        </span>
      ))}
    </div>
  );
}

function Bubble({ h, reserved, last, display }: { h: HistoryItem; reserved: number | null; last: boolean; display: string }) {
  const mine = h.by === "human";
  const tone = mine ? "you" : "opponent";
  const role = useStore((s) => (mine ? s.state?.scenario?.role : s.state?.scenario?.opponent_role));
  const humanOpponent = useStore((s) => !!s.state?.opponent_kind && s.state.opponent_kind !== "agent");
  return (
    <Anchor id={last ? "history:last" : `history:${h.id}`} className={`enter flex gap-2.5 ${mine ? "flex-row-reverse" : ""}`}>
      <div className={`mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full ${mine ? "bg-you text-white" : "bg-opponent text-white"}`} aria-hidden>
        {mine ? <UserRound size={15} /> : <OpponentIcon human={humanOpponent} size={15} />}
      </div>
      <div className={`flex max-w-[min(34rem,85%)] flex-col gap-1.5 rounded-xl border px-3 py-2 ${mine ? "rounded-tr-sm border-you/20 bg-you/[0.04]" : "rounded-tl-sm border-opponent/25 bg-opponent/[0.05]"}`}>
        <div className="flex items-center gap-2 text-[11px] text-muted">
          <span className={`font-semibold ${mine ? "text-you" : "text-opponent"}`}>{mine ? "You" : "Opponent"}</span>
          {role && <span className="capitalize">{role}</span>}
          {h.step !== null && h.step !== undefined && <span className="tnum">round {h.step + 1}</span>}
          {h.relative_time !== null && h.relative_time !== undefined && (
            <span className="tnum inline-flex items-center gap-0.5">
              <Clock3 size={10} /> {Math.round(h.relative_time * 100)}%
            </span>
          )}
        </div>
        {h.text && <Markdown text={h.text} size="sm" />}
        {h.offer &&
          (h.view ? (
            <Renderer components={h.view} ctx={STATIC_CTX} />
          ) : display === "text" && h.offer_str ? (
            <div className="text-sm font-medium">{h.offer_str}</div>
          ) : (
            <OfferChips offer={h.offer} tone={tone} />
          ))}
        {h.data && Object.keys(h.data).length > 0 && (
          <div className="text-[11px] text-muted">
            {Object.entries(h.data)
              .map(([k, v]) => `${k}: ${fmtValue(v)}`)
              .join(", ")}
          </div>
        )}
        {h.offer && h.utility !== null && h.utility !== undefined && (
          <div className="min-w-[11rem]">
            <div className="mb-0.5 text-[11px] text-muted">Worth to you</div>
            <Gauge value={h.utility} reserved={reserved} party={tone} size="sm" parts={h.utility_parts} />
          </div>
        )}
        {!h.offer && !h.text && <div className="text-xs italic text-muted">No offer</div>}
      </div>
    </Anchor>
  );
}

export function Thread() {
  const st = useStore((s) => s.state);
  const ref = useRef<HTMLDivElement>(null);
  const items = st?.history ?? [];
  const newestFirst = !!st?.prefs.last_offer_on_top;
  const showHistory = st?.prefs.show_history !== false;
  const humanOpponent = !!st && !!st.opponent_kind && st.opponent_kind !== "agent";
  const waitingToStart = !!st?.waiting_for_opponent && st.phase === "starting";
  // a human opponent deciding is shown like an AI opponent thinking
  const humanTurn = humanOpponent && st?.phase === "running" && !st.negotiation.is_my_turn && !st.negotiation.thinking;
  const thinking = (st?.negotiation.thinking && (st.phase === "running" || st.phase === "starting")) || waitingToStart || humanTurn;
  // Keep the newest message in view: scroll to the end (or the top when the
  // newest-first option is on) whenever something is added.
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const id = requestAnimationFrame(() => {
      el.scrollTo({ top: newestFirst ? 0 : el.scrollHeight, behavior: items.length > 1 ? "smooth" : "auto" });
    });
    return () => cancelAnimationFrame(id);
  }, [items.length, thinking, newestFirst, st?.phase]);
  if (!st) return null;
  let list = showHistory ? items : items.filter((h) => h.kind === "system" || h === [...items].reverse().find((x) => x.kind === "offer" && x.by === "agent"));
  const lastId = [...items].reverse().find((x) => x.kind === "offer")?.id;
  if (newestFirst) list = [...list].reverse();
  const typing = thinking && (
    <div className="flex items-center gap-2.5 text-sm text-muted" role="status">
      <div className="flex h-7 w-7 items-center justify-center rounded-full bg-opponent/15 text-opponent">
        <OpponentIcon human={humanOpponent} size={15} />
      </div>
      <span className="inline-flex gap-1" aria-hidden>
        <span className="dot h-1.5 w-1.5 rounded-full bg-opponent" />
        <span className="dot h-1.5 w-1.5 rounded-full bg-opponent" />
        <span className="dot h-1.5 w-1.5 rounded-full bg-opponent" />
      </span>
      {waitingToStart
        ? "Waiting for the other participant…"
        : st.phase === "starting"
          ? "Setting up the negotiation…"
          : humanOpponent
            ? "Your opponent is deciding…"
            : "Your opponent is thinking…"}
    </div>
  );
  return (
    <Anchor id="history" className="flex min-h-0 flex-1 flex-col">
      <div ref={ref} className="scroll-thin flex min-h-0 flex-1 flex-col overflow-y-auto px-3 py-4 sm:px-5">
        <div className="mx-auto flex w-full max-w-4xl flex-col gap-3">
        {newestFirst && typing}
        {list.length === 0 && !thinking && (
          <div className="m-auto max-w-sm text-center text-sm text-muted">
            {st.phase === "ready" ? "Offers you and your opponent exchange will appear here." : "No offers yet."}
          </div>
        )}
        {list.map((h) =>
          h.kind === "system" ? (
            <div key={h.id} className={`mx-auto flex items-center gap-2 rounded-full px-3 py-1 text-xs font-medium ${h.status === "success" ? "bg-good/10 text-good" : "bg-sunken text-muted"}`}>
              {h.status === "success" ? <CircleCheck size={14} /> : <CircleX size={14} />}
              {h.text}
            </div>
          ) : (
            <Bubble key={h.id} h={h} reserved={st.reserved_value} last={h.id === lastId} display={st.prefs.offer_display} />
          ),
        )}
        {!newestFirst && typing}
        </div>
      </div>
    </Anchor>
  );
}
