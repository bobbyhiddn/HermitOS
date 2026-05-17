"""
Step 11 (post-stack) — Shore prime registration.

Shore is the SOC/watchdog dashboard. When a prime starts up, it registers
with Shore so its tile appears in the Shore landing page.

The installer writes the prime's registration record into
/etc/hermetic/primes.d/<prime-name>.json — Shore watches this directory
and creates a tile for each registered prime on startup or via inotify.

Registration record schema:
    {
        "name": "nova",          // prime name (machine-readable)
        "display": "Nova",       // display name (title-case)
        "port": 7777,            // dashboard HTTP port
        "dashboard_url": "http://localhost:7777",
        "health_url": "http://localhost:7777/status",  // 200 = healthy
        "service": "nova.service",                     // systemd unit to check
        "registered_at": "2026-01-01T00:00:00Z",
        "installer_version": "1.0.0"
    }

Shore reads all .json files in /etc/hermetic/primes.d/ and renders a tile
per entry. Health is checked by polling health_url every 30s:
    green  = HTTP 200
    yellow = HTTP non-200 or timeout < 5s
    red    = connection refused / service not running

Shore itself typically runs at :7778. If Shore is not installed, this
step writes the registration file only — the tile appears once Shore
is installed and started.
"""

import json
import os
import datetime
from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Button, Static, Label, Input
from textual.containers import Container, Vertical, Horizontal

MOUNT_POINT = "/mnt/hermit"
PRIMES_DIR = "etc/hermetic/primes.d"


class ShoreRegisterScreen(Screen):
    """
    Step 11 — Register this prime with Shore.
    Configures the Shore tile for this prime's dashboard.
    """

    def compose(self) -> ComposeResult:
        state = self.app.state
        prime = state.get("prime_name", "prime")
        prime_display = state.get("prime_name_display", prime.capitalize())
        default_port = "7777"

        yield Static("  HermitOS Installer", classes="wizard-title")
        yield Static("Step 11 of 12 — Shore Registration", classes="step-indicator")
        with Container(classes="content-area"):
            with Vertical():
                with Container(classes="info-box"):
                    yield Label("Register your prime with Shore.", classes="bold")
                    yield Label("")
                    yield Label(
                        "Shore is the system dashboard — it shows a tile for each prime "
                        "running on this box. When you start HermitOS, Shore displays "
                        f"a '{prime_display}' tile that links to the prime's dashboard."
                    )
                    yield Label("")
                    yield Label("Shore runs at:  http://localhost:7778", classes="muted")
                    yield Label(
                        f"Tile will show: {prime_display}  →  http://localhost:{default_port}",
                        classes="muted"
                    )

                yield Static("")

                yield Label(f"Prime dashboard port (default: {default_port}):", classes="bold")
                yield Input(value=default_port, id="port_input", placeholder="7777")

                yield Static("")
                yield Label("Shore service URL (where Shore runs):", classes="bold")
                yield Input(value="http://localhost:7778", id="shore_url_input")

                yield Static("")
                with Container(classes="warning-box"):
                    yield Label("Note: Shore will be installed as part of the HermitOS stack.", classes="bold")
                    yield Label(
                        "The registration file is written now so Shore picks it up "
                        "automatically on first boot."
                    )

                yield Static("", id="reg_status")

        with Horizontal(classes="button-bar"):
            yield Button("← Back", id="btn_back", classes="secondary")
            yield Button("Skip (configure later)", id="btn_skip", classes="secondary")
            yield Button("Register & Continue →", id="btn_next", classes="primary")

    def _write_registration(self, prime: str, port: int, shore_url: str) -> tuple[bool, str]:
        """Write the Shore prime registration JSON file."""
        primes_dir = os.path.join(MOUNT_POINT, PRIMES_DIR)
        os.makedirs(primes_dir, exist_ok=True)

        registration = {
            "name": prime,
            "display": prime.capitalize(),
            "port": port,
            "dashboard_url": f"http://localhost:{port}",
            "health_url": f"http://localhost:{port}/status",
            "service": f"{prime}.service",
            "shore_url": shore_url,
            "registered_at": datetime.datetime.utcnow().isoformat() + "Z",
            "installer_version": "1.0.0",
        }

        reg_path = os.path.join(primes_dir, f"{prime}.json")
        try:
            with open(reg_path, "w") as f:
                json.dump(registration, f, indent=2)
            return True, reg_path
        except Exception as e:
            return False, str(e)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        state = self.app.state
        prime = state.get("prime_name", "prime")

        if event.button.id == "btn_back":
            self.app.go_back()

        elif event.button.id == "btn_skip":
            self.app.go_next("bootloader")

        elif event.button.id == "btn_next":
            port_str = self.query_one("#port_input", Input).value.strip()
            shore_url = self.query_one("#shore_url_input", Input).value.strip()

            try:
                port = int(port_str)
                if not (1024 <= port <= 65535):
                    raise ValueError("out of range")
            except ValueError:
                self.query_one("#reg_status", Static).update(
                    "✗ Invalid port. Use a number between 1024 and 65535."
                )
                return

            state["prime_port"] = port
            state["shore_url"] = shore_url

            ok, result = self._write_registration(prime, port, shore_url)
            status = self.query_one("#reg_status", Static)

            if ok:
                status.update(f"✓ Registered! Shore tile config written to:\n  {result}")
                status.add_class("success-box")
                self.app.go_next("bootloader")
            else:
                status.update(f"⚠ Could not write registration: {result}\nContinuing anyway...")
                status.add_class("warning-box")
                self.app.go_next("bootloader")
