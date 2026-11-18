import { useEffect, useRef, useState } from "react";
import { Bot, Eraser, Send, SlidersHorizontal, X } from "lucide-react";
import { send, useStore, useUiState } from "../store";
import type { AgentPanel, SessionState } from "../types";
import { Markdown } from "../ui/Markdown";
import { Modal } from "../ui/Modal";
import { Renderer } from "../ui/Renderer";

const AUTONOMY = [
  { v: "suggest", label: "Suggest", hint: "Fills fields and points at buttons; you act" },
  { v: "semi", label: "Semi", hint: "Sends counter-offers; asks you before accepting or ending" },
  { v: "full", label: "Full", hint: "Acts on everything you allow" },
];

export function PanelView({ p }: { p: AgentPanel }) {
  const rv = useStore((s) => s.state?.reserved_value);
  return (
    <section className="enter rounded-xl border border-you/25 bg-surface">
      <div className="flex items-center justify-between border-b border-line px-3 py-2">
        <div className="flex items-center gap-1.5 text-sm font-semibold">
          <Bot size={14} className="text-you" /> {p.title}
        </div>
        <button className="btn-ghost px-1 py-0.5" aria-label="Close panel" onClick={() => send({ type: "close_panel", panel_id: p.id })}>
          <X size={14} />
        </button>
      </div>
      <div className="p-3">
        <Renderer
          components={p.components}
          ctx={{ reserved: rv, onInput: () => {}, onAction: (action, payload) => send({ type: "panel_action", panel_id: p.id, action, payload }) }}
        />
      </div>
    </section>
  );
}

function Controls({ st }: { st: SessionState }) {
  const sup = st.support!;
  return (
    <div className="flex flex-col gap-4 text-sm">
      <div>
        <div className="mb-1.5 font-semibold">How much may the assistant do?</div>
        <div className="grid grid-cols-3 gap-1 rounded-lg bg-sunken p-0.5">
          {AUTONOMY.map((a) => {
            const allowed = ["suggest", "semi", "full"].indexOf(a.v) <= ["suggest", "semi", "full"].indexOf(sup.autonomy.admin);
            const on = sup.autonomy.effective === a.v;
            return (
              <button key={a.v} disabled={!allowed} title={a.hint} aria-pressed={on} onClick={() => send({ type: "support", op: "autonomy", value: a.v })} className={`rounded-md px-2 py-1.5 text-xs font-medium disabled:opacity-40 ${on ? "bg-surface shadow-lift" : "text-muted hover:text-ink"}`}>
                {a.label}
              </button>
            );
          })}
        </div>
        <div className="mt-1 text-xs text-muted">{AUTONOMY.find((a) => a.v === sup.autonomy.effective)?.hint}</div>
      </div>
      <div>
        <div className="mb-1.5 font-semibold">Abilities</div>
        <div className="flex flex-col divide-y divide-line rounded-lg border border-line">
          {sup.capabilities
            .filter((c) => c.granted)
            .map((c) => (
              <label key={c.key} className="flex cursor-pointer items-center gap-3 px-3 py-2">
                <div className="flex-1">
                  <div className="text-sm">{c.label}</div>
                  <div className="text-xs text-muted">{c.description}</div>
                </div>
                <input type="checkbox" role="switch" className="h-4 w-4 accent-[rgb(var(--you))]" checked={c.on} onChange={(e) => send({ type: "support", op: "capability", key: c.key, value: e.target.checked })} />
              </label>
            ))}
        </div>
      </div>
      <div>
        <div className="mb-1.5 font-semibold">Unprompted messages appear as</div>
        <div className="inline-flex rounded-lg bg-sunken p-0.5">
          {[
            ["toast", "Notifications"],
            ["board", "Status board"],
            ["chat", "Chat"],
          ].map(([v, l]) => (
            <button key={v} aria-pressed={sup.proactive_delivery === v} onClick={() => send({ type: "support", op: "delivery", value: v })} className={`rounded-md px-2.5 py-1 text-xs font-medium ${sup.proactive_delivery === v ? "bg-surface shadow-lift" : "text-muted"}`}>
              {l}
            </button>
          ))}
        </div>
      </div>
      <button className="btn-ghost w-fit" onClick={() => send({ type: "support", op: "reset" })}>
        <Eraser size={14} /> Clear the conversation
      </button>
    </div>
  );
}

export function Assistant({ fill = false }: { fill?: boolean } = {}) {
  const st = useStore((s) => s.state);
  const open = useStore((s) => s.assistantOpen);
  const setOpen = useStore((s) => s.setAssistantOpen);
  const [text, setText] = useUiState("assistant.text", "");
  const [settings, setSettings] = useUiState("assistant.settings", false);
  const ref = useRef<HTMLDivElement>(null);
  const n = st?.chat.length ?? 0;
  useEffect(() => {
    if (ref.current) ref.current.scrollTop = ref.current.scrollHeight;
  }, [n, open, st?.support?.busy]);
  const asking = !!st?.pending_question;
  if (!st?.support || !open) return null;
  const sup = st.support;
  const submit = () => {
    const t = text.trim();
    if (!t) return;
    send({ type: asking ? "answer" : "chat", text: t });
    setText("");
  };
  return (
    <aside className={`flex h-full w-full flex-col bg-surface ${fill ? "" : "border-l border-line lg:w-[360px]"}`} aria-label="Assistant">
      <div className="flex items-center gap-2 border-b border-line px-3 py-2.5">
        <div className={`flex h-8 w-8 items-center justify-center rounded-full ${sup.enabled ? "bg-ink text-surface" : "bg-sunken text-muted"}`}>
          <Bot size={17} />
        </div>
        <div className="flex-1">
          <div className="text-sm font-semibold">{sup.name}</div>
          <div className="text-xs text-muted">{!sup.enabled ? "Switched off" : sup.busy ? "Working…" : "Ready to help"}</div>
        </div>
        <label className="flex cursor-pointer items-center gap-1.5 text-xs text-muted">
          <input type="checkbox" role="switch" className="peer sr-only" checked={sup.enabled} onChange={(e) => send({ type: "support", op: "enable", value: e.target.checked })} />
          <span className="relative h-4 w-7 rounded-full bg-line transition-colors after:absolute after:left-0.5 after:top-0.5 after:h-3 after:w-3 after:rounded-full after:bg-surface after:transition-transform peer-checked:bg-good peer-checked:after:translate-x-3" />
          <span className="sr-only">Assistant on</span>
        </label>
        <button className="btn-ghost px-1.5" aria-label="Assistant settings" onClick={() => setSettings(true)}>
          <SlidersHorizontal size={16} />
        </button>
        <button className="btn-ghost px-1.5" aria-label="Close assistant" onClick={() => setOpen(false)}>
          <X size={16} />
        </button>
      </div>
      <div ref={ref} className="scroll-thin flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto px-3 py-3">
        {st.chat.length === 0 && (
          <div className="mt-6 text-center text-sm text-muted">
            Ask about your opponent's offer, what to propose next, or what a tool shows.
          </div>
        )}
        {st.chat.map((m) => {
          const mine = m.user === "You";
          return (
            <div key={m.id} className={`enter flex ${mine ? "justify-end" : ""}`}>
              <div className={`max-w-[88%] rounded-xl px-3 py-2 ${mine ? "rounded-br-sm bg-you text-white" : "rounded-bl-sm bg-sunken"} ${m.kind === "question" ? "border border-you/30 bg-you/5" : ""}`}>
                {mine ? <div className="whitespace-pre-wrap text-sm">{m.text}</div> : <Markdown text={m.text} size="sm" />}
                {m.kind === "question" && st.pending_question?.id === m.question_id && (m.options?.length ?? 0) > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {m.options!.map((o) => (
                      <button key={o} className="btn-primary px-2.5 py-1 text-xs" onClick={() => send({ type: "answer", text: o })}>
                        {o}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </div>
          );
        })}
        {sup.busy && (
          <div className="flex gap-1 px-1" role="status" aria-label="The assistant is working">
            <span className="dot h-1.5 w-1.5 rounded-full bg-muted" />
            <span className="dot h-1.5 w-1.5 rounded-full bg-muted" />
            <span className="dot h-1.5 w-1.5 rounded-full bg-muted" />
          </div>
        )}
        {st.agent_panels
          .filter((p) => p.placement === "assistant")
          .map((p) => (
            <PanelView key={p.id} p={p} />
          ))}
      </div>
      <div className="border-t border-line p-2.5">
        <div className="flex items-end gap-2">
          <textarea
            className="field max-h-32 resize-none"
            rows={1}
            value={text}
            disabled={!sup.enabled}
            placeholder={asking ? "Type your answer…" : sup.enabled ? "Message the assistant" : "Switch the assistant on to chat"}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                submit();
              }
            }}
          />
          <button className="btn-primary h-9 px-3" onClick={submit} disabled={!sup.enabled || !text.trim()} aria-label="Send">
            <Send size={15} />
          </button>
        </div>
      </div>
      <Modal open={settings} onClose={() => setSettings(false)} title="Assistant settings">
        <Controls st={st} />
      </Modal>
    </aside>
  );
}

/** Open the assistant when the agent asks a question or shows a panel in it. */
export function useAutoOpenAssistant() {
  const asking = useStore((s) => s.state?.pending_question?.id);
  const panels = useStore((s) => (s.state?.agent_panels ?? []).filter((p) => p.placement === "assistant").map((p) => p.id).join(","));
  const setOpen = useStore((s) => s.setAssistantOpen);
  useEffect(() => {
    if (asking || panels) setOpen(true);
  }, [asking, panels, setOpen]);
}

export function StatusBoard() {
  const board = useStore((s) => s.state?.board);
  const hasAgent = useStore((s) => !!s.state?.support);
  const [collapsed, setCollapsed] = useUiState("statusBoard.collapsed", false);
  if (!hasAgent || !board) return null;
  return (
    <div className="flex items-start gap-2 border-t border-line bg-surface px-3 py-2 sm:px-4" role="status" aria-label="Assistant status board">
      <Bot size={15} className="mt-0.5 shrink-0 text-you" />
      <div className={`min-w-0 flex-1 ${collapsed ? "line-clamp-1" : "max-h-40 overflow-y-auto"}`}>
        <Markdown text={board} size="sm" />
      </div>
      <button className="text-xs text-muted hover:text-ink" onClick={() => setCollapsed(!collapsed)}>
        {collapsed ? "More" : "Less"}
      </button>
    </div>
  );
}

export function FloatingPanels() {
  const panels = useStore((s) => s.state?.agent_panels ?? []);
  const modal = panels.find((p) => p.placement === "modal");
  const side = panels.filter((p) => p.placement === "side");
  return (
    <>
      {side.length > 0 && (
        <div className="mx-auto flex w-full max-w-4xl flex-col gap-2 px-3 pt-3 sm:px-5">
          {side.map((p) => (
            <PanelView key={p.id} p={p} />
          ))}
        </div>
      )}
      {modal && (
        <Modal open onClose={() => send({ type: "close_panel", panel_id: modal.id })} title={modal.title} wide>
          <Renderer
            components={modal.components}
            ctx={{ onInput: () => {}, onAction: (action, payload) => send({ type: "panel_action", panel_id: modal.id, action, payload }) }}
          />
        </Modal>
      )}
    </>
  );
}
