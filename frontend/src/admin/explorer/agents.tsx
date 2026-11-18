import { useState } from "react";
import { Bot, Swords } from "lucide-react";
import { Group } from "../Group";
import { Row } from "../Row";
import { useLayer, type Layer } from "../layer";
import { Select } from "../controls/Select";
import { Balance } from "../pages/Projects";
import { PoolPicker } from "./PoolPicker";
import { choices } from "./library";
import type { Adapter, ExGroup, ExItem } from "./types";

type Kind = "opponent" | "assistant";

/** The pool participants face (opponents) or get (Assistants) at the layer, and the Assistant balance. */
function makeExtra(kind: Kind) {
  return function Extra({ layer, groups, items }: { layer: Layer; groups: ExGroup[]; items: ExItem[] }) {
    const { info } = useLayer();
    const studies = info.layers.filter((l) => l.kind === "study" && (layer.kind !== "project" || l.project === layer.project));
    const [st, setSt] = useState<string>("");
    const s = layer.kind === "study" ? `${layer.project}/${layer.study}` : st || (studies[0] ? `${studies[0].project}/${studies[0].study}` : "");
    return (
      <>
        <PoolPicker kind={kind} layer={layer} choices={choices(items, groups)} title={kind === "opponent" ? "Opponents participants face" : "Assistants participants get"} id={`${kind}-pool`} />
        {kind === "assistant" && s && (
          <>
            {layer.kind !== "study" && (
              <Group title="Balance in a study">
                <Row label="Study">
                  <Select label="Study for the balance" value={s} onChange={setSt} options={studies.map((l) => `${l.project}/${l.study}`)} />
                </Row>
              </Group>
            )}
            <Balance key={s} project={s.split("/")[0]} study={s.split("/")[1]} />
          </>
        )}
      </>
    );
  };
}

export function agentsAdapter(kind: Kind): Adapter {
  const noun = kind === "opponent" ? "opponent" : "Assistant";
  return {
    kind: kind === "opponent" ? "opponents" : "assistants",
    noun,
    nouns: `${noun}s`,
    groupNoun: "group",
    groupNouns: `${noun} groups`,
    icon: kind === "opponent" ? Swords : Bot,
    color: kind === "opponent" ? "bg-opponent" : "bg-you",
    code: true,
    accept: ".py,.zip",
    linkHint: kind === "opponent" ? "/srv/agents or pkg.mod.Class" : "/srv/assistants or pkg.mod:Class",
    uploadHint: `A .py file, or a .zip of a package; every ${noun} class found is added (or the classes named). Group files list the classes by their spec and import path, so they work on their own.`,
    Extra: makeExtra(kind),
    validKey: (k) => /^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/.test(k) && !k.includes(".."),
  };
}
