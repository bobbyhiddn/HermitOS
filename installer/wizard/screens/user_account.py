"""Step 8 — User account and hostname configuration."""

import re
from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Button, Static, Label, Input
from textual.containers import Container, Vertical, Horizontal


class UserAccountScreen(Screen):
    """Step 8 — Configure user account, hostname, and system identity."""

    def compose(self) -> ComposeResult:
        prime = self.app.state.get("prime_name_display", "Your Prime")
        yield Static("  HermitOS Installer", classes="wizard-title")
        yield Static("Step 8 of 11 — User Account & System Identity", classes="step-indicator")
        with Container(classes="content-area"):
            with Vertical():
                with Container(classes="info-box"):
                    yield Label("Configure your system identity.", classes="bold")
                    yield Label(
                        "These settings create your user account and identify the system on the network.",
                        classes="muted"
                    )

                yield Static("")

                # Hostname
                yield Label("Hostname (system name on network):", classes="bold")
                yield Input(value="hermit", id="hostname_input", placeholder="e.g. hermit, mypc, tower")
                yield Static("", id="hostname_msg")

                yield Static("")

                # Username
                yield Label("Username:", classes="bold")
                yield Input(
                    value=self.app.state.get("prime_name", "hermit"),
                    id="username_input",
                    placeholder="lowercase letters/numbers"
                )
                yield Static("", id="username_msg")

                yield Static("")

                # Password
                yield Label("Password:", classes="bold")
                yield Input(placeholder="Enter password", password=True, id="password_input")

                yield Static("")

                # Confirm password
                yield Label("Confirm password:", classes="bold")
                yield Input(placeholder="Confirm password", password=True, id="password_confirm")
                yield Static("", id="password_msg")

                yield Static("")

                with Container(classes="info-box"):
                    yield Label(f"Note: {prime} (your Prime agent) will run as a systemd service", classes="muted")
                    yield Label("      under this user account. Choose a strong password.", classes="muted")

        with Horizontal(classes="button-bar"):
            yield Button("← Back", id="btn_back", classes="secondary")
            yield Button("Continue →", id="btn_next", classes="primary")

    def _validate_username(self, name: str) -> tuple[bool, str]:
        if not name:
            return False, "Username cannot be empty."
        if not re.match(r'^[a-z][a-z0-9_-]*$', name):
            return False, "Username must be lowercase letters, numbers, _ or -."
        if len(name) < 2 or len(name) > 32:
            return False, "Username must be 2–32 characters."
        return True, ""

    def _validate_hostname(self, name: str) -> tuple[bool, str]:
        if not name:
            return False, "Hostname cannot be empty."
        if not re.match(r'^[a-zA-Z0-9][a-zA-Z0-9-]*[a-zA-Z0-9]$|^[a-zA-Z0-9]$', name):
            return False, "Hostname must be letters/numbers/hyphens, no leading/trailing hyphens."
        if len(name) > 63:
            return False, "Hostname must be 63 characters or fewer."
        return True, ""

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn_back":
            self.app.go_back()
        elif event.button.id == "btn_next":
            hostname = self.query_one("#hostname_input", Input).value.strip().lower()
            username = self.query_one("#username_input", Input).value.strip().lower()
            password = self.query_one("#password_input", Input).value
            confirm = self.query_one("#password_confirm", Input).value

            errors = []

            ok, msg = self._validate_hostname(hostname)
            if not ok:
                self.query_one("#hostname_msg", Static).update(f"✗ {msg}")
                errors.append(msg)
            else:
                self.query_one("#hostname_msg", Static).update("")

            ok, msg = self._validate_username(username)
            if not ok:
                self.query_one("#username_msg", Static).update(f"✗ {msg}")
                errors.append(msg)
            else:
                self.query_one("#username_msg", Static).update("")

            if not password:
                self.query_one("#password_msg", Static).update("✗ Password cannot be empty.")
                errors.append("Password required.")
            elif password != confirm:
                self.query_one("#password_msg", Static).update("✗ Passwords do not match.")
                errors.append("Passwords must match.")
            elif len(password) < 8:
                self.query_one("#password_msg", Static).update(
                    "⚠ Weak password — use at least 8 characters."
                )
                # Allow weak passwords (warn only)
            else:
                self.query_one("#password_msg", Static).update("✓ Password OK.")

            if errors:
                return

            self.app.state["hostname"] = hostname
            self.app.state["username"] = username
            self.app.state["password"] = password
            self.app.go_next("base_install")
