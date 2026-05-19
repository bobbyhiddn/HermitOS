"""Step 1 — Welcome screen."""

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Button, Static, Label
from textual.containers import Container, Vertical, Horizontal


LOGO = """
  ██╗  ██╗███████╗██████╗ ███╗   ███╗██╗████████╗ ██████╗ ███████╗
  ██║  ██║██╔════╝██╔══██╗████╗ ████║██║╚══██╔══╝██╔═══██╗██╔════╝
  ███████║█████╗  ██████╔╝██╔████╔██║██║   ██║   ██║   ██║███████╗
  ██╔══██║██╔══╝  ██╔══██╗██║╚██╔╝██║██║   ██║   ██║   ██║╚════██║
  ██║  ██║███████╗██║  ██║██║ ╚═╝ ██║██║   ██║   ╚██████╔╝███████║
  ╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝╚═╝     ╚═╝╚═╝   ╚═╝    ╚═════╝ ╚══════╝
"""


class WelcomeScreen(Screen):
    """Welcome & introduction screen."""

    def compose(self) -> ComposeResult:
        yield Static(LOGO, classes="hermit-logo")
        yield Static("Step 1 of 9 — Welcome", classes="step-indicator")
        with Container(classes="content-area"):
            with Vertical():
                yield Static("")
                with Container(classes="info-box"):
                    yield Label("Welcome to the HermitOS Installer!", classes="bold")
                    yield Label("")
                    yield Label(
                        "HermitOS is a self-hosted computing platform built on Debian 13 (Trixie). "
                        "It combines a Wayland desktop (Sway), container orchestration (K3s + Incus), "
                        "and an AI agent layer (Hermetic) into a single cohesive system."
                    )
                    yield Label("")
                    yield Label("This wizard will guide you through a complete installation:", classes="bold")
                    yield Label("  • Network setup")
                    yield Label("  • Drive selection & partitioning")
                    yield Label("  • Base Debian 13 installation")
                    yield Label("  • HermitOS stack (desktop, K3s, Incus)")
                    yield Label("  • Bootloader (GRUB EFI)")
                    yield Label("  • Optional: Nvidia driver setup")
                    yield Label("")

                with Container(classes="warning-box"):
                    yield Label("⚠  This installer will ERASE the selected drive.", classes="bold")
                    yield Label("   Ensure you have backups of any important data before continuing.")

                yield Static("")
                yield Label("Estimated time: 20–45 minutes (depends on internet speed)", classes="muted")

        with Horizontal(classes="button-bar"):
            yield Button("Begin Installation →", variant="success", id="btn_next", classes="primary")
            yield Button("Exit Installer", variant="default", id="btn_exit", classes="secondary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn_next":
            self.app.go_next("locale")  # Step 2: Language/Locale
        elif event.button.id == "btn_exit":
            self.app.exit()
