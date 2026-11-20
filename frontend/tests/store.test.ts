// Run with `npm test`. The session store's websocket handling, with a fake WebSocket.
import assert from "node:assert/strict";
import { registerHooks } from "node:module";
import { afterEach, test } from "node:test";
import { JSDOM } from "jsdom";

// the app's sources import siblings without an extension (the bundler adds it)
registerHooks({
  resolve(spec: string, ctx: any, next: any) {
    try {
      return next(spec, ctx);
    } catch (e) {
      if (spec.startsWith(".")) return next(spec + ".ts", ctx);
      throw e;
    }
  },
});

class FakeSocket {
  static OPEN = 1;
  static all: FakeSocket[] = [];
  readyState = 0;
  sent: any[] = [];
  onopen: (() => void) | null = null;
  onclose: ((ev: any) => void) | null = null;
  onmessage: ((ev: any) => void) | null = null;
  url: string;
  constructor(url: string) {
    this.url = url;
    FakeSocket.all.push(this);
  }
  send(text: string) {
    this.sent.push(JSON.parse(text));
  }
  close() {}
  open() {
    this.readyState = 1;
    this.onopen?.();
  }
  recv(msg: any) {
    this.onmessage?.({ data: JSON.stringify(msg) });
  }
}

const { window } = new JSDOM("", { url: "http://localhost/app" });
Object.assign(globalThis, { window, document: window.document, location: window.location, WebSocket: FakeSocket });
const { useStore } = await import("../src/store.ts");

afterEach(() => useStore.getState().disconnect()); // stops its timers, or node never exits

const connect = () => {
  useStore.getState().connect("s1");
  const ws = FakeSocket.all.at(-1)!;
  ws.open();
  ws.recv({ type: "state", state: { chat: [], history: [], draft: { values: {} } } });
  return ws;
};

test("a chat message that is already shown is not added again", () => {
  const ws = connect();
  const m = { id: "a1", user: "You", text: "hi", kind: "text", time: 1 };
  ws.recv({ type: "state", state: { chat: [m], history: [], draft: { values: {} } } }); // e.g. a reconnect snapshot
  ws.recv({ type: "chat", message: m });
  ws.recv({ type: "chat", message: { ...m, id: "a2", text: "again" } });
  assert.deepEqual(useStore.getState().state!.chat.map((x: any) => x.id), ["a1", "a2"]);
});
