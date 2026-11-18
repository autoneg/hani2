"""Level 1 - the simplest possible Assistant (no LLM at all)."""

from hani2.support_agent.runtime import SupportAgent


class HelloAgent(SupportAgent):
    def handle_user_message(self, text: str) -> None:
        self.post(f"Hello! You said: {text}")
