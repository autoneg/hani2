import { useLayer, LayerPicker, parseLayer } from "./layer";
import { useLayeredSettings } from "./settings";
import { ErrorNote, FieldGroup, SaveBar, SchemaGroups, Spinner } from "./schema";

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
          <SaveBar dirty={s.dirty} save={s.save} discard={s.discard} where={target.label} />
        </>
      )}
    </>
  );
}
