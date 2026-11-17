import { useEffect, useMemo, useRef, useState } from "react";
import { ArrowRight, Check, CircleCheck, CircleX, FileText, Handshake, Loader2, Plane, Play, RefreshCw, Send, Sparkles, Wand2, X } from "lucide-react";
import { api } from "../api";
import { send, useStore, useUiState } from "../store";
import { now as clockNow } from "../clock";
import type { IssueSpec, Questionnaire, SessionState } from "../types";
import { Anchor } from "../ui/Anchor";
import { Gauge } from "../ui/Gauge";
import { clock, fmtValue, pct, showValue } from "../ui/format";
import { Markdown } from "../ui/Markdown";
import { Modal } from "../ui/Modal";

/* ------------------------------------------------------------------ */
/* Issue field                                                          */
/* ------------------------------------------------------------------ */
function IssueField({ issue, value, disabled }: { issue: IssueSpec; value: any; disabled: boolean }) {
  const set = (v: any) => {
    useStore.getState().patchDraft({ [issue.name]: v });
    send({ type: "draft", values: { [issue.name]: v } });
  };
  const values = issue.values;
  let input: React.ReactNode;
  if (values && values.length <= 6 && values.length > 0) {
    input = (
      <div className="flex flex-wrap gap-1" role="radiogroup" aria-label={issue.name}>
        {values.map((v) => {
          const on = String(v) === String(value);
          return (
            <button
              key={String(v)}
              role="radio"
              aria-checked={on}
              disabled={disabled}
              onClick={() => set(v)}
              className={`tnum min-w-[2.5rem] rounded-lg border px-2.5 py-1.5 text-sm transition-colors disabled:opacity-50 ${on ? "border-you bg-you text-white" : "border-line bg-surface hover:border-you/50"}`}
            >
              {showValue(issue, v)}
            </button>
          );
        })}
      </div>
    );
  } else if (values && values.length > 0) {
    input = (
      <select className="field tnum" value={JSON.stringify(value)} disabled={disabled} onChange={(e) => set(JSON.parse(e.target.value))} aria-label={issue.name}>
        {values.map((v) => (
          <option key={String(v)} value={JSON.stringify(v)}>
            {showValue(issue, v)}
          </option>
        ))}
      </select>
    );
  } else {
    input = (
      <input
        type="number"
        className="field tnum"
        aria-label={issue.name}
        min={issue.min}
        max={issue.max}
        step={issue.kind === "int" ? 1 : "any"}
        value={value ?? ""}
        disabled={disabled}
        onChange={(e) => e.target.value !== "" && set(Number(e.target.value))}
      />
    );
  }
  return (
    <Anchor id={`issue:${issue.name}`} className="min-w-0">
      <div className="mb-1 flex items-baseline justify-between gap-2">
        <span className="text-sm font-medium">{issue.name}</span>
        {issue.min !== undefined && !values && (
          <span className="tnum text-[11px] text-muted">
            {fmtValue(issue.min)}–{fmtValue(issue.max)}
          </span>
        )}
      </div>
      {input}
      {issue.description && <div className="mt-1 text-[11px] text-muted">{issue.description}</div>}
    </Anchor>
  );
}

/* ------------------------------------------------------------------ */
/* Confirmation dialog                                                  */
/* ------------------------------------------------------------------ */
export function ConfirmDialog() {
  const confirm = useStore((s) => s.confirm);
  const setConfirm = useStore((s) => s.setConfirm);
  const st = useStore((s) => s.state);
  useEffect(() => {
    if (confirm) send({ type: "event", name: "modal_opened", component: "confirm", action: confirm.kind });
  }, [confirm]);
  if (!st || !confirm) return null;
  const rv = st.reserved_value;
  const po = st.partner_offer;
  const accept = confirm.kind === "accept";
  const below = accept && po?.utility != null && po.utility < rv;
  return (
    <Modal open onClose={() => setConfirm(null)} title={accept ? "Accept this offer?" : "End without agreement?"}>
      <div className="flex flex-col gap-3 text-sm">
        {confirm.message && <div className="rounded-lg bg-you/10 px-3 py-2">{confirm.message}</div>}
        {accept && po ? (
          <>
            <div className="font-medium">{po.text}</div>
            <div>
              <div className="mb-1 text-xs text-muted">You will receive</div>
              <Gauge value={po.utility} reserved={rv} size="lg" />
            </div>
            {below && (
              <div className="rounded-lg border border-bad/30 bg-bad/10 px-3 py-2 text-bad">
                This offer is worth less to you ({pct(po.utility, 1)}) than ending the negotiation ({pct(rv, 1)}).
              </div>
            )}
          </>
        ) : (
          <p>
            The negotiation ends and you receive your value on disagreement: <b className="tnum">{pct(rv, 1)}</b>.
          </p>
        )}
        <div className="mt-1 flex justify-end gap-2">
          <button className="btn-secondary" onClick={() => setConfirm(null)}>
            Cancel
          </button>
          <button
            className={accept ? "btn-success" : "btn bg-bad text-white hover:bg-bad/90"}
            onClick={() => {
              send({ type: accept ? "accept" : "end" });
              setConfirm(null);
            }}
          >
            {accept ? "Accept offer" : "End negotiation"}
          </button>
        </div>
      </div>
    </Modal>
  );
}

/* ------------------------------------------------------------------ */
/* Running: offer on the table, decisions, counter-offer editor         */
/* ------------------------------------------------------------------ */
function Running({ st }: { st: SessionState }) {
  const setConfirm = useStore((s) => s.setConfirm);
  const draftVersion = useStore((s) => s.draftVersion);
  const myTurn = st.negotiation.is_my_turn && !st.negotiation.thinking;
  const po = st.partner_offer;
  const rv = st.reserved_value;
  const [countering, setCountering] = useUiState("dock.countering", false);
  const [text, setText] = useUiState("dock.text", st.draft.text || "");
  const [textOnly, setTextOnly] = useUiState("dock.textOnly", !!st.settings.text_only_mode);
  const timer = useRef<number | undefined>(undefined);
  useEffect(() => setText(st.draft.text || ""), [draftVersion]); // agent wrote the message
  useEffect(() => {
    if (!myTurn) setCountering(false);
  }, [myTurn]);
  const highlightedReject = st.highlights.some((h) => h.target === "reject" || h.target === "send" || h.target === "offer");
  const showEditor = countering || !po || !!st.prefs.offer_panel_always_visible || highlightedReject;
  const allowText = st.settings.allow_text_human !== false;
  const issues = st.scenario?.issues ?? [];
  const cols = Math.min(3, Math.max(1, st.scenario?.n_issue_columns ?? 2));
  const onText = (v: string) => {
    setText(v);
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => send({ type: "draft_text", text: v }), 250);
  };
  const doSend = () => {
    window.clearTimeout(timer.current);
    send({ type: "send", text, text_only: textOnly, values: useStore.getState().state?.draft.values });
    setText("");
  };

  if (st.autopilot.active) {
    return (
      <div className="flex items-center gap-3 rounded-xl border border-you/30 bg-you/5 px-4 py-3">
        <Plane size={18} className="text-you" />
        <div className="flex-1 text-sm">
          <div className="font-semibold">Autopilot is negotiating for you</div>
          <div className="text-muted">Driver: {st.autopilot.driver}. The history keeps updating.</div>
        </div>
        <button className="btn-secondary" onClick={() => send({ type: "autopilot", active: false })}>
          Take back control
        </button>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      <Anchor id="partner_offer">
        <div className={`rounded-xl border px-4 py-3 ${po ? "border-partner/30 bg-partner/[0.05]" : "border-dashed border-line"}`}>
          {po ? (
            <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
              <div className="min-w-[10rem] flex-1">
                <div className="text-xs font-medium text-partner">Offer on the table</div>
                <div className="font-semibold">{po.text}</div>
              </div>
              <div className="min-w-[10rem] max-w-full flex-1 sm:max-w-[14rem]">
                <div className="mb-0.5 text-[11px] text-muted">Worth to you · line marks no-deal value</div>
                <Gauge value={po.utility} reserved={rv} party="partner" />
              </div>
            </div>
          ) : (
            <div className="text-sm text-muted">{st.negotiation.thinking ? "Waiting for your partner…" : "No offer on the table yet. Make the first offer."}</div>
          )}
        </div>
      </Anchor>

      <div className="flex flex-wrap items-center gap-2">
        <Anchor id="accept">
          <button className="btn-success px-4 py-2" disabled={!myTurn || !po} onClick={() => setConfirm({ kind: "accept" })}>
            <Check size={16} /> Accept {po?.utility != null && <span className="tnum opacity-90">{pct(po.utility)}</span>}
          </button>
        </Anchor>
        <Anchor id="reject">
          <button className={`btn px-4 py-2 ${showEditor ? "bg-you text-white" : "border border-you/40 bg-surface text-you hover:bg-you/5"}`} disabled={!myTurn} onClick={() => setCountering(!countering)} aria-expanded={showEditor}>
            <ArrowRight size={16} /> Counter-offer
          </button>
        </Anchor>
        <div className="flex-1" />
        <Anchor id="end">
          <button className="btn-danger px-3 py-2" disabled={!myTurn} onClick={() => setConfirm({ kind: "end" })}>
            <X size={16} /> End <span className="tnum opacity-80">{pct(rv)}</span>
          </button>
        </Anchor>
      </div>

      {showEditor && (
        <Anchor id="offer" className="enter">
          <div className="rounded-xl border border-line bg-surface p-3 sm:p-4">
            {!textOnly && (
              <div className="grid gap-3" style={{ gridTemplateColumns: `repeat(auto-fit, minmax(min(100%, ${cols === 1 ? 600 : cols === 2 ? 220 : 160}px), 1fr))` }}>
                {issues.map((i) => (
                  <IssueField key={i.name} issue={i} value={st.draft.values[i.name]} disabled={!myTurn} />
                ))}
              </div>
            )}
            {!textOnly && (
              <div className="mt-3 rounded-lg bg-sunken/70 px-3 py-2">
                <div className="mb-1 text-xs text-muted">If your partner accepts this offer you get</div>
                <Gauge value={st.draft.utility} reserved={rv} size="lg" />
              </div>
            )}
            <div className="mt-3 flex flex-col gap-2 sm:flex-row sm:items-end">
              {allowText && (
                <Anchor id="message" className="flex-1">
                  <label className="label" htmlFor="hani-msg">
                    Message to your partner (optional)
                  </label>
                  <textarea
                    id="hani-msg"
                    className="field resize-none"
                    rows={2}
                    value={text}
                    placeholder="Explain your offer…"
                    disabled={!myTurn}
                    onChange={(e) => onText(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && (e.metaKey || e.ctrlKey) && myTurn) doSend();
                    }}
                  />
                </Anchor>
              )}
              <Anchor id="send">
                <button className="btn-primary w-full px-5 py-2 sm:w-auto" disabled={!myTurn} onClick={doSend}>
                  <Send size={15} /> Send offer
                </button>
              </Anchor>
            </div>
            {st.is_admin && (
              <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-line pt-3 text-xs">
                <span className="text-muted">Admin</span>
                <label className="inline-flex items-center gap-1.5">
                  <input type="checkbox" className="accent-[rgb(var(--you))]" checked={textOnly} onChange={(e) => setTextOnly(e.target.checked)} /> Text only
                </label>
                <button className="btn-ghost px-2 py-1 text-xs" onClick={() => send({ type: "extract" })}>
                  <Wand2 size={13} /> Offer from message
                </button>
                <button className="btn-ghost px-2 py-1 text-xs" onClick={() => send({ type: "generate" })}>
                  <Sparkles size={13} /> Write message
                </button>
              </div>
            )}
          </div>
        </Anchor>
      )}
      {!myTurn && st.phase === "running" && !st.negotiation.thinking && <div className="text-xs text-muted">Waiting…</div>}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Intro: load / start                                                  */
/* ------------------------------------------------------------------ */
function AutoCountdown({ st }: { st: SessionState }) {
  const [, tick] = useState(0);
  const now = clockNow();
  useEffect(() => {
    const t = window.setInterval(() => tick((x) => x + 1), 500);
    return () => window.clearInterval(t);
  }, []);
  const d = st.study.auto_deadline;
  if (!d) return null;
  return (
    <div className="tnum text-xs text-muted">
      {st.study.auto_kind === "start" ? "Starts" : "The next negotiation starts"} automatically in {clock(d - now)}
    </div>
  );
}

function AdminPickers({ st }: { st: SessionState }) {
  const [meta, setMeta] = useState<any>(null);
  const [type, setType] = useState<string>(st.scenario?.type ?? "");
  const [name, setName] = useState<string>("");
  useEffect(() => {
    if (st.is_admin) api("/api/admin/meta").then(setMeta).catch(() => {});
  }, [st.is_admin]);
  const setTypes: string[] | undefined = meta?.scenario_sets?.[st.settings?.scenario_set || meta?.scenario_set];
  const agents: string[] = useMemo(() => {
    if (!meta) return [];
    const all = new Set<string>();
    Object.values((meta.opponent_groups ?? meta.agent_groups) as Record<string, string[]>).forEach((g) => g.forEach((a) => all.add(a)));
    return Array.from(all);
  }, [meta]);
  return (
    <div className="grid gap-3 rounded-xl border border-dashed border-line p-3 sm:grid-cols-2">
      {st.can_choose_scenario && (
        <div>
          <span className="label">Scenario</span>
          <div className="flex gap-1.5">
            {meta?.scenario_sets && (
              <select
                className="field"
                aria-label="Scenario set"
                value={st.settings?.scenario_set ?? ""}
                onChange={(e) => { send({ type: "pref", key: "scenario_set", value: e.target.value || null }); setType(""); setName(""); }}
              >
                <option value="">Default set ({meta.scenario_set})</option>
                {Object.keys(meta.scenario_sets).map((k: string) => (
                  <option key={k} value={k}>{k}</option>
                ))}
              </select>
            )}
            <select className="field" value={type} onChange={(e) => { setType(e.target.value); setName(""); }}>
              <option value="">Next in order</option>
              {(setTypes ?? meta?.scenario_types ?? ["Trade", "Island", "Grocery"]).map((t: string) => (
                <option key={t}>{t}</option>
              ))}
            </select>
            {meta && type && (meta.scenarios[type] ?? []).length > 0 && (
              <select className="field" value={name} onChange={(e) => setName(e.target.value)}>
                <option value="">Any</option>
                {meta.scenarios[type].map((n: string) => (
                  <option key={n}>{n}</option>
                ))}
              </select>
            )}
            <button className="btn-secondary shrink-0" onClick={() => send({ type: "load", scenario_type: type || null, name: name || null })}>
              Load
            </button>
          </div>
        </div>
      )}
      {st.admin_mode && (
        <div>
          <span className="label">Opponent for the next negotiation</span>
          <input
            className="field"
            list="hani-agents"
            placeholder="Random from the pool"
            defaultValue={st.next_opponent ?? ""}
            onBlur={(e) => send({ type: "opponent", spec: e.target.value })}
            onKeyDown={(e) => e.key === "Enter" && send({ type: "opponent", spec: (e.target as HTMLInputElement).value })}
          />
          <datalist id="hani-agents">
            {agents.map((a) => (
              <option key={a} value={a} />
            ))}
          </datalist>
        </div>
      )}
    </div>
  );
}

function Intro({ st }: { st: SessionState }) {
  const [md, setMd] = useState("");
  useEffect(() => {
    api("/api/announcements").then((r) => setMd(r.markdown)).catch(() => {});
  }, []);
  const prolific = st.study.kind === "prolific";
  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-start gap-4">
        <div className="hidden h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-you/10 text-you sm:flex">
          <Handshake size={22} />
        </div>
        <div className="flex-1">
          <div className="text-lg font-semibold">{st.round.label}</div>
          {st.scenario && (
            <p className="text-sm text-muted">
              {st.scenario.title}.{" "}
              {st.scenario.role ? (
                <>
                  You negotiate as the <b className="text-ink">{st.scenario.role}</b>.{" "}
                </>
              ) : null}
              Check your Preferences, then start.
            </p>
          )}
          {prolific && (
            <p className="mt-1 text-sm text-muted">
              {st.study.practice_next ? "This first negotiation is a practice round and does not count." : `${st.study.counted} of ${st.study.required} counted negotiations done.`}
            </p>
          )}
        </div>
      </div>
      {md && st.round.number === 0 && (
        <div className="rounded-xl bg-sunken/70 px-4 py-3">
          <Markdown text={md} size="sm" />
        </div>
      )}
      {(st.can_choose_scenario || st.admin_mode) && <AdminPickers st={st} />}
      <div className="flex flex-wrap items-center gap-3">
        <button className="btn-primary px-5 py-2.5 text-base" onClick={() => send({ type: "start" })} disabled={!st.scenario}>
          <Play size={17} /> Start negotiation
        </button>
        {!prolific && (
          <button className="btn-ghost" onClick={() => send({ type: "load" })} title="Load a different scenario">
            <RefreshCw size={15} /> Different scenario
          </button>
        )}
        <AutoCountdown st={st} />
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Result, questionnaire, completion                                    */
/* ------------------------------------------------------------------ */
function ResultCard({ st }: { st: SessionState }) {
  const r = st.result;
  const ok = r?.status === "success";
  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-start gap-3">
        <div className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-xl ${ok ? "bg-good/10 text-good" : "bg-sunken text-muted"}`}>{ok ? <CircleCheck size={22} /> : <CircleX size={22} />}</div>
        <div className="flex-1">
          <div className="text-lg font-semibold">{ok ? "Agreement reached" : "No agreement"}</div>
          <div className="text-sm text-muted">{ok ? r?.agreement_str : r?.status === "timedout" ? "The time ran out." : r?.ended_by === "human" ? "You ended the negotiation." : r?.ended_by === "agent" ? "Your partner ended the negotiation." : "The negotiation ended."}</div>
        </div>
      </div>
      {r && (
        <div className="rounded-xl bg-sunken/70 px-4 py-3">
          <div className="mb-1 text-xs text-muted">Your result</div>
          <Gauge value={r.human_utility} reserved={r.reserved_value} size="lg" />
        </div>
      )}
      {st.notice && <div className={`rounded-lg px-3 py-2 text-sm ${st.notice.level === "error" ? "bg-bad/10 text-bad" : st.notice.level === "success" ? "bg-good/10 text-good" : "bg-you/10"}`}>{st.notice.text}</div>}
      <div className="flex flex-wrap items-center gap-3">
        <button className="btn-primary px-5 py-2.5" onClick={() => send({ type: "load" })}>
          <ArrowRight size={16} /> Next negotiation
        </button>
        <AutoCountdown st={st} />
      </div>
    </div>
  );
}

function QuestionnaireForm({ q }: { q: Questionnaire }) {
  const [answers, setAnswers] = useState<Record<string, any>>({});
  const [busy, setBusy] = useState(false);
  const set = (id: string, v: any) => setAnswers((a) => ({ ...a, [id]: v }));
  return (
    <form
      className="flex flex-col gap-4"
      onSubmit={(e) => {
        e.preventDefault();
        setBusy(true);
        send({ type: "questionnaire", answers });
        window.setTimeout(() => setBusy(false), 1500);
      }}
    >
      <div className="flex items-center gap-3">
        <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-you/10 text-you">
          <FileText size={22} />
        </div>
        <div>
          <div className="text-lg font-semibold">{q.title ?? "A few questions"}</div>
          {q.intro && <div className="text-sm text-muted">{q.intro}</div>}
        </div>
      </div>
      {q.questions.map((qq) => {
        const n = qq.type === "likert7" ? 7 : qq.type === "likert5" ? 5 : 0;
        return (
          <fieldset key={qq.id} className="flex flex-col gap-2">
            <legend className="mb-1 text-sm">
              <Markdown text={qq.text + (qq.required ? "" : "")} size="sm" />
            </legend>
            {n > 0 && (
              <div>
                <div className="flex gap-1">
                  {Array.from({ length: n }, (_, i) => i + 1).map((v) => (
                    <button type="button" key={v} aria-pressed={answers[qq.id] === v} onClick={() => set(qq.id, v)} className={`tnum h-9 flex-1 rounded-lg border text-sm ${answers[qq.id] === v ? "border-you bg-you text-white" : "border-line hover:border-you/50"}`}>
                      {v}
                    </button>
                  ))}
                </div>
                {qq.labels && (
                  <div className="mt-1 flex justify-between text-[11px] text-muted">
                    <span>{qq.labels["1"] ?? (qq.labels as any)[1]}</span>
                    <span>{qq.labels[String(n)] ?? (qq.labels as any)[n]}</span>
                  </div>
                )}
              </div>
            )}
            {qq.type === "yes_no" && (
              <div className="flex gap-2">
                {["yes", "no"].map((v) => (
                  <button type="button" key={v} aria-pressed={answers[qq.id] === v} onClick={() => set(qq.id, v)} className={`h-9 w-24 rounded-lg border text-sm capitalize ${answers[qq.id] === v ? "border-you bg-you text-white" : "border-line hover:border-you/50"}`}>
                    {v}
                  </button>
                ))}
              </div>
            )}
            {qq.type === "select" && (
              <select className="field" value={answers[qq.id] ?? ""} onChange={(e) => set(qq.id, e.target.value)}>
                <option value="">Choose…</option>
                {(qq.options ?? []).map((o) => (
                  <option key={o}>{o}</option>
                ))}
              </select>
            )}
            {qq.type === "text" && <textarea className="field" rows={2} value={answers[qq.id] ?? ""} onChange={(e) => set(qq.id, e.target.value)} />}
          </fieldset>
        );
      })}
      <button className="btn-primary w-fit px-5 py-2" disabled={busy}>
        {busy ? <Loader2 size={15} className="animate-spin" /> : <Check size={15} />} Submit answers
      </button>
    </form>
  );
}

function Finished({ st }: { st: SessionState }) {
  return (
    <div className="flex flex-col items-start gap-3">
      <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-good/10 text-good">
        <CircleCheck size={22} />
      </div>
      <div className="text-lg font-semibold">You're all done. Thank you!</div>
      <p className="max-w-prose text-sm text-muted">You completed every negotiation. Use the button below to finish and submit your session.</p>
      {st.finish_url && (
        <a className="btn-success px-5 py-2.5" href={st.finish_url} target="_top">
          Finish and submit <ArrowRight size={16} />
        </a>
      )}
    </div>
  );
}

export function ActionDock({ embedded = false, maxHeight = "max-h-[64vh]" }: { embedded?: boolean; maxHeight?: string }) {
  const st = useStore((s) => s.state);
  if (!st) return null;
  let body: React.ReactNode;
  if (st.phase === "running" || st.phase === "starting") body = <Running st={st} />;
  else if (st.phase === "ended") body = <ResultCard st={st} />;
  else if (st.phase === "questionnaire" && st.questionnaire) body = <QuestionnaireForm q={st.questionnaire} />;
  else if (st.phase === "finished") body = <Finished st={st} />;
  else body = <Intro st={st} />;
  return (
    <div
      className={`scroll-thin overflow-y-auto bg-surface/80 px-3 py-3 backdrop-blur sm:px-5 sm:py-4 ${
        embedded ? "min-h-0 min-w-[300px] flex-1" : `${maxHeight} border-t border-line`
      }`}
    >
      <div className="mx-auto w-full max-w-4xl">{body}</div>
    </div>
  );
}
