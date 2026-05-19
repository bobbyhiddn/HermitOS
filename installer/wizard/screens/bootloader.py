"""Step 7 — GRUB EFI bootloader installation."""

import subprocess
import os
from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Button, Static, Label, RichLog
from textual.containers import Container, Vertical, Horizontal
from textual.worker import get_current_worker
from textual import work

MOUNT_POINT = "/mnt/hermit"


def chroot_stream(cmd: list[str], log_cb, env_extra: dict = None):
    env = {
        **os.environ,
        "DEBIAN_FRONTEND": "noninteractive",
        "HOME": "/root",
        "PATH": "/usr/sbin:/usr/bin:/sbin:/bin",
    }
    if env_extra:
        env.update(env_extra)
    proc = subprocess.Popen(
        ["chroot", MOUNT_POINT] + cmd,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, env=env,
    )
    for line in proc.stdout:
        log_cb(line.rstrip())
    proc.wait()
    return proc.returncode


def chroot_run(cmd: list[str]):
    env = {
        **os.environ,
        "DEBIAN_FRONTEND": "noninteractive",
        "HOME": "/root",
        "PATH": "/usr/sbin:/usr/bin:/sbin:/bin",
    }
    return subprocess.run(["chroot", MOUNT_POINT] + cmd, capture_output=True, text=True, env=env)


def install_grub(state: dict, log_cb) -> tuple[bool, str]:
    """Install and configure GRUB EFI bootloader."""
    target_drive = state.get("target_drive", "")
    efi_partition = state.get("efi_partition", "")
    install_nvidia = state.get("install_nvidia", False)
    hostname = state.get("hostname", "hermit")

    if not target_drive or not efi_partition:
        return False, "No target drive or EFI partition set."

    log_cb(f"Installing GRUB EFI to {target_drive} (EFI: {efi_partition})")

    # Install GRUB inside chroot
    # --removable: installs to /EFI/BOOT/BOOTX64.EFI so UEFI firmware
    # auto-discovers HermitOS without relying on NVRAM boot entries
    # (critical for USB installs and cross-machine portability)
    rc = chroot_stream(
        [
            "grub-install",
            "--target=x86_64-efi",
            f"--efi-directory=/boot/efi",
            "--bootloader-id=HermitOS",
            "--recheck",
            "--no-floppy",
            "--removable",
            target_drive,
        ],
        log_cb
    )
    if rc != 0:
        return False, "grub-install failed. Check EFI partition is mounted."

    # Configure GRUB defaults
    log_cb("Configuring GRUB...")
    kernel_params = "quiet splash rd.auto=1 net.ifnames=0 biosdevname=0"
    if install_nvidia:
        kernel_params += " nvidia-drm.modeset=1"

    grub_default = f"""GRUB_DEFAULT=0
GRUB_TIMEOUT=5
GRUB_DISTRIBUTOR="HermitOS"
GRUB_CMDLINE_LINUX_DEFAULT="{kernel_params}"
GRUB_CMDLINE_LINUX=""
GRUB_TERMINAL_OUTPUT="console"
GRUB_GFXMODE="auto"
GRUB_DISABLE_OS_PROBER=false
"""
    with open(f"{MOUNT_POINT}/etc/default/grub", "w") as f:
        f.write(grub_default)

    # Enable os-prober for dual-boot detection
    log_cb("Running os-prober to detect other operating systems...")
    chroot_run(["os-prober"])

    # Generate grub.cfg
    log_cb("Generating GRUB configuration...")
    rc = chroot_stream(["update-grub"], log_cb)
    if rc != 0:
        log_cb("Warning: update-grub reported errors (may be non-fatal).")

    # Create EFI fallback entry
    log_cb("Creating EFI fallback boot entry...")
    efi_dir = f"{MOUNT_POINT}/boot/efi/EFI/BOOT"
    hermit_efi_dir = f"{MOUNT_POINT}/boot/efi/EFI/HermitOS"
    os.makedirs(efi_dir, exist_ok=True)

    # Copy grubx64.efi to BOOTX64.EFI for compatibility with strict UEFI firmware
    grubx64 = f"{MOUNT_POINT}/boot/efi/EFI/HermitOS/grubx64.efi"
    bootx64 = f"{efi_dir}/BOOTX64.EFI"
    if os.path.exists(grubx64):
        subprocess.run(["cp", "-f", grubx64, bootx64], capture_output=True)
        log_cb("EFI fallback (BOOTX64.EFI) created.")
    else:
        log_cb("Warning: grubx64.efi not found, skipping fallback copy.")

    return True, "GRUB installed successfully."


def update_initramfs(log_cb) -> tuple[bool, str]:
    """Regenerate initramfs with correct hardware drivers."""
    log_cb("Regenerating initramfs (includes hardware drivers for bare metal)...")

    # Ensure initramfs has the right modules
    modules_conf = f"{MOUNT_POINT}/etc/initramfs-tools/modules"
    with open(modules_conf, "a") as f:
        f.write("# HermitOS — hardware modules\n")
        f.write("nvme\n")
        f.write("ahci\n")
        f.write("sd_mod\n")
        f.write("xhci_hcd\n")
        f.write("ehci_hcd\n")
        f.write("usbhid\n")

    env = {
        **os.environ,
        "DEBIAN_FRONTEND": "noninteractive",
        "HOME": "/root",
        "PATH": "/usr/sbin:/usr/bin:/sbin:/bin",
    }
    proc = subprocess.Popen(
        ["chroot", MOUNT_POINT, "update-initramfs", "-u", "-k", "all"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, env=env,
    )
    for line in proc.stdout:
        log_cb(line.rstrip())
    proc.wait()

    if proc.returncode != 0:
        return False, "update-initramfs failed."
    return True, "initramfs updated with hardware drivers."


class BootloaderScreen(Screen):
    """Step 7 — GRUB EFI bootloader."""

    _done: bool = False

    def compose(self) -> ComposeResult:
        yield Static("  HermitOS Installer", classes="wizard-title")
        yield Static("Step 7 of 9 — Bootloader", classes="step-indicator")
        with Container(classes="content-area"):
            with Vertical():
                with Container(id="info_area", classes="info-box"):
                    target = self.app.state.get("target_drive", "?")
                    efi = self.app.state.get("efi_partition", "?")
                    yield Label("Ready to install GRUB EFI bootloader.", classes="bold")
                    yield Label("")
                    yield Label(f"Target drive: {target}")
                    yield Label(f"EFI partition: {efi}")
                    yield Label("")
                    yield Label("This will:")
                    yield Label("  • Install GRUB EFI to the EFI partition")
                    yield Label("  • Configure boot menu ('HermitOS')")
                    yield Label("  • Run os-prober (detects Windows, other Linux)")
                    yield Label("  • Regenerate initramfs with real hardware drivers")
                    yield Label("    (NVMe, SATA, USB — critical for bare metal boot)")

                yield RichLog(id="grub_log", highlight=True, markup=True, max_lines=200)

        with Horizontal(classes="button-bar"):
            yield Button("← Back", id="btn_back", classes="secondary")
            yield Button("Install Bootloader →", id="btn_next", classes="primary")

    def on_mount(self) -> None:
        self.query_one("#grub_log").display = False

    def _log(self, msg: str) -> None:
        app = self.app
        if app is None:
            return
        app.call_from_thread(self._append_log, msg)

    def _append_log(self, msg: str) -> None:
        if msg:
            self.query_one("#grub_log", RichLog).write(msg)

    @work(exclusive=True, thread=True)
    def run_bootloader_install(self) -> None:
        app = self.app
        if app is None:
            return
        state = app.state

        steps = [
            ("GRUB EFI installation", lambda: install_grub(state, self._log)),
            ("initramfs regeneration", lambda: update_initramfs(self._log)),
        ]

        for name, fn in steps:
            self._log(f"\n[bold cyan]▶ {name}...[/bold cyan]")
            try:
                ok, msg = fn()
                if ok:
                    self._log(f"[green]✓ {msg}[/green]")
                else:
                    self._log(f"[bold red]✗ Failed: {msg}[/bold red]")
                    app.call_from_thread(self._on_failed, msg)
                    return
            except Exception as e:
                self._log(f"[bold red]✗ Exception: {e}[/bold red]")
                app.call_from_thread(self._on_failed, str(e))
                return

        app.state["grub_done"] = True
        app.call_from_thread(self._on_success)

    def _on_success(self) -> None:
        self._done = True
        self.query_one("#grub_log", RichLog).write(
            "\n[bold green]✓ Bootloader installed. System is bootable.[/bold green]"
        )
        btn = self.query_one("#btn_next", Button)
        btn.label = "Continue →"
        btn.disabled = False
        btn.focus()

    def _on_failed(self, msg: str) -> None:
        btn = self.query_one("#btn_next", Button)
        btn.label = "Retry"
        btn.disabled = False

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn_back":
            self.app.go_back()
        elif event.button.id == "btn_next":
            if self._done:
                self.app.go_next("nvidia")
                return
            self.query_one("#info_area").display = False
            self.query_one("#grub_log").display = True
            self.query_one("#btn_next", Button).disabled = True
            self.query_one("#btn_next", Button).label = "Installing..."
            self.run_bootloader_install()
