"""The functions the Assistant's language model may call.

Each function is gated by a :class:`~hani2.support_agent.capabilities.Capability`
(or ``None`` for read-only helpers) and only advertised to the model while that
capability is effective. Subclass :class:`ToolDispatcher` and override
:meth:`ToolDispatcher.register_extra_tools` to add your own functions.
"""

from __future__ import annotations

from typing import Any, Callable

from hani2.support_agent.capabilities import Capability

__all__ = ["ToolDispatcher", "make_function_schema"]


def _log_agent_action(session_state: dict, action: str, detail: str = "") -> None:
    """Attribution: record that the *agent* (not the human) took an action."""
    try:
        from hani2.events import EventType, log_event

        s = session_state.get("_session")
        log_event(
            getattr(s, "sid", None),
            EventType.SUPPORT_AGENT,
            user=session_state.get("user"),
            component="SupportAgent",
            action=action,
            value={"actor": "agent", "detail": detail},
        )
        if s is not None:
            s.ss["support_agent_used"] = True
    except Exception:
        pass


class ToolDispatcher:
    def __init__(self, runtime):
        self.runtime = runtime
        # name -> (required Capability or None, handler, schema dict)
        self._registry: dict[str, tuple[Capability | None, Callable, Callable]] = {
            "send_toast": (Capability.TOAST, self._send_toast, self._schema_send_toast),
            "show_on_board": (None, self._show_on_board, self._schema_show_on_board),
            "pin_message": (Capability.PIN, self._pin_message, self._schema_pin_message),
            "unpin_message": (Capability.PIN, self._unpin_message, self._schema_unpin_message),
            "list_tools": (None, self._list_tools, self._schema_list_tools),
            "set_tool_enabled": (
                Capability.TOOL_ENABLE,
                self._set_tool_enabled,
                self._schema_set_tool_enabled,
            ),
            "set_tool_visible": (
                Capability.TOOL_VISIBILITY,
                self._set_tool_visible,
                self._schema_set_tool_visible,
            ),
            "message_user": (Capability.CHAT, self._message_user, self._schema_message_user),
            "ask_user": (Capability.CHAT, self._ask_user, self._schema_ask_user),
            "move_tool": (Capability.TOOL_ORDER, self._move_tool, self._schema_move_tool),
            "get_negotiation_state": (
                None,
                self._get_negotiation_state,
                self._schema_get_negotiation_state,
            ),
            "set_offer": (Capability.FILL_OFFER, self._set_offer, self._schema_set_offer),
            "set_message_text": (
                Capability.FILL_TEXT,
                self._set_message_text,
                self._schema_set_message_text,
            ),
            "submit_counter_offer": (
                Capability.SUBMIT_COUNTER,
                self._submit_counter_offer,
                self._schema_submit_counter_offer,
            ),
            "accept_offer": (Capability.ACCEPT, self._accept_offer, self._schema_accept_offer),
            "end_negotiation": (Capability.END, self._end_negotiation, self._schema_end_negotiation),
            "focus_tool": (Capability.TOOL_VISIBILITY, self._focus_tool, self._schema_focus_tool),
            "highlight": (Capability.HIGHLIGHT, self._highlight, self._schema_highlight),
            "clear_highlights": (Capability.HIGHLIGHT, self._clear_highlights, self._schema_clear_highlights),
            "annotate": (Capability.ANNOTATE, self._annotate, self._schema_annotate),
            "set_layout": (Capability.LAYOUT, self._set_layout, self._schema_set_layout),
            "set_presentation": (Capability.PRESENTATION, self._set_presentation, self._schema_set_presentation),
            "set_offer_display": (Capability.OFFER_DISPLAY, self._set_offer_display, self._schema_set_offer_display),
            "set_interface": (Capability.INTERFACE, self._set_interface, self._schema_set_interface),
            "set_opponent_estimate": (Capability.OPPONENT_MODEL, self._set_opponent_estimate,
                                      self._schema_set_opponent_estimate),
            "show_panel": (Capability.PANELS, self._show_panel, self._schema_show_panel),
            "close_panel": (Capability.PANELS, self._close_panel, self._schema_close_panel),
            "read_tool": (Capability.TOOL_USE, self._read_tool, self._schema_read_tool),
            "use_tool": (Capability.TOOL_USE, self._use_tool, self._schema_use_tool),
            "add_tool": (Capability.TOOL_ADD, self._add_tool, self._schema_add_tool),
            "remove_tool": (Capability.TOOL_ADD, self._remove_tool, self._schema_remove_tool),
            "get_private_information": (Capability.PRIVATE_INFO, self._get_private_information,
                                        self._schema_get_private_information),
            "show_past_negotiation": (Capability.PRIVATE_INFO, self._show_past_negotiation,
                                      self._schema_show_past_negotiation),
            "get_opponent_utility": (Capability.OPPONENT_UTILITY, self._get_opponent_utility,
                                     self._schema_get_opponent_utility),
            # model_choice or own_models (the runtime checks which sequences it may use)
            "list_model_sequences": (None, self._list_model_sequences, self._schema_list_model_sequences),
            "use_model_sequence": (None, self._use_model_sequence, self._schema_use_model_sequence),
            "define_model_sequence": (Capability.OWN_MODELS, self._define_model_sequence,
                                      self._schema_define_model_sequence),
        }
        self.register_extra_tools()

    def register_extra_tools(self) -> None:
        """Hook for ToolDispatcher subclasses to add custom functions.

        Add entries to ``self._registry`` here::

            self._registry["my_tool"] = (None, self._my_tool, self._schema_my_tool)

        Use a ``Capability`` (or ``None`` for ungated read-only helpers) as the
        first element. Build schemas with the module-level ``_fn`` helper.
        """

    def register(self, name, handler, schema, capability=None) -> None:
        """Convenience for subclasses to register a custom tool."""
        self._registry[name] = (capability, handler, schema)

    # ------------------------------------------------------------------ #
    @property
    def caps(self):
        return self.runtime.capabilities

    @property
    def ss(self) -> dict:
        return self.runtime.session_state

    def _actions(self) -> dict | None:
        return self.ss.get("actions")

    def _effective_names(self) -> list[str]:
        names = []
        for name, (cap, _, _) in self._registry.items():
            if cap is None:
                # Read-only helpers: offer them whenever the relevant family is granted.
                if name == "list_tools" and not (
                    self.caps.has(Capability.TOOL_ENABLE)
                    or self.caps.has(Capability.TOOL_VISIBILITY)
                    or self.caps.has(Capability.TOOL_ORDER)
                    or self.caps.has(Capability.TOOL_ADD)
                    or self.caps.has(Capability.TOOL_USE)
                ):
                    continue
                if name in ("list_model_sequences", "use_model_sequence") and not (
                    self.caps.has(Capability.MODEL_CHOICE) or self.caps.has(Capability.OWN_MODELS)
                ):
                    continue
                names.append(name)
            elif self.caps.has(cap):
                if cap == Capability.PRIVATE_INFO and not self._information_split():
                    continue  # nothing private this round
                if name == "show_past_negotiation" and not self._holds_past():
                    continue
                names.append(name)
        return names

    def _human_only(self, action: str) -> bool:
        """Whether only the participant may take ``action`` (the autopilot, which the
        participant handed control to, may)."""
        from hani2.recording.recorder import current_actor

        st = self._information()
        if st is None or current_actor() == "autopilot":
            return False
        # sending or accepting decides every issue, so a human-only issue makes them the participant's too
        return action in st.human_only_actions or (action in ("send", "accept") and bool(st.human_only_issues))

    def _strip_human_only(self, outcome: Any) -> tuple[Any, list[str]]:
        """``outcome`` without the issues only the participant may set, and those issue names."""
        st = self._information()
        sess = self.ss.get("_session")
        if st is None or not st.human_only_issues or not isinstance(outcome, dict) or sess is None:
            return outcome, []
        allowed, kept = {}, []
        for k, v in outcome.items():
            issue = sess._resolve_issue(k)
            if issue is not None and st.human_only_issue(issue.name):
                kept.append(issue.name)
            else:
                allowed[k] = v
        return allowed, kept

    def _information(self):
        sess = self.ss.get("_session")
        return getattr(sess, "information", None)

    def _information_split(self) -> bool:
        st = self._information()
        return bool(st is not None and st.split)

    def _holds_past(self) -> bool:
        st = self._information()
        return bool(st is not None and st.assistant_past)

    def schemas(self) -> list[dict]:
        return [self._registry[n][2]() for n in self._effective_names()]

    def execute(self, name: str, args: dict) -> dict:
        entry = self._registry.get(name)
        if entry is None:
            return {"ok": False, "error": f"unknown function '{name}'"}
        cap, handler, _ = entry
        if cap is not None and not self.caps.has(cap):
            result = {"ok": False, "error": f"capability '{cap.value}' is not enabled"}
            self._record(name, args, result, 0.0)
            return result
        import time as _time

        t0 = _time.perf_counter()
        try:
            result = handler(args or {})
        except Exception as e:
            self._record(name, args, {"ok": False, "error": str(e)}, _time.perf_counter() - t0)
            raise
        self._record(name, args, result, _time.perf_counter() - t0)
        return result

    def _record(self, name: str, args: dict, result: Any, latency: float) -> None:
        """Put the call in the session's recording (see :mod:`hani2.recording`)."""
        s = self.ss.get("_session")
        r = getattr(s, "recorder", None)
        if r is not None:
            r.function_call(name, args or {}, result, latency)

    # ------------------------------------------------------------------ #
    # Toasts                                                              #
    # ------------------------------------------------------------------ #
    def _send_toast(self, args: dict) -> dict:
        message = str(args.get("message", "")).strip()
        if not message:
            return {"ok": False, "error": "message is required"}
        level = str(args.get("level", "info")).lower()
        ok = self.runtime.toast(message, level)
        _log_agent_action(self.ss, "send_toast", message[:80])
        return {"ok": ok}

    def _schema_send_toast(self) -> dict:
        return _fn(
            "send_toast",
            "Show the human a toast notification.",
            {
                "message": {"type": "string", "description": "Text to display."},
                "level": {
                    "type": "string",
                    "enum": ["info", "success", "warning", "error"],
                    "description": "Severity / colour of the toast.",
                },
            },
            ["message"],
        )

    def _show_on_board(self, args: dict) -> dict:
        text = str(args.get("content", "")).strip()
        if not text:
            return {"ok": False, "error": "content is required"}
        ok = self.runtime.show_on_board(text, append=bool(args.get("append", False)))
        _log_agent_action(self.ss, "show_on_board", text[:80])
        return {"ok": ok}

    def _schema_show_on_board(self) -> dict:
        return _fn(
            "show_on_board",
            "Write to the always-visible status board: a full-width strip below the "
            "other panels that you write into directly. Use it for anything the human "
            "should see persistently: your current recommendation, a summary, a table, "
            "or a warning. Content may be markdown OR raw HTML.",
            {
                "content": {"type": "string", "description": "Markdown or HTML to display."},
                "append": {
                    "type": "boolean",
                    "description": "Append below existing content instead of replacing.",
                },
            },
            ["content"],
        )

    # ------------------------------------------------------------------ #
    # Pinned messages                                                     #
    # ------------------------------------------------------------------ #
    def _pin_message(self, args: dict) -> dict:
        r = self.runtime.pin_message(
            str(args.get("text", "")),
            position=str(args.get("position", "top")).lower(),
            level=str(args.get("level", "info")).lower(),
            pin_id=(str(args["id"]) if args.get("id") else None),
            dismissible=bool(args.get("dismissible", True)),
        )
        _log_agent_action(self.ss, "pin_message", str(args.get("text", ""))[:80])
        return r

    def _schema_pin_message(self) -> dict:
        return _fn(
            "pin_message",
            "Pin a short message (markdown) at the top or bottom of the human's screen. It stays "
            "until you unpin it (or the human dismisses it) and the rest of the screen shrinks to "
            "make room, so nothing is covered. Use it for something the human must keep in view "
            "(a deadline, a warning, your key advice). Give an id to update the same pin later.",
            {
                "text": {"type": "string", "description": "Markdown to show."},
                "position": {"type": "string", "enum": ["top", "bottom"], "description": "Above or below the negotiation (default top)."},
                "level": {"type": "string", "enum": ["info", "success", "warning", "error"]},
                "id": {"type": "string", "description": "Optional id; reusing it replaces that pin."},
                "dismissible": {"type": "boolean", "description": "Whether the human may close it (default true)."},
            },
            ["text"],
        )

    def _unpin_message(self, args: dict) -> dict:
        r = self.runtime.unpin_message(str(args["id"]) if args.get("id") else None)
        _log_agent_action(self.ss, "unpin_message", str(args.get("id") or "all"))
        return r

    def _schema_unpin_message(self) -> dict:
        return _fn(
            "unpin_message",
            "Remove a pinned message by its id, or every pinned message when no id is given.",
            {"id": {"type": "string", "description": "The pin to remove (omit for all)."}},
            [],
        )

    # ------------------------------------------------------------------ #
    # Talking to the human at any moment                                  #
    # ------------------------------------------------------------------ #
    def _message_user(self, args: dict) -> dict:
        text = str(args.get("text", "")).strip()
        if not text:
            return {"ok": False, "error": "text is required"}
        channel = str(args.get("channel", "chat")).lower()
        if channel not in ("chat", "toast", "board"):
            channel = "chat"
        self.runtime.message_user(text, channel=channel)
        _log_agent_action(self.ss, "message_user", f"{channel}: {text[:80]}")
        return {"ok": True, "channel": channel}

    def _schema_message_user(self) -> dict:
        return _fn(
            "message_user",
            "Send the human a message right now, even in the middle of your work. "
            "channel: 'chat' (default), 'toast' (a pop-up) or 'board' (the status strip).",
            {
                "text": {"type": "string", "description": "What to tell the human."},
                "channel": {"type": "string", "enum": ["chat", "toast", "board"]},
            },
            ["text"],
        )

    def _ask_user(self, args: dict) -> dict:
        question = str(args.get("question", "")).strip()
        if not question:
            return {"ok": False, "error": "question is required"}
        options = [str(o) for o in (args.get("options") or []) if str(o).strip()]
        answer = self.runtime.ask_user(question, options or None)
        _log_agent_action(self.ss, "ask_user", question[:80])
        if answer is None:
            return {"ok": False, "error": "the human did not answer (or cannot be asked now)"}
        return {"ok": True, "answer": answer}

    def _schema_ask_user(self) -> dict:
        return _fn(
            "ask_user",
            "Ask the human a question and wait for the answer (use sparingly, only when "
            "you truly need their preference or a decision). Optionally offer short "
            "answer buttons; the human can also type a free-text reply.",
            {
                "question": {"type": "string"},
                "options": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional short choices shown as buttons.",
                },
            },
            ["question"],
        )

    # ------------------------------------------------------------------ #
    # Tool control                                                        #
    # ------------------------------------------------------------------ #
    def _controller(self):
        return self.ss.get("tool_controller")

    def _list_tools(self, args: dict) -> dict:
        ctrl = self._controller()
        if ctrl is None:
            return {"ok": False, "error": "tool controller unavailable"}
        out = {"ok": True, "tools": self.runtime.run_on_doc(ctrl.list_tools)}
        if self.runtime.capabilities.has(Capability.TOOL_ADD):
            try:
                out["can_add"] = self.runtime.available_tools()
            except Exception as e:  # noqa: BLE001
                out["can_add_error"] = str(e)
        return out

    def _schema_list_tools(self) -> dict:
        return _fn(
            "list_tools",
            "List the participant's tools (name, description, pane, visible, enabled) and, under can_add, "
            "tools you may add to their screen with add_tool.",
            {},
            [],
        )

    def _read_tool(self, args: dict) -> dict:
        return self.runtime.read_tool(str(args.get("name", "")))

    def _schema_read_tool(self) -> dict:
        return _fn(
            "read_tool",
            "Read what a tool currently shows (numbers, tables, chart summaries) and which inputs and "
            "buttons it has. Use it to learn what any tool can tell or do for the participant.",
            {"name": {"type": "string", "description": "Tool tab name."}},
            ["name"],
        )

    def _use_tool(self, args: dict) -> dict:
        row = args.get("row")
        return self.runtime.use_tool(
            str(args.get("name", "")),
            inputs=args.get("inputs") or None,
            action=args.get("action") or None,
            payload=args.get("payload") or None,
            row=int(row) if row is not None else None,
        )

    def _schema_use_tool(self) -> dict:
        return _fn(
            "use_tool",
            "Operate a tool like the participant would: set inputs (by the input names read_tool lists), "
            "then optionally press a button (its action) or pick a table row (the table's action and row "
            "index). Returns what the tool shows afterwards. Changes to the offer go through your own "
            "permissions.",
            {
                "name": {"type": "string", "description": "Tool tab name."},
                "inputs": {"type": "object", "description": "Input name → new value.", "additionalProperties": True},
                "action": {"type": "string", "description": "Button action or table selection action."},
                "row": {"type": "integer", "description": "Row index for a table selection action."},
                "payload": {"type": "object", "description": "Extra data for the action (rarely needed).",
                            "additionalProperties": True},
            },
            ["name"],
        )

    def _add_tool(self, args: dict) -> dict:
        return self.runtime.add_tool(
            str(args.get("name", "")),
            pane=args.get("pane") or None,
            focus=bool(args.get("focus", True)),
        )

    def _schema_add_tool(self) -> dict:
        return _fn(
            "add_tool",
            "Add a tool to the participant's screen now, by name from list_tools → can_add. It stays for "
            "the rest of the session. Add a tool when it helps with what the participant is doing.",
            {
                "name": {"type": "string", "description": "Name from can_add."},
                "pane": {"type": "string", "enum": ["upper", "lower", "side"],
                         "description": "Where to put it (default: the tool's own pane)."},
                "focus": {"type": "boolean", "description": "Bring it to the front (default true)."},
            },
            ["name"],
        )

    def _remove_tool(self, args: dict) -> dict:
        return self.runtime.remove_tool(str(args.get("name", "")))

    def _schema_remove_tool(self) -> dict:
        return _fn("remove_tool", "Remove a tool that was added during the session.",
                   {"name": {"type": "string", "description": "Tool tab name."}}, ["name"])

    def _set_tool_enabled(self, args: dict) -> dict:
        ctrl = self._controller()
        if ctrl is None:
            return {"ok": False, "error": "tool controller unavailable"}
        name, enabled = args.get("name"), bool(args.get("enabled", True))
        res = self.runtime.run_on_doc(
            lambda: ctrl.set_tool_enabled(name, enabled, allow_permanent=True)
        )
        _log_agent_action(self.ss, "set_tool_enabled", f"{name}={enabled}")
        return res

    def _schema_set_tool_enabled(self) -> dict:
        return _fn(
            "set_tool_enabled",
            "Enable or disable a tool (the tab stays, content is shown/hidden).",
            {
                "name": {"type": "string", "description": "Tool tab name."},
                "enabled": {"type": "boolean"},
            },
            ["name", "enabled"],
        )

    def _set_tool_visible(self, args: dict) -> dict:
        ctrl = self._controller()
        if ctrl is None:
            return {"ok": False, "error": "tool controller unavailable"}
        name, visible = args.get("name"), bool(args.get("visible", True))
        res = self.runtime.run_on_doc(
            lambda: ctrl.set_tool_visible(name, visible, allow_permanent=True)
        )
        _log_agent_action(self.ss, "set_tool_visible", f"{name}={visible}")
        return res

    def _schema_set_tool_visible(self) -> dict:
        return _fn(
            "set_tool_visible",
            "Show or hide a tool's tab entirely.",
            {
                "name": {"type": "string", "description": "Tool tab name."},
                "visible": {"type": "boolean"},
            },
            ["name", "visible"],
        )

    def _move_tool(self, args: dict) -> dict:
        ctrl = self._controller()
        if ctrl is None:
            return {"ok": False, "error": "tool controller unavailable"}
        name = args.get("name")
        position = args.get("position")
        pane = args.get("pane")
        res = self.runtime.run_on_doc(lambda: ctrl.move_tool(name, position=position, pane=pane))
        _log_agent_action(self.ss, "move_tool", f"{name}->pane={pane},pos={position}")
        return res

    def _schema_move_tool(self) -> dict:
        return _fn(
            "move_tool",
            "Reorder a tool within its pane and/or move it to another pane.",
            {
                "name": {"type": "string", "description": "Tool tab name."},
                "position": {"type": "integer", "description": "0-based index within the target pane."},
                "pane": {
                    "type": "string",
                    "enum": ["upper", "lower", "side"],
                    "description": "Target pane (omit to keep current pane).",
                },
            },
            ["name"],
        )

    # ------------------------------------------------------------------ #
    # Negotiation context (read-only)                                     #
    # ------------------------------------------------------------------ #
    def _get_negotiation_state(self, args: dict) -> dict:
        actions = self._actions()
        if actions is None:
            return {"ok": False, "error": "no active negotiation"}
        return {"ok": True, **self.runtime.context()}

    def _get_private_information(self, args: dict) -> dict:
        return self.runtime.private_information()

    def _schema_get_private_information(self) -> dict:
        return _fn(
            "get_private_information",
            "What only you know in this negotiation (the participant does not see it unless you tell them): "
            "your part of the participant's preferences, their value on disagreement when you have it, summaries "
            "of the past negotiations you hold, market research about the opponent, and who holds what.",
            {},
            [],
        )

    def _show_past_negotiation(self, args: dict) -> dict:
        return self.runtime.past_negotiation(str(args.get("id") or ""))

    def _schema_show_past_negotiation(self) -> dict:
        return _fn(
            "show_past_negotiation",
            "Every offer of one past negotiation you hold (in this scenario, with similar parties): who offered what, "
            "and how it ended.",
            {"id": {"type": "string", "description": "The negotiation's id, e.g. P2 (from get_private_information)"}},
            ["id"],
        )

    def _schema_get_negotiation_state(self) -> dict:
        return _fn(
            "get_negotiation_state",
            "Get the current negotiation state: issues, the opponent's offer on the table, "
            "the human's current draft offer and message, utilities, and recent history.",
            {},
            [],
        )

    def _get_opponent_utility(self, args: dict) -> dict:
        offer = args.get("offer")
        return self.runtime.opponent_view(offer if isinstance(offer, dict) else None)

    def _schema_get_opponent_utility(self) -> dict:
        return _fn(
            "get_opponent_utility",
            "The opponent's private preferences (issue weights and option values, or its best outcomes), its "
            "reserved value and its utility of the offers on the table and in the history. With 'offer', also "
            "the opponent's and the human's utility of that offer.",
            {"offer": {"type": "object", "description": "Optional map of issue name to value to score."}},
            [],
        )

    # ------------------------------------------------------------------ #
    # Model sequences                                                     #
    # ------------------------------------------------------------------ #
    def _list_model_sequences(self, args: dict) -> dict:
        seqs = [{"name": d["name"], "description": d.get("description", ""),
                 "models": [f"{e.get('connection') or e.get('provider')}:{e.get('model')}" for e in d.get("entries", [])]}
                for d in self.runtime.model_sequences()]
        return {"ok": True, "current": self.runtime.model_sequence or "assistant", "sequences": seqs}

    def _schema_list_model_sequences(self) -> dict:
        return _fn("list_model_sequences",
                   "List the named language-model sequences you may switch to (e.g. tiny, offline, small, "
                   "medium, large) and the one you use now.", {}, [])

    def _use_model_sequence(self, args: dict) -> dict:
        return self.runtime.use_model_sequence(str(args.get("name") or ""))

    def _schema_use_model_sequence(self) -> dict:
        return _fn("use_model_sequence",
                   "Use another named language-model sequence for your next replies (from list_model_sequences; "
                   "'assistant' goes back to the default). Prefer small models for simple requests.",
                   {"name": {"type": "string", "description": "The sequence name."}}, ["name"])

    def _define_model_sequence(self, args: dict) -> dict:
        return self.runtime.define_model_sequence(str(args.get("name") or ""), args.get("entries") or [],
                                                  str(args.get("description") or ""))

    def _schema_define_model_sequence(self) -> dict:
        return _fn("define_model_sequence",
                   "Define your own language-model sequence for this session (tried in order). Each entry is "
                   "an object with provider, model, params (temperature, effort, thinking, ...) and api_key and/or "
                   "api_base (your own key or server; the study's models are used through its sequences).",
                   {"name": {"type": "string", "description": "A new sequence name."},
                    "entries": {"type": "array", "items": {}, "description": "The entries, first choice first."},
                    "description": {"type": "string", "description": "What the sequence is for."}},
                   ["name", "entries"])

    # ------------------------------------------------------------------ #
    # Action panel                                                        #
    # ------------------------------------------------------------------ #
    def _require_turn(self, actions: dict) -> dict | None:
        if not actions["can_act"]():
            return {"ok": False, "error": "it is not the human's turn to act right now"}
        return None

    def _set_offer(self, args: dict) -> dict:
        actions = self._actions()
        if actions is None:
            return {"ok": False, "error": "no active negotiation"}
        outcome = args.get("outcome")
        if not isinstance(outcome, dict):
            return {"ok": False, "error": "outcome must be an object of issue_name -> value"}
        allowed, kept = self._strip_human_only(outcome)
        res = self.runtime.run_on_doc(lambda: actions["set_offer"](allowed))
        _log_agent_action(self.ss, "set_offer", str(outcome)[:120])
        if kept and isinstance(res, dict):
            res = {**res, "human_only": sorted(set(kept) | set(res.get("human_only") or [])),
                   "note": f"only the participant may set {', '.join(kept)}; suggest a value to them instead "
                           "(their current values were kept)"}
        return res

    def _schema_set_offer(self) -> dict:
        return _fn(
            "set_offer",
            "Fill the human's offer fields with the given outcome (does not submit).",
            {
                "outcome": {
                    "type": "object",
                    "description": "Map of issue name to chosen value. Use exact issue names "
                    "and valid values (call get_negotiation_state first).",
                }
            },
            ["outcome"],
        )

    def _set_message_text(self, args: dict) -> dict:
        actions = self._actions()
        if actions is None:
            return {"ok": False, "error": "no active negotiation"}
        text = str(args.get("text", ""))
        res = self.runtime.run_on_doc(lambda: actions["set_text"](text))
        _log_agent_action(self.ss, "set_message_text", text[:80])
        return res

    def _schema_set_message_text(self) -> dict:
        return _fn(
            "set_message_text",
            "Write the message that will be sent to the opponent (does not submit). "
            "NEVER reveal the human's utility values; keep it qualitative.",
            {"text": {"type": "string"}},
            ["text"],
        )

    def _submit_counter_offer(self, args: dict) -> dict:
        actions = self._actions()
        if actions is None:
            return {"ok": False, "error": "no active negotiation"}
        if (err := self._require_turn(actions)) is not None:
            return err
        outcome = args.get("outcome")
        message = args.get("message")
        human_only = self._human_only("send")
        execute = self.caps.autonomy_allows_execute(Capability.SUBMIT_COUNTER) and not human_only
        kept: list = []

        def _do():
            if isinstance(outcome, dict):
                allowed, stripped = self._strip_human_only(outcome)
                kept.extend(stripped)
                res = actions["set_offer"](allowed) or {}
                kept.extend(x for x in res.get("human_only") or [] if x not in kept)
                if res.get("ok") is False:  # unknown issue or invalid value: never send the old draft instead
                    return {"ok": False, "error": res.get("error") or "the offer was not set: fix these issues",
                            "unrecognised": res.get("unrecognised") or []}
            if message is not None:
                actions["set_text"](str(message))
            if not execute:
                actions["highlight"]("reject")
            return execute

        executed = self.runtime.run_on_doc(_do)
        if isinstance(executed, dict):
            return executed
        if executed:  # outside run_on_doc: sending may call the language model (auto_extract / auto_generate)
            sent = actions["reject_counter"]()
            if isinstance(sent, dict) and not sent.get("ok"):
                return {"ok": False, "error": sent.get("error") or "the counter-offer was not sent"}
        _log_agent_action(
            self.ss, "submit_counter_offer" if executed else "recommend_counter_offer", str(outcome)[:120]
        )
        extra = {"human_only": kept, "note_human_only": f"only the participant may set {', '.join(kept)}; "
                                                         "their current values were kept"} if kept else {}
        if human_only:
            return {"ok": True, "submitted": False, **extra,
                    "note": "Only the participant may send offers (or set some issues) in this negotiation: "
                            "filled the offer/message and highlighted the Send button for them."}
        if executed:
            return {"ok": True, "submitted": True, **extra}
        return {**extra,
            "ok": True,
            "submitted": False,
            "note": "Suggest mode: filled the offer/message and highlighted the Send button "
            "for the human to confirm.",
        }

    def _schema_submit_counter_offer(self) -> dict:
        execute = self.caps.autonomy_allows_execute(Capability.SUBMIT_COUNTER)
        verb = (
            "Submit a counter-offer (reject the opponent's offer and send this outcome + message)."
            if execute
            else "Prepare a counter-offer: fills the offer fields and message and highlights the "
            "Send button. In the current mode this does NOT auto-submit; the human must confirm."
        )
        return _fn(
            "submit_counter_offer",
            verb,
            {
                "outcome": {"type": "object", "description": "Issue name -> value."},
                "message": {"type": "string", "description": "Message to the opponent (no ufun leaks)."},
            },
            [],
        )

    def _accept_offer(self, args: dict) -> dict:
        return self._irreversible(Capability.ACCEPT, "accept")

    def _schema_accept_offer(self) -> dict:
        return self._schema_irreversible("accept_offer", Capability.ACCEPT, "Accept the opponent's current offer.")

    def _end_negotiation(self, args: dict) -> dict:
        return self._irreversible(Capability.END, "end")

    def _schema_end_negotiation(self) -> dict:
        return self._schema_irreversible(
            "end_negotiation", Capability.END, "End the negotiation with no agreement."
        )

    def _irreversible(self, cap: Capability, action_key: str) -> dict:
        actions = self._actions()
        if actions is None:
            return {"ok": False, "error": "no active negotiation"}
        if (err := self._require_turn(actions)) is not None:
            return err
        human_only = self._human_only({"accept": "accept", "end": "end"}.get(action_key, action_key))
        execute = self.caps.autonomy_allows_execute(cap) and not human_only  # FULL only
        confirm = self.caps.autonomy_allows_confirm(cap) and not human_only  # SEMI+

        if execute:
            done = self.runtime.run_on_doc(lambda: actions[action_key](confirm=False))
            if isinstance(done, dict) or not done:  # a gate refusal, or the session refused (no offer, not the turn)
                return done if isinstance(done, dict) else {"ok": False, "error": f"could not {action_key} now"}
            _log_agent_action(self.ss, f"{action_key}_executed")
            return {"ok": True, "executed": True}
        if confirm:
            self.runtime.run_on_doc(lambda: actions[action_key](confirm=True))
            _log_agent_action(self.ss, f"{action_key}_confirm_requested")
            return {"ok": True, "executed": False, "note": "Asked the human to confirm via dialog."}
        # SUGGEST: only highlight the button.
        self.runtime.run_on_doc(lambda: actions["highlight"](action_key))
        _log_agent_action(self.ss, f"recommend_{action_key}")
        if human_only:
            return {"ok": True, "executed": False,
                    "note": f"Only the participant may {action_key} in this negotiation: highlighted the button "
                            "for them; tell them why you recommend it."}
        return {
            "ok": True,
            "executed": False,
            "note": "Suggest mode: highlighted the button for the human to press.",
        }

    def _schema_irreversible(self, name: str, cap: Capability, base: str) -> dict:
        if self.caps.autonomy_allows_execute(cap):
            desc = base + " This executes immediately."
        elif self.caps.autonomy_allows_confirm(cap):
            desc = base + " This pops a confirmation dialog for the human to approve."
        else:
            desc = base + " In the current mode this only highlights the button for the human."
        return _fn(name, desc, {}, [])


    # ------------------------------------------------------------------ #
    # Interface control: focus, highlight, annotate, layout, panels       #
    # ------------------------------------------------------------------ #
    def _session(self):
        return self.ss.get("_session")

    def _focus_tool(self, args: dict) -> dict:
        ctrl = self._controller()
        name = args.get("name")
        res = self.runtime.run_on_doc(lambda: ctrl.focus_tool(name))
        _log_agent_action(self.ss, "focus_tool", str(name))
        return res

    def _schema_focus_tool(self) -> dict:
        return _fn("focus_tool", "Bring a tool's tab to the front (showing and enabling it).",
                   {"name": {"type": "string", "description": "Tool tab name."}}, ["name"])

    def _highlight(self, args: dict) -> dict:
        target = str(args.get("target", "")).strip()
        if not target:
            return {"ok": False, "error": "target is required"}
        res = self._session().highlight(target, message=args.get("message"), style=args.get("style") or "pulse",
                                        duration=args.get("duration"))
        _log_agent_action(self.ss, "highlight", target)
        return res

    def _schema_highlight(self) -> dict:
        return _fn(
            "highlight",
            "Spotlight a part of the interface, optionally with a short callout note. Targets: "
            "'accept', 'reject', 'end', 'send', 'offer' (the counter-offer editor), 'message', "
            "'partner_offer', 'history', 'history:last', 'timer', 'issue:<issue name>', "
            "'tool:<tool name>', 'pane:upper|lower|side'.",
            {
                "target": {"type": "string"},
                "message": {"type": "string", "description": "Optional short callout text."},
                "style": {"type": "string", "enum": ["pulse", "glow", "spotlight"],
                          "description": "pulse (default), glow, or spotlight (dims everything else)."},
                "duration": {"type": "number", "description": "Seconds before it fades (omit = until the next turn)."},
            },
            ["target"],
        )

    def _clear_highlights(self, args: dict) -> dict:
        return self._session().clear_highlights(args.get("target"))

    def _schema_clear_highlights(self) -> dict:
        return _fn("clear_highlights", "Remove highlights (all, or only the given target).",
                   {"target": {"type": "string"}}, [])

    def _annotate(self, args: dict) -> dict:
        target = str(args.get("target", "")).strip()
        if not target:
            return {"ok": False, "error": "target is required"}
        text = args.get("text")
        res = self._session().annotate(target, text, kind=str(args.get("kind") or "info"))
        _log_agent_action(self.ss, "annotate", f"{target}: {str(text)[:60]}")
        return res

    def _schema_annotate(self) -> dict:
        return _fn(
            "annotate",
            "Attach a short note to an interface element, e.g. 'issue:Price' -> 'Opponent keeps "
            "conceding here'. Same targets as highlight. Omit text to remove the note.",
            {
                "target": {"type": "string"},
                "text": {"type": "string"},
                "kind": {"type": "string", "enum": ["info", "success", "warning", "tip"]},
            },
            ["target"],
        )

    def _set_layout(self, args: dict) -> dict:
        changes = {k: args[k] for k in ("view", "sizes", "collapsed") if k in args}
        res = self._session().set_layout(**changes)
        _log_agent_action(self.ss, "set_layout", str(changes)[:120])
        return res

    def _schema_set_layout(self) -> dict:
        return _fn(
            "set_layout",
            "Rearrange the interface. view: 'full' (all panes), 'simple' (history, offer and one "
            "tools area), 'focus' (only the negotiation; tools come back when one is opened) or "
            "'bare' (no tools at all: the history, the offer area and you). Switch to 'simple' or "
            "'full' when the participant wants more, to 'focus' or 'bare' when they want less. "
            "The study may fix the view; the result then says so. collapsed: regions to "
            "collapse, any of 'tools', 'history', 'side'. sizes: fractions such as "
            "{'tools': 0.4} (width share of the tools column).",
            {
                "view": {"type": "string", "enum": ["full", "simple", "focus", "bare"]},
                "collapsed": {"type": "array", "items": {"type": "string"}},
                "sizes": {"type": "object"},
            },
            [],
        )

    def _set_offer_display(self, args: dict) -> dict:
        keys = ("offer_template", "issue_format", "value_labels", "issue_widget", "offer_display", "reset")
        changes = {k: args[k] for k in keys if k in args and args[k] is not None}
        res = self._session().set_offer_display(**changes)
        _log_agent_action(self.ss, "set_offer_display", str(changes)[:160])
        return res

    def _schema_set_offer_display(self) -> dict:
        return _fn(
            "set_offer_display",
            "Change how offers are shown everywhere (history, the offer on the table, the result, "
            "notifications), over the scenario's defaults, for this session. offer_template: one "
            "sentence with {Issue} placeholders, e.g. '{Quantity} units at {Price} each' ('' drops "
            "it). issue_format: issue -> Python format for one value, e.g. {'Price': '${:,.2f}'}. "
            "value_labels: issue -> {value: shown name}. issue_widget: issue -> 'buttons', 'select', "
            "'slider' or 'number' (the control in the offer editor). offer_display: 'text' "
            "(sentences) or 'table' (issue chips). reset: true drops every change, or a list of "
            "keys to drop. Values themselves never change, only how they read.",
            {
                "offer_template": {"type": "string"},
                "issue_format": {"type": "object"},
                "value_labels": {"type": "object"},
                "issue_widget": {"type": "object"},
                "offer_display": {"type": "string", "enum": ["text", "table"]},
                "reset": {"anyOf": [{"type": "boolean"}, {"type": "array", "items": {"type": "string"}}]},
            },
            [],
        )

    def _set_interface(self, args: dict) -> dict:
        prefs = args.get("prefs") if isinstance(args.get("prefs"), dict) else None
        css = args.get("custom_css")
        res = self._session().set_interface(prefs=prefs, custom_css=css if isinstance(css, str) else None)
        _log_agent_action(self.ss, "set_interface",
                          str({**({"prefs": prefs} if prefs else {}),
                               **({"custom_css": f"{len(css)} chars"} if isinstance(css, str) else {})})[:160])
        return res

    def _schema_set_interface(self) -> dict:
        return _fn(
            "set_interface",
            "Adjust the participant's interface when they ask. prefs: their display settings, any "
            "of show_history (false: only the latest offer), show_human_offers, color_utility_by_issue "
            "(utility bars split into one coloured segment per issue), last_offer_on_top, "
            "offer_panel_always_visible, offer_display ('text' | 'table'), font_scale (0.7-1.6), "
            "show_scenario_picture, scenario_picture_style ('small' | 'large' | 'watermark'). "
            "custom_css: a style sheet added to the page (replaces the previous one; '' removes "
            "it): colours, spacing, fonts, sizes, hiding decorations. Target stable hooks such as "
            "[data-region=header], [data-region=dock] (the offer area), [data-region=tools], "
            "[data-anchor=history], [data-anchor=accept], [data-anchor=end], [data-anchor=offer], "
            "[data-anchor='issue:<name>'] and the CSS colour variables on :root (space-separated RGB, e.g. "
            "':root{--you: 200 40 40; --paper: 250 247 240}'; --font-scale scales the text). No url(), @import or !important; the accept, end and "
            "send controls cannot be hidden. Settings the study keeps fixed are refused.",
            {
                "prefs": {"type": "object"},
                "custom_css": {"type": "string"},
            },
            [],
        )

    def _set_presentation(self, args: dict) -> dict:
        style = args.get("style")
        kw = {k: bool(args[k]) for k in ("may_hide", "may_show") if isinstance(args.get(k), bool)}
        place = args.get("place") or None
        res = self._session().set_assistant_presentation(style if style else None, **kw, place=place,
                                                         clear=bool(args.get("reset")))
        _log_agent_action(self.ss, "set_presentation", str({**({"style": style} if style else {}),
                                                            **({"place": place} if place else {}), **kw})[:120])
        return res

    def _schema_set_presentation(self) -> dict:
        return _fn(
            "set_presentation",
            "Choose how you appear: style 'panel' (only the Assistant button in the header opens "
            "your chat), 'persona' (only a character in a corner of the screen) or 'both'. "
            "may_hide: whether the participant may hide the character; may_show: whether they may "
            "bring it back after hiding it. place: where your open chat goes, 'beside' the page "
            "or 'tools' (over the tool area, in the open tool's place; closing it brings the tool "
            "back). reset: true hands the choice back to the default.",
            {
                "style": {"type": "string", "enum": ["panel", "persona", "both"]},
                "place": {"type": "string", "enum": ["beside", "tools"]},
                "may_hide": {"type": "boolean"},
                "may_show": {"type": "boolean"},
                "reset": {"type": "boolean"},
            },
            [],
        )

    def _set_opponent_estimate(self, args: dict) -> dict:
        if args.get("clear"):
            res = self._session().set_opponent_estimate(None, by="assistant")
        else:
            spec = {k: args[k] for k in ("weights", "values", "reserved_value") if k in args}
            if not spec.get("weights") and not spec.get("values"):
                return {"ok": False, "error": "give weights and/or values (or clear: true)"}
            res = self._session().set_opponent_estimate(spec, by="assistant")
        _log_agent_action(self.ss, "set_opponent_estimate", "clear" if args.get("clear") else
                          str({k: args.get(k) for k in ("weights", "reserved_value")})[:120])
        return res

    def _schema_set_opponent_estimate(self) -> dict:
        return _fn(
            "set_opponent_estimate",
            "Share your estimate of the opponent's preferences, for example from its offers. The "
            "participant's Negotiation Plot then shows every deal by their utility and the opponent's "
            "estimated utility, and the Utility-based Selector can show and choose deals by it; both "
            "say clearly it is an estimate. weights: issue name -> importance (any positive numbers; "
            "equal if omitted). values: issue name -> {option: value from 0 to 1}, or 'increasing' / "
            "'decreasing' for numeric issues. reserved_value: the opponent's estimated value of no "
            "deal (0 to 1). Call again to update it, or with clear: true to remove it.",
            {
                "weights": {"type": "object", "additionalProperties": {"type": "number"}},
                "values": {"type": "object"},
                "reserved_value": {"type": "number"},
                "clear": {"type": "boolean"},
            },
            [],
        )

    def _show_panel(self, args: dict) -> dict:
        from hani2.tools import ui

        pid = str(args.get("panel_id") or "assistant")
        comps = []
        if args.get("markdown"):
            comps.append(ui.markdown(str(args["markdown"])))
        rows = args.get("table")
        if isinstance(rows, list) and rows and all(isinstance(r, dict) for r in rows):
            comps.append(ui.table(rows))
        buttons = [b for b in (args.get("buttons") or []) if isinstance(b, (dict, str))]
        if buttons:
            comps.append(ui.row(*[
                ui.button(b if isinstance(b, str) else str(b.get("label", "OK")),
                          action=b if isinstance(b, str) else str(b.get("action") or b.get("label", "ok")),
                          variant="primary" if i == 0 else "secondary")
                for i, b in enumerate(buttons)
            ]))
        res = self._session().show_panel(pid, str(args.get("title") or "Assistant"), comps,
                                         placement=str(args.get("placement") or "assistant"))
        _log_agent_action(self.ss, "show_panel", pid)
        return res

    def _schema_show_panel(self) -> dict:
        return _fn(
            "show_panel",
            "Show a small panel you design: markdown text, an optional table (list of row "
            "objects) and optional buttons. When the human clicks a button you receive a message "
            "'(panel <panel_id>) clicked <action>'. Re-use a panel_id to update it.",
            {
                "panel_id": {"type": "string"},
                "title": {"type": "string"},
                "markdown": {"type": "string"},
                "table": {"type": "array", "items": {"type": "object"}},
                "buttons": {"type": "array", "items": {"type": "object", "properties": {
                    "label": {"type": "string"}, "action": {"type": "string"}}}},
                "placement": {"type": "string", "enum": ["assistant", "side", "modal"],
                              "description": "assistant (in the assistant dock, default), side (above the offer panel) or modal."},
            },
            ["panel_id", "title"],
        )

    def _close_panel(self, args: dict) -> dict:
        return self._session().close_panel(args.get("panel_id"))

    def _schema_close_panel(self) -> dict:
        return _fn("close_panel", "Close a panel you showed (or all panels if panel_id is omitted).",
                   {"panel_id": {"type": "string"}}, [])


def make_function_schema(
    name: str, description: str, properties: dict, required: list[str]
) -> dict:
    """Build an OpenAI/litellm function-tool schema. Public helper for custom
    ToolDispatcher subclasses registering extra tools."""
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        },
    }


# Internal alias used throughout this module.
_fn = make_function_schema
