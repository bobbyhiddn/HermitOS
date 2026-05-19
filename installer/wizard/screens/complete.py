"""Step 9 — Installation complete."""

import subprocess
import os
from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Button, Static, Label, RichLog
from textual.containers import Container, Vertical, Horizontal
from textual.worker import get_current_worker
from textual import work

MOUNT_POINT = "/mnt/hermit"


def unmount_all(log_cb) -> None:
    """Safely unmount all partitions."""
    # Unmount in reverse order
    mounts = [
        f"{MOUNT_POINT}/dev/pts",
        f"{MOUNT_POINT}/dev",
        f"{MOUNT_POINT}/run",
        f"{MOUNT_POINT}/sys",
        f"{MOUNT_POINT}/proc",
        f"{MOUNT_POINT}/home",
        f"{MOUNT_POINT}/boot/efi",
        MOUNT_POINT,
    ]
    for mount in mounts:
        r = subprocess.run(
            ["umount", "-lf", mount],
            capture_output=True, text=True
        )
        if r.returncode == 0:
            log_cb(f"Unmounted: {mount}")
        # Ignore errors (mount may not be mounted)


class CompleteScreen(Screen):
    """Step 9 — Installation complete."""

    def compose(self) -> ComposeResult:
        state = self.app.state
        hostname = state.get("hostname", "hermit")
        username = state.get("username", "hermit")
        target_drive = state.get("target_drive", "?")

        yield Static("  HermitOS Installer", classes="wizard-title")
        yield Static("Step 9 of 9 — Complete!", classes="step-indicator")
        with Container(classes="content-area"):
            with Vertical():
                yield Static("")
                with Container(classes="success-box"):
                    yield Label("✓ HermitOS installation complete!", classes="bold")
                    yield Label("")
                    yield Label(f"Hostname:   {hostname}")
                    yield Label(f"Username:   {username}")
                    yield Label(f"Drive:      {target_drive}")
                    yield Label("")
                    yield Label("What was installed:", classes="bold")
                    prime = state.get("prime_name_display", "")
                    if state.get("install_sway"):
                        yield Label("  ✓ KDE Plasma 6 desktop (Wayland)")
                    if state.get("install_incus"):
                        yield Label("  ✓ Incus hypervisor (VMs & containers)")
                    if state.get("install_k3s"):
                        yield Label("  ✓ K3s single-node Kubernetes")
                    if state.get("install_hermetic") and prime:
                        yield Label(f"  ✓ Hermetic agent platform (Prime: {prime})")
                    if state.get("install_nvidia"):
                        yield Label("  ✓ Nvidia proprietary driver")
                    yield Label("  ✓ Base Debian 13 (Trixie)")
                    yield Label("  ✓ Linux kernel (amd64) with hardware firmware")
                    yield Label("  ✓ GRUB EFI bootloader")

                yield Static("")
                with Container(classes="warning-box"):
                    yield Label("⚠  Next steps:", classes="bold")
                    yield Label("  1. Select 'Unmount & Reboot' below")
                    yield Label("  2. Remove this USB drive when system shuts down")
                    yield Label("  3. Boot into HermitOS from your drive")
                    yield Label(f"  4. Log in as '{username}' — Sway starts automatically")
                    yield Label("  5. Open a terminal (Super+Enter) to begin configuration")

                yield Static("")
                yield RichLog(id="unmount_log", highlight=True, markup=True, max_lines=50)

        with Horizontal(classes="button-bar"):
            yield Button("Open Shell (Debug)", id="btn_shell", classes="secondary")
            yield Button("Unmount & Reboot", id="btn_reboot", classes="primary")

    def on_mount(self) -> None:
        self.query_one("#unmount_log").display = False

    def _log(self, msg: str) -> None:
        app = self.app
        if app is None:
            return
        app.call_from_thread(self._append_log, msg)

    def _append_log(self, msg: str) -> None:
        self.query_one("#unmount_log", RichLog).write(msg)

    @work(exclusive=True, thread=True)
    def do_unmount_and_reboot(self) -> None:
        self._log("Unmounting all partitions...")
        unmount_all(self._log)
        self._log("[bold green]✓ All partitions unmounted safely.[/bold green]")
        self._log("")
        self._log("[bold]Rebooting in 5 seconds...[/bold]")
        self._log("Remove the USB drive when the system powers off!")
        import time
        time.sleep(5)
        subprocess.run(["reboot"])

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn_reboot":
            self.query_one("#unmount_log").display = True
            self.query_one("#btn_reboot").disabled = True
            self.query_one("#btn_reboot").label = "Rebooting..."
            self.do_unmount_and_reboot()
        elif event.button.id == "btn_shell":
            # Exit the app — drops to shell for recovery
            self.app.exit()
