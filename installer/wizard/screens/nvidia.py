"""Step 8 — Nvidia driver detection and optional installation."""

import subprocess
import os
from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Button, Static, Label, Checkbox, RichLog
from textual.containers import Container, Vertical, Horizontal
from textual.worker import get_current_worker
from textual import work

MOUNT_POINT = "/mnt/hermit"


def detect_nvidia() -> tuple[bool, str]:
    """Check if an Nvidia GPU is present."""
    result = subprocess.run(
        ["lspci"], capture_output=True, text=True
    )
    for line in result.stdout.splitlines():
        if "nvidia" in line.lower():
            return True, line.strip()
    return False, ""


def install_nvidia_driver(log_cb) -> tuple[bool, str]:
    """Install Nvidia proprietary driver inside chroot."""
    env = {
        **os.environ,
        "DEBIAN_FRONTEND": "noninteractive",
        "HOME": "/root",
        "PATH": "/usr/sbin:/usr/bin:/sbin:/bin",
    }

    log_cb("Updating apt cache...")
    proc = subprocess.Popen(
        ["chroot", MOUNT_POINT, "apt-get", "update", "-qq"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, env=env,
    )
    proc.communicate()

    log_cb("Installing nvidia-detect to find correct driver version...")
    proc = subprocess.Popen(
        ["chroot", MOUNT_POINT, "apt-get", "install", "-y", "nvidia-detect"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, env=env,
    )
    proc.communicate()

    # Get recommended driver
    result = subprocess.run(
        ["chroot", MOUNT_POINT, "nvidia-detect"],
        capture_output=True, text=True, env=env,
    )
    log_cb(f"nvidia-detect output:\n{result.stdout}")

    # Parse recommended package
    driver_pkg = "nvidia-driver"
    for line in result.stdout.splitlines():
        if "nvidia-driver" in line.lower() or "nvidia-" in line.lower():
            parts = line.strip().split()
            for part in parts:
                if part.startswith("nvidia-"):
                    driver_pkg = part.strip(".,;")
                    break

    log_cb(f"Installing driver package: {driver_pkg}")
    packages = [
        driver_pkg,
        "nvidia-kernel-support",
        "nvidia-modprobe",
        "libglx-nvidia0",
    ]

    proc = subprocess.Popen(
        ["chroot", MOUNT_POINT, "apt-get", "install", "-y"] + packages,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, env=env,
    )
    for line in proc.stdout:
        log_cb(line.rstrip())
    proc.wait()

    if proc.returncode != 0:
        return False, "Nvidia driver installation failed. You can install it later with: apt install nvidia-driver"

    # Configure kernel parameter
    log_cb("Configuring nvidia-drm.modeset=1...")
    grub_default_path = f"{MOUNT_POINT}/etc/default/grub"
    with open(grub_default_path, "r") as f:
        content = f.read()

    if "nvidia-drm.modeset=1" not in content:
        content = content.replace(
            'GRUB_CMDLINE_LINUX_DEFAULT="',
            'GRUB_CMDLINE_LINUX_DEFAULT="nvidia-drm.modeset=1 '
        )
        with open(grub_default_path, "w") as f:
            f.write(content)

    # Regenerate grub config
    log_cb("Updating GRUB config...")
    subprocess.run(
        ["chroot", MOUNT_POINT, "update-grub"],
        capture_output=True, env=env,
    )

    # Add nvidia modules to initramfs
    modprobe_conf = f"{MOUNT_POINT}/etc/modprobe.d/nvidia.conf"
    with open(modprobe_conf, "w") as f:
        f.write("options nvidia-drm modeset=1\n")
        f.write("blacklist nouveau\n")
        f.write("blacklist nvidiafb\n")

    # Regenerate initramfs
    log_cb("Regenerating initramfs with Nvidia driver...")
    proc = subprocess.Popen(
        ["chroot", MOUNT_POINT, "update-initramfs", "-u", "-k", "all"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, env=env,
    )
    for line in proc.stdout:
        log_cb(line.rstrip())
    proc.wait()

    return True, "Nvidia driver installed. nouveau is blacklisted."


class NvidiaScreen(Screen):
    """Step 8 — Nvidia GPU driver (optional)."""

    _nvidia_detected: bool = False
    _nvidia_info: str = ""
    _done: bool = False

    def compose(self) -> ComposeResult:
        yield Static("  HermitOS Installer", classes="wizard-title")
        yield Static("Step 8 of 9 — Nvidia GPU (Optional)", classes="step-indicator")
        with Container(classes="content-area"):
            with Vertical():
                with Container(id="detect_area"):
                    yield Label("Detecting GPU hardware...", id="detect_status", classes="muted")
                    yield Static("", id="gpu_info")
                    yield Static("")
                    yield Checkbox(
                        "Install Nvidia proprietary driver (non-free)",
                        value=False, id="cb_nvidia"
                    )
                    yield Static("")
                    with Container(classes="info-box"):
                        yield Label("Notes:", classes="bold")
                        yield Label("• Nouveau (open source) works for basic display but not full performance")
                        yield Label("• Proprietary driver needed for: CUDA, AI workloads, Ollama GPU mode")
                        yield Label("• You can install later with: sudo apt install nvidia-driver")
                        yield Label("• Sway works with both drivers")

                yield RichLog(id="nvidia_log", highlight=True, markup=True, max_lines=200)

        with Horizontal(classes="button-bar"):
            yield Button("← Back", id="btn_back", classes="secondary")
            yield Button("Skip (use Nouveau)", id="btn_skip", classes="secondary")
            yield Button("Apply & Continue →", id="btn_next", classes="primary")

    def on_mount(self) -> None:
        self.query_one("#nvidia_log").display = False
        self._detect_gpu()

    def _detect_gpu(self) -> None:
        self._nvidia_detected, self._nvidia_info = detect_nvidia()
        status = self.query_one("#detect_status", Label)
        gpu_info = self.query_one("#gpu_info", Static)
        cb = self.query_one("#cb_nvidia", Checkbox)

        if self._nvidia_detected:
            status.update(f"✓ Nvidia GPU detected!")
            gpu_info.update(self._nvidia_info)
            gpu_info.add_class("success-box")
            cb.value = True  # Default to installing driver if GPU found
        else:
            status.update("No Nvidia GPU detected.")
            gpu_info.update(
                "No Nvidia hardware found. Using standard Nouveau/Mesa drivers."
            )
            cb.value = False
            cb.disabled = True

    @work(exclusive=True, thread=True)
    def run_nvidia_install(self) -> None:
        app = self.app
        if app is None:
            return
        ok, msg = install_nvidia_driver(self._log)
        app.state["install_nvidia"] = ok
        if ok:
            app.call_from_thread(self._on_success, msg)
        else:
            app.call_from_thread(self._on_failed, msg)

    def _log(self, msg: str) -> None:
        app = self.app
        if app is None:
            return
        app.call_from_thread(self._append_log, msg)

    def _append_log(self, msg: str) -> None:
        if msg:
            self.query_one("#nvidia_log", RichLog).write(msg)

    def _on_success(self, msg: str) -> None:
        self._done = True
        self.query_one("#nvidia_log", RichLog).write(f"\n[bold green]✓ {msg}[/bold green]")
        btn = self.query_one("#btn_next", Button)
        btn.label = "Finish →"
        btn.disabled = False
        btn.focus()

    def _on_failed(self, msg: str) -> None:
        self._done = True
        self.query_one("#nvidia_log", RichLog).write(f"\n[yellow]⚠ {msg}[/yellow]")
        btn = self.query_one("#btn_next", Button)
        btn.label = "Continue Without Driver →"
        btn.disabled = False

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn_back":
            self.app.go_back()
        elif event.button.id == "btn_skip" or (
            event.button.id == "btn_next" and self._done
        ):
            self.app.go_next("complete")
        elif event.button.id == "btn_next":
            install = self.query_one("#cb_nvidia", Checkbox).value
            if install and self._nvidia_detected:
                self.query_one("#detect_area").display = False
                self.query_one("#nvidia_log").display = True
                self.query_one("#btn_next", Button).disabled = True
                self.query_one("#btn_next", Button).label = "Installing..."
                self.run_nvidia_install()
            else:
                # Skip nvidia
                self.app.state["install_nvidia"] = False
                self.app.go_next("complete")
