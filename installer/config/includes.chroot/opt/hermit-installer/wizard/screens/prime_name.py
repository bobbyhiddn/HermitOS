"""Step 5 — Name your Prime agent."""

import re
from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Button, Static, Label, Input
from textual.containers import Container, Vertical, Horizontal


PRIME_EXAMPLES = [
    "atlas", "nova", "sage", "echo", "forge",
    "lyra", "cipher", "axiom", "herald", "zenith",
]


class PrimeNameScreen(Screen):
    """Step 5 — Name the Prime agent that will manage this system."""

    def compose(self) -> ComposeResult:
        yield Static("  HermitOS Installer", classes="wizard-title")
        yield Static("Step 5 of 11 — Name Your Prime", classes="step-indicator")
        with Container(classes="content-area"):
            with Vertical():
                with Container(classes="info-box"):
                    yield Label("Choose a name for your Prime agent.", classes="bold")
                    yield Label("")
                    yield Label(
                        "Your Prime is the AI agent that manages this HermitOS system. "
                        "Its name becomes the identity that flows through the entire stack:"
                    )
                    yield Label("")
                    yield Label("  • Systemd service:  <name>.service")
                    yield Label("  • Config file:      /etc/hermetic/<name>.yaml")
                    yield Label("  • Database:         <name>")
                    yield Label("  • Gitea repo:       <Name>.Notes  (agent memory)")
                    yield Label("  • Dashboard title:  <Name> Dashboard")
                    yield Label("  • Agent self-identity in its system prompt")
                    yield Label("")
                    yield Label(
                        "Think of it like naming your character — this resonates through everything.",
                        classes="muted"
                    )

                yield Static("")

                with Container(classes="warning-box"):
                    yield Label("Rules: lowercase, letters and numbers only, no spaces.", classes="bold")
                    yield Label("Examples: " + ", ".join(PRIME_EXAMPLES), classes="muted")

                yield Static("")
                yield Label("Prime name:", classes="bold")
                yield Input(
                    placeholder="e.g. nova, atlas, sage...",
                    id="prime_input",
                    max_length=32,
                )
                yield Static("", id="validation_msg")

        with Horizontal(classes="button-bar"):
            yield Button("← Back", id="btn_back", classes="secondary")
            yield Button("Set Name & Continue →", id="btn_next", classes="primary")

    def _validate_name(self, name: str) -> tuple[bool, str]:
        """Validate the prime name."""
        if not name:
            return False, "Name cannot be empty."
        if not re.match(r'^[a-z][a-z0-9]*$', name):
            return False, "Name must be lowercase letters/numbers, starting with a letter."
        if len(name) < 2:
            return False, "Name must be at least 2 characters."
        if len(name) > 32:
            return False, "Name must be 32 characters or fewer."
        # Reserved names that would conflict with system accounts
        reserved = {"root", "daemon", "bin", "sys", "sync", "games", "man",
                    "lp", "mail", "news", "uucp", "proxy", "www-data", "hermit",
                    "hermit-installer"}
        if name in reserved:
            return False, f"'{name}' is a reserved system name. Choose another."
        return True, ""

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn_back":
            self.app.go_back()
        elif event.button.id == "btn_next":
            name = self.query_one("#prime_input", Input).value.strip().lower()
            ok, msg = self._validate_name(name)
            validation = self.query_one("#validation_msg", Static)

            if not ok:
                validation.update(f"✗ {msg}")
                validation.remove_class("success-box")
                validation.add_class("error-box")
                return

            # Save prime name (capitalized form for display)
            self.app.state["prime_name"] = name
            self.app.state["prime_name_display"] = name.capitalize()

            validation.update(f"✓ Prime will be named: {name.capitalize()}")
            validation.remove_class("error-box")
            validation.add_class("success-box")

            self.app.go_next("drive")
