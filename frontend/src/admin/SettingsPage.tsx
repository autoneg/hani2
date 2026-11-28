import { useLayer, LayerPicker, parseLayer } from "./layer";
import { useLayeredSettings } from "./settings";
import { ErrorNote, FieldGroup, SaveBar, SchemaGroups, Spinner } from "./schema";
import { RawFile, jsonObjectProblem } from "./RawFile";
import { api } from "../api";
import { lq } from "./layer";
import { toast } from "./toast";

const FILE: Record<string, string> = { env: "env.json", llm: "llm_settings.json", assistant: "assistant_settings.json", autopilot: "autopilot_settings.json" };

const SHARED = parseLayer("settings");

/** A page that edits one JSON settings file through declarative field groups. */
export function SettingsPage({ kind, groups, layered = true, top, note }: { kind: string; groups: FieldGroup[] | ((get: (p: string) => any) => FieldGroup[]); layered?: boolean; top?: (get: (p: string) => any) => React.ReactNode; note?: React.ReactNode }) {
  const { layer } = useLayer();
  const target = layered ? layer : SHARED;
  const s = useLayeredSettings(kind, target);
  return (
    <>
      {layered ? <LayerPicker /> : note}
      {s.error && <ErrorNote>{s.error}</ErrorNote>}
      {!s.data ? (
        !s.error && <Spinner />
      ) : (
        <>
          {top?.(s.get)}
          <SchemaGroups groups={typeof groups === "function" ? groups(s.get) : groups} s={s} />
          {FILE[kind] && (
            <RawFile
              id={`raw-${kind}`}
              title={`${target.label}: ${FILE[kind]} as JSON`}
              text={JSON.stringify(s.own ?? {}, null, 2)}
              load={() => api(`/api/admin/settings/${kind}${lq(target)}`).then((r: any) => JSON.stringify(r?.own ?? {}, null, 2))}
              parse={jsonObjectProblem}
              locked={s.dirty}
              lockedNote="Save or revert the changes above first: both write this file."
              footer={`Only this layer's own values; the rest is inherited.${FILE[kind] === "env.json" ? " The General, Negotiation, Participant interface and Tool settings pages all edit this one file." : ""} Saving replaces the file.`}
              save={async (t) => {
                try {
                  await api(`/api/admin/settings/${kind}${lq(target)}`, { method: "PUT", body: t.trim() ? JSON.parse(t) : {} });
                  await s.reload();
                  toast(`Saved ${FILE[kind]} of ${target.label}. New sessions use it.`);
                } catch (e: any) {
                  toast(e.message, "error");
                  throw e;
                }
              }}
            />
          )}
          <SaveBar dirty={s.dirty} save={s.save} discard={s.discard} where={target.label} />
        </>
      )}
    </>
  );
}
