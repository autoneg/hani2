// HANI2's bridge for pi (loaded with `pi --mode rpc -ne -e pi_bridge.ts --no-tools --tools <names>`).
//
// * The system prompt of every request is exactly HANI2's (read from HANI2_PI_SYSTEM_FILE), so
//   nothing of pi's default coding prompt (or the working folder) reaches the model.
// * HANI2's functions (read from HANI2_PI_TOOLS_FILE: [{name, description, parameters}]) are
//   registered as pi tools whose execute() asks the RPC host (HANI2) to run them, through pi's
//   extension UI request `input` (see pi's docs/rpc.md and docs/extensions.md). HANI2 runs each call
//   through the Assistant's dispatcher and answers with the result. Nothing runs here.
// * No commands are registered, so a participant's "/name" text is never run as a command.
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { readFileSync } from "node:fs";

function readJson(path: string | undefined, fallback: any): any {
  if (!path) return fallback;
  try {
    return JSON.parse(readFileSync(path, "utf8"));
  } catch {
    return fallback;
  }
}

export default function (pi: ExtensionAPI) {
  const system = process.env.HANI2_PI_SYSTEM_FILE ? readFileSync(process.env.HANI2_PI_SYSTEM_FILE, "utf8") : "";
  const specs: any[] = readJson(process.env.HANI2_PI_TOOLS_FILE, []);
  const timeout = Number(process.env.HANI2_PI_TOOL_TIMEOUT_MS || "60000");
  pi.on("before_agent_start", async () => ({ systemPrompt: system || "You are a helpful assistant." }));
  for (const spec of specs) {
    pi.registerTool({
      name: spec.name,
      label: spec.name,
      description: spec.description || spec.name,
      parameters: spec.parameters || { type: "object", properties: {} },
      async execute(toolCallId: string, params: any, signal: any, _onUpdate: any, ctx: any) {
        const reply = await ctx.ui.input("hani2_function_call", JSON.stringify({ name: spec.name, id: toolCallId, arguments: params }), {
          signal,
          timeout,
        });
        if (reply === undefined) throw new Error("HANI2 did not answer the function call");
        return { content: [{ type: "text", text: String(reply) }], details: undefined };
      },
    } as any);
  }
}
