import { useEffect, useMemo, useRef, useState } from "react";
import { ChevronLeft } from "lucide-react";
import { api } from "../api";
import { navigate } from "../router";
import { Sidebar } from "./Sidebar";
import { LayerContext, useLayerState } from "./layer";
import { NavContext, SubPage } from "./Nav";
import { searchSettings, Hit } from "./search";
import { PAGES } from "./pages";
import { Spinner } from "./schema";
import { toast } from "./toast";
import { Tile } from "./Row";

function pageFromHash(): { page: string | null; row: string | null } {
  const [p, row] = decodeURIComponent(location.hash.slice(1)).split("/");
  if (!p) return { page: null, row: null };
  const found = PAGES.find((x) => x.id === p || x.aliases?.includes(p));
  return { page: found?.id ?? null, row: row || null };
}

/** Scroll to a row and flash it (waits for pages that load their data first). */
function reveal(id: string) {
  let tries = 0;
  const t = window.setInterval(() => {
    const el = document.getElementById(`setting-${id}`);
    if (el || ++tries > 40) {
      window.clearInterval(t);
      if (!el) return;
      el.scrollIntoView({ block: "center", behavior: "smooth" });
      el.classList.remove("setting-flash");
      void el.offsetWidth;
      el.classList.add("setting-flash");
      const f = el.matches("input,select,textarea,button") ? el : el.querySelector<HTMLElement>("input,select,textarea,button[role=switch]");
      f?.focus({ preventScroll: true });
    }
  }, 75);
}

/** The admin console: a macOS System Settings–style window (sidebar with search, one page at a time). */
export function SettingsShell() {
  const first = pageFromHash();
  const [page, setPage] = useState<string | null>(first.page ?? (window.matchMedia("(min-width: 768px)").matches ? "overview" : null));
  const [stack, setStack] = useState<SubPage[]>([]);
  const [query, setQuery] = useState("");
  const [meta, setMeta] = useState<any>(null);
  const [allowed, setAllowed] = useState<boolean | null>(null);
  const layerState = useLayerState();
  const searchRef = useRef<HTMLInputElement>(null);
  const mainRef = useRef<HTMLElement>(null);

  useEffect(() => {
    api("/api/auth/me").then((m) => {
      if (!m.user) navigate("/login?next=/admin", true);
      else setAllowed(!!m.is_admin);
    }).catch((e) => toast(e.message, "error"));
    api("/api/admin/meta").then(setMeta).catch(() => {});
    if (first.row) reveal(first.row);
    const onHash = () => {
      const h = pageFromHash();
      if (h.page) {
        setPage(h.page);
        setStack([]);
        if (h.row) reveal(h.row);
      }
    };
    window.addEventListener("hashchange", onHash);
    const k = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "f") {
        e.preventDefault();
        searchRef.current?.focus();
        searchRef.current?.select();
      }
    };
    window.addEventListener("keydown", k);
    return () => {
      window.removeEventListener("hashchange", onHash);
      window.removeEventListener("keydown", k);
    };
  }, []);
  useEffect(() => {
    history.replaceState(null, "", page ? `#${page}` : location.pathname + location.search);
  }, [page]);

  const hits = useMemo(() => searchSettings(PAGES.filter((p) => !p.href), meta, query), [query, meta]);
  const pick = (id: string) => {
    setPage(id);
    setStack([]);
    mainRef.current?.scrollTo({ top: 0 });
  };
  const onHit = (h: Hit) => {
    pick(h.page.id);
    if (h.entry) reveal(h.entry.id);
    if (!window.matchMedia("(min-width: 768px)").matches) setQuery("");
  };
  const def = PAGES.find((p) => p.id === page);
  const nav = useMemo(
    () => ({ push: (p: SubPage) => (setStack((s) => [...s, p]), mainRef.current?.scrollTo({ top: 0 })), pop: () => setStack((s) => s.slice(0, -1)), depth: stack.length }),
    [stack.length],
  );

  if (allowed === false) return <div className="flex h-screen items-center justify-center text-sm text-muted">This page is for administrators.</div>;
  if (allowed === null || !layerState.ready) return <div className="flex h-screen items-center justify-center"><Spinner /></div>;
  const sub = stack[stack.length - 1];
  const showList = page === null;
  return (
    <LayerContext.Provider value={{ layer: layerState.layer, setLayer: layerState.setLayer, info: layerState.info, reload: layerState.reload }}>
      <div className="flex h-[100dvh] overflow-hidden bg-paper">
        <aside className={`${showList ? "flex" : "hidden"} w-full shrink-0 flex-col border-r border-line md:flex md:w-64`}>
          <Sidebar pages={PAGES} current={page} onPick={pick} query={query} setQuery={setQuery} hits={hits} onHit={onHit} searchRef={searchRef} />
        </aside>
        <main ref={mainRef} className={`${showList ? "hidden" : "block"} scroll-thin min-w-0 flex-1 overflow-y-auto md:block`} aria-label={def?.title}>
          {def && (
            <NavContext.Provider value={nav}>
              <header className="sticky top-0 z-20 flex h-12 items-center gap-2 border-b border-line/70 bg-paper/85 px-3 backdrop-blur sm:px-6">
                {stack.length > 0 ? (
                  <button className="btn-ghost -ml-1 px-1.5" onClick={nav.pop} aria-label="Back">
                    <ChevronLeft size={18} />
                  </button>
                ) : (
                  <button className="btn-ghost -ml-1 px-1.5 md:hidden" onClick={() => setPage(null)} aria-label="All settings">
                    <ChevronLeft size={18} />
                  </button>
                )}
                <Tile icon={def.icon} color={def.color} />
                <h1 className="min-w-0 truncate text-[0.95rem] font-semibold">
                  {stack.length > 0 ? (
                    <>
                      <button className="hidden font-normal text-muted hover:text-ink sm:inline" onClick={() => setStack([])}>{def.title}</button>
                      {stack.map((s, i) => (
                        <span key={i} className={i === stack.length - 1 ? "" : "hidden sm:inline"}>
                          <span className="hidden px-1.5 text-muted/60 sm:inline">›</span>
                          {i === stack.length - 1 ? s.title : <button className="font-normal text-muted hover:text-ink" onClick={() => setStack(stack.slice(0, i + 1))}>{s.title}</button>}
                        </span>
                      ))}
                    </>
                  ) : (
                    def.title
                  )}
                </h1>
              </header>
              <div className="mx-auto max-w-[52rem] px-4 pb-10 pt-6 sm:px-8">
                {sub ? (
                  // the top page, and the pages under it that ask to keep their state (hidden)
                  stack.map((s, i) =>
                    i === stack.length - 1 || s.keep ? <div key={i} hidden={i !== stack.length - 1}>{s.render()}</div> : null,
                  )
                ) : (
                  <>
                    {def.subtitle && <p className="-mt-1 mb-5 text-sm text-muted">{def.subtitle}</p>}
                    <def.Component meta={meta} layer={layerState.layer} />
                  </>
                )}
              </div>
            </NavContext.Provider>
          )}
        </main>
      </div>
    </LayerContext.Provider>
  );
}
