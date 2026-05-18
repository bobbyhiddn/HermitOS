"""Step 5 — Base system installation via debootstrap."""

import subprocess
import os
import threading
from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Button, Static, Label, ProgressBar, RichLog
from textual.containers import Container, Vertical, Horizontal
from textual.worker import get_current_worker
from textual import work


MOUNT_POINT = "/mnt/hermit"


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, **kwargs)


def mount_partitions(state: dict) -> tuple[bool, str]:
    """Mount root, EFI, and optional home partitions to MOUNT_POINT."""
    root = state.get("root_partition", "")
    efi = state.get("efi_partition", "")
    home = state.get("home_partition", "")

    os.makedirs(MOUNT_POINT, exist_ok=True)

    # Mount root
    r = run(["mount", root, MOUNT_POINT])
    if r.returncode != 0:
        return False, f"Failed to mount root {root}: {r.stderr}"

    # Mount EFI
    efi_dir = f"{MOUNT_POINT}/boot/efi"
    os.makedirs(efi_dir, exist_ok=True)
    r = run(["mount", efi, efi_dir])
    if r.returncode != 0:
        return False, f"Failed to mount EFI {efi}: {r.stderr}"

    # Mount home if separate
    if home:
        home_dir = f"{MOUNT_POINT}/home"
        os.makedirs(home_dir, exist_ok=True)
        r = run(["mount", home, home_dir])
        if r.returncode != 0:
            return False, f"Failed to mount home {home}: {r.stderr}"

    return True, "Partitions mounted."


def run_debootstrap(log_cb) -> tuple[bool, str]:
    """Run debootstrap to install base Debian 13 system."""
    log_cb("Running debootstrap (this takes 10-20 minutes)...")
    log_cb("Downloading base system packages from deb.debian.org...")

    proc = subprocess.Popen(
        [
            "debootstrap",
            "--arch=amd64",
            "--include=apt-transport-https,ca-certificates,curl,gnupg,locales,sudo,systemd,systemd-sysv",
            "trixie",
            MOUNT_POINT,
            "http://deb.debian.org/debian",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    for line in proc.stdout:
        line = line.rstrip()
        if line:
            log_cb(line)

    proc.wait()
    if proc.returncode != 0:
        return False, "debootstrap failed — check network connectivity."
    return True, "debootstrap complete."


def configure_apt(state: dict, log_cb) -> None:
    """Write apt sources with full non-free support."""
    log_cb("Configuring apt sources...")
    sources = """deb http://deb.debian.org/debian trixie main contrib non-free non-free-firmware
deb http://security.debian.org/debian-security trixie-security main contrib non-free non-free-firmware
deb http://deb.debian.org/debian trixie-updates main contrib non-free non-free-firmware
"""
    with open(f"{MOUNT_POINT}/etc/apt/sources.list", "w") as f:
        f.write(sources)

    # Write apt preferences to prefer trixie
    os.makedirs(f"{MOUNT_POINT}/etc/apt/preferences.d", exist_ok=True)
    with open(f"{MOUNT_POINT}/etc/apt/preferences.d/hermit", "w") as f:
        f.write("Package: *\nPin: release n=trixie\nPin-Priority: 900\n")


def bind_mount_filesystems(log_cb) -> None:
    """Bind-mount /proc, /sys, /dev for chroot operations."""
    log_cb("Mounting virtual filesystems...")
    for fs, target in [
        ("proc", f"{MOUNT_POINT}/proc"),
        ("sysfs", f"{MOUNT_POINT}/sys"),
        ("devtmpfs", f"{MOUNT_POINT}/dev"),
        ("devpts", f"{MOUNT_POINT}/dev/pts"),
        ("tmpfs", f"{MOUNT_POINT}/run"),
    ]:
        os.makedirs(target, exist_ok=True)
        run(["mount", "-t", fs, fs, target])


def chroot_run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    """Run a command inside the chroot."""
    return subprocess.run(
        ["chroot", MOUNT_POINT] + cmd,
        capture_output=True, text=True, **kwargs
    )


def install_base_packages(log_cb) -> tuple[bool, str]:
    """Install essential packages inside chroot."""
    packages = [
        # Kernel & firmware (critical for bare metal!)
        "linux-image-amd64",
        "linux-headers-amd64",
        "firmware-linux",
        "firmware-linux-nonfree",
        "firmware-misc-nonfree",
        "firmware-iwlwifi",
        "firmware-atheros",
        "firmware-realtek",
        "firmware-brcm80211",
        "intel-microcode",
        "amd64-microcode",
        # Network
        "network-manager",
        "wpasupplicant",
        "wireless-tools",
        "iw",
        # Base system
        "sudo",
        "openssh-server",
        "curl",
        "wget",
        "git",
        "vim",
        "tmux",
        "htop",
        "rsync",
        "unzip",
        "lsof",
        "pciutils",
        "usbutils",
        "dmidecode",
        "lshw",
        # Storage
        "parted",
        "gdisk",
        "e2fsprogs",
        "dosfstools",
        "nvme-cli",
        "smartmontools",
        # Boot
        "grub-efi-amd64",
        "grub-efi-amd64-signed",
        "shim-signed",
        "efibootmgr",
        "os-prober",
        # Python
        "python3",
        "python3-pip",
        "python3-venv",
        "pipx",
        # Locale & time
        "locales",
        "tzdata",
        "ntpsec",
    ]

    log_cb("Updating apt package index...")
    r = chroot_run(["apt-get", "update", "-qq"])
    if r.returncode != 0:
        return False, f"apt-get update failed: {r.stderr}"

    log_cb(f"Installing {len(packages)} base packages (may take 5-15 minutes)...")

    proc = subprocess.Popen(
        ["chroot", MOUNT_POINT, "apt-get", "install", "-y", "--no-install-recommends"] + packages,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env={**os.environ, "DEBIAN_FRONTEND": "noninteractive"},
    )
    for line in proc.stdout:
        line = line.rstrip()
        if line and not line.startswith("debconf"):
            log_cb(line)

    proc.wait()
    if proc.returncode != 0:
        return False, "Package installation failed."
    return True, "Base packages installed."


def configure_system(state: dict, log_cb) -> None:
    """Configure locale, timezone, hostname, fstab."""
    hostname = state.get("hostname", "hermit")
    locale = state.get("locale", "en_US.UTF-8")
    timezone = state.get("timezone", "America/Chicago")
    root_part = state.get("root_partition", "")
    efi_part = state.get("efi_partition", "")
    home_part = state.get("home_partition", "")

    log_cb(f"Setting hostname: {hostname}")
    with open(f"{MOUNT_POINT}/etc/hostname", "w") as f:
        f.write(f"{hostname}\n")
    with open(f"{MOUNT_POINT}/etc/hosts", "w") as f:
        f.write(f"127.0.0.1\tlocalhost\n127.0.1.1\t{hostname}\n\n"
                f"::1\tlocalhost ip6-localhost ip6-loopback\n")

    log_cb(f"Setting locale: {locale}")
    chroot_run(["sed", "-i", f"s/# {locale} UTF-8/{locale} UTF-8/", "/etc/locale.gen"])
    chroot_run(["locale-gen"])
    with open(f"{MOUNT_POINT}/etc/locale.conf", "w") as f:
        f.write(f"LANG={locale}\n")

    log_cb(f"Setting timezone: {timezone}")
    chroot_run(["ln", "-sf", f"/usr/share/zoneinfo/{timezone}", "/etc/localtime"])
    chroot_run(["dpkg-reconfigure", "-f", "noninteractive", "tzdata"])

    log_cb("Writing /etc/fstab...")
    # Get UUIDs
    def get_uuid(part: str) -> str:
        r = subprocess.run(["blkid", "-s", "UUID", "-o", "value", part], capture_output=True, text=True)
        return r.stdout.strip()

    root_uuid = get_uuid(root_part)
    efi_uuid = get_uuid(efi_part)

    fstab = f"# /etc/fstab - HermitOS\n"
    fstab += f"UUID={root_uuid}\t/\text4\terrors=remount-ro\t0\t1\n"
    fstab += f"UUID={efi_uuid}\t/boot/efi\tvfat\tumask=0077\t0\t1\n"
    if home_part:
        home_uuid = get_uuid(home_part)
        fstab += f"UUID={home_uuid}\t/home\text4\tdefaults\t0\t2\n"
    fstab += "tmpfs\t/tmp\ttmpfs\tdefaults,nosuid,nodev\t0\t0\n"

    with open(f"{MOUNT_POINT}/etc/fstab", "w") as f:
        f.write(fstab)

    log_cb("Enabling NetworkManager...")
    chroot_run(["systemctl", "enable", "NetworkManager"])


def create_user(state: dict, log_cb) -> None:
    """Create the main user account."""
    username = state.get("username", "hermit")
    password = state.get("password", "hermit")

    log_cb(f"Creating user: {username}")
    chroot_run(["useradd", "-m", "-s", "/bin/bash",
                "-G", "sudo,audio,video,plugdev,netdev,bluetooth",
                username])
    proc = subprocess.Popen(
        ["chroot", MOUNT_POINT, "passwd", username],
        stdin=subprocess.PIPE,
        capture_output=True, text=True,
    )
    proc.communicate(input=f"{password}\n{password}\n")

    log_cb(f"Configuring sudo for {username}...")
    with open(f"{MOUNT_POINT}/etc/sudoers.d/{username}", "w") as f:
        f.write(f"{username} ALL=(ALL) NOPASSWD:ALL\n")
    os.chmod(f"{MOUNT_POINT}/etc/sudoers.d/{username}", 0o440)


class BaseInstallScreen(Screen):
    """Step 5 — Base system installation."""

    _install_done: bool = False

    def compose(self) -> ComposeResult:
        yield Static("  HermitOS Installer", classes="wizard-title")
        yield Static("Step 5 of 9 — Base System Installation", classes="step-indicator")
        with Container(classes="content-area"):
            with Vertical():
                with Container(id="pre_install", classes="info-box"):
                    yield Label("Ready to install Debian 13 (Trixie) base system.", classes="bold")
                    yield Label("")
                    root = self.app.state.get("root_partition", "?")
                    efi = self.app.state.get("efi_partition", "?")
                    yield Label(f"Root partition: {root}")
                    yield Label(f"EFI partition:  {efi}")
                    home = self.app.state.get("home_partition", "")
                    if home:
                        yield Label(f"Home partition: {home}")
                    yield Label("")
                    yield Label("This will run debootstrap + configure the base system.")
                    yield Label("⏱  Estimated time: 10–25 minutes", classes="muted")
                yield Static("", id="log_container")
                yield RichLog(id="install_log", highlight=True, markup=True, max_lines=200)

        with Horizontal(classes="button-bar"):
            yield Button("← Back", id="btn_back", classes="secondary")
            yield Button("Begin Installation →", id="btn_next", classes="primary")

    def on_mount(self) -> None:
        self.query_one("#install_log").display = False
        self.query_one("#log_container").display = False

    def _log(self, msg: str) -> None:
        """Thread-safe log update."""
        app = self.app
        if app is None:
            return
        app.call_from_thread(self._append_log, msg)

    def _append_log(self, msg: str) -> None:
        log = self.query_one("#install_log", RichLog)
        log.write(msg)

    @work(exclusive=True, thread=True)
    def run_installation(self) -> None:
        app = self.app
        if app is None:
            return
        state = app.state

        steps = [
            ("Mounting partitions", lambda: mount_partitions(state)),
            ("Running debootstrap", lambda: run_debootstrap(self._log)),
            ("Configuring apt sources", lambda: (configure_apt(state, self._log), (True, "OK"))[1]),
            ("Binding virtual filesystems", lambda: (bind_mount_filesystems(self._log), (True, "OK"))[1]),
            ("Installing base packages", lambda: install_base_packages(self._log)),
            ("Configuring system (hostname, locale, fstab)", lambda: (configure_system(state, self._log), (True, "OK"))[1]),
            ("Creating user account", lambda: (create_user(state, self._log), (True, "OK"))[1]),
        ]

        for step_name, step_fn in steps:
            self._log(f"\n[bold cyan]▶ {step_name}...[/bold cyan]")
            try:
                result = step_fn()
                if isinstance(result, tuple):
                    ok, msg = result
                    if not ok:
                        self._log(f"[bold red]✗ Failed: {msg}[/bold red]")
                        app.call_from_thread(self._on_install_failed, msg)
                        return
                    self._log(f"[green]✓ {msg}[/green]")
                else:
                    self._log(f"[green]✓ Done[/green]")
            except Exception as e:
                self._log(f"[bold red]✗ Exception: {e}[/bold red]")
                app.call_from_thread(self._on_install_failed, str(e))
                return

        app.state["debootstrap_done"] = True
        app.call_from_thread(self._on_install_success)

    def _on_install_success(self) -> None:
        self._install_done = True
        log = self.query_one("#install_log", RichLog)
        log.write("\n[bold green]✓ Base system installation complete![/bold green]")
        btn = self.query_one("#btn_next", Button)
        btn.label = "Continue to HermitOS Stack →"
        btn.disabled = False
        btn.focus()

    def _on_install_failed(self, msg: str) -> None:
        log = self.query_one("#install_log", RichLog)
        log.write(f"\n[bold red]Installation failed. You can retry or exit to a shell.[/bold red]")
        self.query_one("#btn_next", Button).label = "Retry"
        self.query_one("#btn_next", Button).disabled = False

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn_back":
            self.app.go_back()
        elif event.button.id == "btn_next":
            if self._install_done:
                self.app.go_next("hermitos_stack")
                return
            # Start installation
            self.query_one("#pre_install").display = False
            self.query_one("#install_log").display = True
            self.query_one("#btn_next", Button).disabled = True
            self.query_one("#btn_next", Button).label = "Installing..."
            self.run_installation()
