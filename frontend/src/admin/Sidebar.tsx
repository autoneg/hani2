import { useRef } from "react";
import { ArrowLeft, Clapperboard, Search, X } from "lucide-react";
import { Brand, ThemeButton } from "../negotiate/Header";
import { navigate, withBase } from "../router";
import type { PageDef } from "./types";
import type { Hit } from "./search";
import { Tile } from "./Row";

function go(path: string) {
  return (e: React.MouseEvent) => {
    e.preventDefault();
    navigate(path);
  };
}

/** The left column: brand, search field, grouped pages (or the search results), links. */
export function Sidebar({ pages, current, onPick, query, setQuery, hits, onHit, searchRef }: {
  pages: PageDef[]; current: string | null; onPick: (id: string) => void; query: string; setQuery: (q: string) => void; hits: Hit[]; onHit: (h: Hit) => void; searchRef: React.RefObject<HTMLInputElement | null>;
}) {
  const groups = [...new Set(pages.map((p) => p.group))];
  const listRef = useRef<HTMLDivElement>(null);
  const onKey = (e: React.KeyboardEvent) => {
    if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
    const items = [...(listRef.current?.querySelectorAll<HTMLElement>("[data-nav]") ?? [])];
    const i = items.indexOf(document.activeElement as HTMLElement);
    const next = items[e.key === "ArrowDown" ? Math.min(items.length - 1, i + 1) : Math.max(0, i - 1)];
    if (next) {
      e.preventDefault();
      next.focus();
    }
  };
  return (
    <nav aria-label="Administration" className="flex h-full flex-col bg-sunken/70 dark:bg-sunken" onKeyDown={onKey}>
      <div className="flex items-center justify-between px-4 pb-2 pt-4">
        <Brand />
        <ThemeButton />
      </div>
      <div className="px-3 pb-2">
        <label className="relative block">
          <span className="sr-only">Search settings</span>
          <Search size={14} className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-muted" />
          <input
            ref={searchRef}
            type="search"
            placeholder="Search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && hits[0]) onHit(hits[0]);
              if (e.key === "Escape") setQuery("");
              if (e.key === "ArrowDown") {
                e.preventDefault();
                listRef.current?.querySelector<HTMLElement>("[data-nav]")?.focus();
              }
            }}
            className="w-full rounded-lg border border-line bg-surface py-1.5 pl-8 pr-7 text-sm placeholder:text-muted focus:border-you focus:outline-none focus:ring-2 focus:ring-you/20 [&::-webkit-search-cancel-button]:hidden"
          />
          {query && (
            <button className="absolute right-2 top-1/2 -translate-y-1/2 text-muted hover:text-ink" aria-label="Clear search" onClick={() => setQuery("")}>
              <X size={14} />
            </button>
          )}
        </label>
      </div>
      <div ref={listRef} className="scroll-thin min-h-0 flex-1 overflow-y-auto px-2 pb-2">
        {query ? (
          hits.length ? (
            <ul aria-label="Search results" className="space-y-0.5">
              {hits.map((h, i) => (
                <li key={`${h.page.id}-${h.entry?.id ?? ""}-${i}`}>
                  <button data-nav onClick={() => onHit(h)} className="flex w-full items-start gap-2.5 rounded-lg px-2 py-1.5 text-left hover:bg-line/50 focus-visible:bg-line/50 focus-visible:outline-none">
                    <span className="mt-0.5">
                      <Tile icon={h.page.icon} color={h.page.color} />
                    </span>
                    <span className="min-w-0">
                      <span className="block truncate text-sm">{h.entry ? h.entry.label : h.page.title}</span>
                      <span className="block truncate text-xs text-muted">{h.entry ? h.page.title : h.page.group}</span>
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <p className="px-3 py-6 text-center text-sm text-muted">No settings match “{query}”.</p>
          )
        ) : (
          groups.map((g) => (
            <div key={g} className="mb-3">
              <div className="px-2.5 pb-1 pt-1 text-[0.7rem] font-semibold uppercase tracking-wide text-muted/80">{g}</div>
              <ul className="space-y-px">
                {pages
                  .filter((p) => p.group === g)
                  .map((p) => {
                    const active = current === p.id;
                    const cls = `flex w-full items-center gap-2.5 rounded-lg px-2 py-[5px] text-left text-sm focus-visible:outline-none ${active ? "bg-[rgb(var(--accent-strong))] text-white" : "text-ink hover:bg-line/50 focus-visible:bg-line/50"}`;
                    return (
                      <li key={p.id}>
                        {p.href ? (
                          <a data-nav href={withBase(p.href)} onClick={go(p.href)} className={cls}>
                            <Tile icon={p.icon} color={p.color} /> {p.title}
                          </a>
                        ) : (
                          <button data-nav aria-current={active ? "page" : undefined} onClick={() => onPick(p.id)} className={cls}>
                            <Tile icon={p.icon} color={active ? "bg-white/25" : p.color} /> {p.title}
                          </button>
                        )}
                      </li>
                    );
                  })}
              </ul>
            </div>
          ))
        )}
      </div>
      <div className="border-t border-line/70 p-2">
        <a className="flex items-center gap-2.5 rounded-lg px-2 py-1.5 text-sm text-muted hover:bg-line/50 hover:text-ink" href={withBase("/replay")} onClick={go("/replay")}>
          <Clapperboard size={15} /> Replay recordings
        </a>
        <a className="flex items-center gap-2.5 rounded-lg px-2 py-1.5 text-sm text-muted hover:bg-line/50 hover:text-ink" href={withBase("/app")} onClick={go("/app")}>
          <ArrowLeft size={15} /> Back to negotiating
        </a>
      </div>
    </nav>
  );
}
