"""Step 6 — HermitOS stack selection and installation."""

import subprocess
import os
from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Button, Static, Label, Checkbox, RichLog
from textual.containers import Container, Vertical, Horizontal, ScrollableContainer
from textual.worker import get_current_worker
from textual import work

MOUNT_POINT = "/mnt/hermit"


def chroot_run(cmd: list[str], env_extra: dict = None) -> subprocess.CompletedProcess:
    env = {**os.environ, "DEBIAN_FRONTEND": "noninteractive", "HOME": "/root", "PATH": "/usr/sbin:/usr/bin:/sbin:/bin"}
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        ["chroot", MOUNT_POINT] + cmd,
        capture_output=True, text=True, env=env,
    )


def chroot_stream(cmd: list[str], log_cb, env_extra: dict = None):
    """Run command in chroot, streaming output to log_cb."""
    env = {**os.environ, "DEBIAN_FRONTEND": "noninteractive", "HOME": "/root", "PATH": "/usr/sbin:/usr/bin:/sbin:/bin"}
    if env_extra:
        env.update(env_extra)
    proc = subprocess.Popen(
        ["chroot", MOUNT_POINT] + cmd,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, env=env,
    )
    for line in proc.stdout:
        line = line.rstrip()
        if line:
            log_cb(line)
    proc.wait()
    return proc.returncode


def install_desktop(log_cb) -> tuple[bool, str]:
    """Install KDE Plasma 6 Wayland desktop environment (NVIDIA-friendly)."""
    packages = [
        # KDE Plasma 6 core
        "kde-plasma-desktop",
        "plasma-workspace-wayland",
        "sddm",
        # Essential KDE apps
        "konsole",
        "dolphin",
        "firefox-esr",
        # Audio
        "pipewire",
        "pipewire-pulse",
        "wireplumber",
        "pavucontrol",
        # Portal for Wayland integration
        "xdg-desktop-portal-kde",
        # Screenshot / clipboard
        "spectacle",
        "wl-clipboard",
        # Fonts
        "fonts-noto",
        "fonts-noto-color-emoji",
        # NVIDIA Wayland support
        "egl-wayland",
    ]
    log_cb("Installing KDE Plasma 6 Wayland desktop...")
    rc = chroot_stream(
        ["apt-get", "install", "-y"] + packages,
        log_cb
    )
    if rc != 0:
        return False, "KDE Plasma installation failed."

    # Enable SDDM display manager
    chroot_run(["systemctl", "enable", "sddm"])
    log_cb("SDDM display manager enabled.")

    # Install default wallpaper
    wallpaper_dir = f"{MOUNT_POINT}/usr/share/backgrounds/hermitos"
    os.makedirs(wallpaper_dir, exist_ok=True)
    wallpaper_src = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        "assets", "wallpapers", "default-wallpaper.png"
    )
    if os.path.exists(wallpaper_src):
        import shutil
        shutil.copy2(wallpaper_src, f"{wallpaper_dir}/default-wallpaper.png")
        log_cb("Installed default wallpaper.")

    # Configure KDE to use the hermit wallpaper by default
    # plasma-org.kde.plasma.desktop-appletsrc sets the wallpaper plugin config
    plasma_cfg_dir = f"{MOUNT_POINT}/etc/skel/.config"
    os.makedirs(plasma_cfg_dir, exist_ok=True)
    with open(f"{plasma_cfg_dir}/plasma-org.kde.plasma.desktop-appletsrc", "w") as f:
        f.write("""[Containments][1]
activityId=
formfactor=0
immutability=1
lastScreen=0
location=0
plugin=org.kde.desktopcontainment
wallpaperplugin=org.kde.image

[Containments][1][Wallpaper][org.kde.image][General]
Image=file:///usr/share/backgrounds/hermitos/default-wallpaper.png
FillMode=1
""")

    # Configure SDDM to use Wayland session by default
    sddm_conf_dir = f"{MOUNT_POINT}/etc/sddm.conf.d"
    os.makedirs(sddm_conf_dir, exist_ok=True)
    with open(f"{sddm_conf_dir}/hermit.conf", "w") as f:
        f.write("""[General]
DisplayServer=wayland

[Wayland]
SessionDir=/usr/share/wayland-sessions

[Theme]
Current=breeze
""")

    # NVIDIA Wayland environment variables (critical for proprietary drivers)
    with open(f"{MOUNT_POINT}/etc/profile.d/nvidia-wayland.sh", "w") as f:
        f.write("""# HermitOS — NVIDIA Wayland compatibility
# These ensure KDE Plasma Wayland works properly with proprietary NVIDIA drivers
export __GL_GSYNC_ALLOWED=1
export __GL_VRR_ALLOWED=1
export GBM_BACKEND=nvidia-drm
export __GLX_VENDOR_LIBRARY_NAME=nvidia
""")

    # Ensure nvidia-drm modeset is enabled (required for Wayland)
    modeset_conf = f"{MOUNT_POINT}/etc/modprobe.d/nvidia-wayland.conf"
    with open(modeset_conf, "w") as f:
        f.write("options nvidia-drm modeset=1\n")

    log_cb("KDE Plasma 6 Wayland configured with NVIDIA support.")
    return True, "KDE Plasma 6 desktop installed."


def install_incus(log_cb) -> tuple[bool, str]:
    """Install Incus hypervisor."""
    log_cb("Installing Incus hypervisor...")
    rc = chroot_stream(
        ["apt-get", "install", "-y", "incus", "incus-ui-canonical"],
        log_cb
    )
    if rc != 0:
        # Try without UI
        rc = chroot_stream(["apt-get", "install", "-y", "incus"], log_cb)
        if rc != 0:
            return False, "Incus installation failed."

    # Add user to incus-admin group
    username = "hermit"  # will be updated dynamically
    log_cb("Incus installed. User will be added to incus-admin group after setup.")
    return True, "Incus installed."


def install_k3s_script(log_cb) -> tuple[bool, str]:
    """Install K3s via their install script (requires network)."""
    log_cb("Installing K3s single-node Kubernetes...")
    log_cb("Downloading k3s installer...")

    # Download k3s binary directly (more reliable than curl | sh in chroot)
    k3s_url = "https://github.com/k3s-io/k3s/releases/latest/download/k3s"
    r = subprocess.run(
        ["curl", "-sfL", "-o", f"{MOUNT_POINT}/usr/local/bin/k3s", k3s_url],
        capture_output=True, text=True, timeout=120
    )
    if r.returncode != 0:
        return False, f"Failed to download k3s: {r.stderr}"

    os.chmod(f"{MOUNT_POINT}/usr/local/bin/k3s", 0o755)

    # Write k3s systemd service
    k3s_service = """[Unit]
Description=Lightweight Kubernetes
Documentation=https://k3s.io
Wants=network-online.target
After=network-online.target

[Service]
Type=notify
ExecStartPre=/bin/sh -xc '! /usr/bin/systemctl is-enabled --quiet nm-cloud-setup.service 2>/dev/null'
ExecStart=/usr/local/bin/k3s server --write-kubeconfig-mode 644
KillMode=process
Delegate=yes
LimitNOFILE=1048576
LimitNPROC=infinity
LimitCORE=infinity
TasksMax=infinity
TimeoutStartSec=0
Restart=always
RestartSec=5s

[Install]
WantedBy=multi-user.target
"""
    with open(f"{MOUNT_POINT}/etc/systemd/system/k3s.service", "w") as f:
        f.write(k3s_service)

    # Create kubectl + kubeconfig symlinks
    chroot_run(["ln", "-sf", "/usr/local/bin/k3s", "/usr/local/bin/kubectl"])

    # KUBECONFIG for the hermit user
    with open(f"{MOUNT_POINT}/etc/profile.d/k3s.sh", "w") as f:
        f.write('export KUBECONFIG=/etc/rancher/k3s/k3s.yaml\n')

    # Enable the service
    chroot_run(["systemctl", "enable", "k3s"])

    log_cb("K3s installed and enabled.")
    return True, "K3s installed."


def install_uv_go(log_cb) -> tuple[bool, str]:
    """Install uv (Python) and Go toolchain."""
    log_cb("Installing Go toolchain...")

    # Go: download latest amd64 binary
    go_url = "https://go.dev/dl/go1.22.5.linux-amd64.tar.gz"
    r = subprocess.run(
        ["curl", "-sfL", "-o", "/tmp/go.tar.gz", go_url],
        capture_output=True, text=True, timeout=120
    )
    if r.returncode == 0:
        subprocess.run(
            ["tar", "-C", f"{MOUNT_POINT}/usr/local", "-xzf", "/tmp/go.tar.gz"],
            check=True
        )
        with open(f"{MOUNT_POINT}/etc/profile.d/go.sh", "w") as f:
            f.write('export PATH=$PATH:/usr/local/go/bin\n')
        log_cb("Go 1.22 installed.")
    else:
        log_cb("Warning: Could not download Go — install manually later.")

    log_cb("Installing uv (Python package manager)...")
    r = subprocess.run(
        ["curl", "-LsSf", "-o", "/tmp/uv-install.sh", "https://astral.sh/uv/install.sh"],
        capture_output=True, text=True, timeout=30
    )
    if r.returncode == 0:
        # Install uv to /usr/local/bin
        env = {**os.environ, "UV_INSTALL_DIR": f"{MOUNT_POINT}/usr/local/bin", "HOME": "/root"}
        subprocess.run(["sh", "/tmp/uv-install.sh"], env=env, capture_output=True)
        log_cb("uv installed.")
    else:
        log_cb("Warning: Could not download uv — install manually via pip later.")

    return True, "Python/Go toolchain installed."


def install_ollama(log_cb) -> tuple[bool, str]:
    """Install Ollama LLM runtime."""
    log_cb("Installing Ollama...")
    r = subprocess.run(
        ["curl", "-fsSL", "-o", "/tmp/ollama-install.sh", "https://ollama.com/install.sh"],
        capture_output=True, text=True, timeout=30
    )
    if r.returncode != 0:
        return False, "Could not download Ollama installer."

    # Run installer with OLLAMA_INSTALL_DIR pointing into chroot
    env = {**os.environ, "OLLAMA_INSTALL_DIR": f"{MOUNT_POINT}/usr/local/bin"}
    proc = subprocess.Popen(
        ["sh", "/tmp/ollama-install.sh"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, env=env,
    )
    for line in proc.stdout:
        log_cb(line.rstrip())
    proc.wait()

    if proc.returncode != 0:
        return False, "Ollama install failed."

    # Copy systemd service
    r = subprocess.run(
        ["cp", "-f", "/tmp/ollama.service", f"{MOUNT_POINT}/etc/systemd/system/ollama.service"],
        capture_output=True
    )
    chroot_run(["systemctl", "enable", "ollama"])
    log_cb("Ollama installed and enabled.")
    return True, "Ollama installed."


def add_user_to_groups(state: dict, log_cb) -> None:
    """Add the created user to all relevant groups."""
    username = state.get("username", "hermit")
    groups = ["sudo", "audio", "video", "plugdev", "netdev", "bluetooth", "incus-admin"]
    for group in groups:
        chroot_run(["usermod", "-aG", group, username])
        log_cb(f"Added {username} to group: {group}")


def install_hermetic_platform(prime_name: str, username: str, log_cb) -> tuple[bool, str]:
    """
    Install the Hermetic agent platform.
    Hermetic is the appliance-level agent runtime that runs the user's named Prime.
    The prime_name configures service names, config paths, and agent identity.
    """
    log_cb(f"Installing Hermetic agent platform (Prime: {prime_name.capitalize()})...")

    # Install Go (required to build Hermetic)
    log_cb("Ensuring Go is available...")
    r = chroot_run(["which", "go"])
    if r.returncode != 0:
        log_cb("Go not found — installing via apt...")
        chroot_stream(["apt-get", "install", "-y", "golang-go"], log_cb)

    # Install Python + uv for Hermetic's Python layer
    log_cb("Installing Python tooling for Hermetic...")
    chroot_stream(["apt-get", "install", "-y", "git", "python3", "python3-pip", "python3-venv", "pipx"], log_cb)

    # Clone Hermetic from Gitea (if available) or GitHub
    hermetic_dir = f"{MOUNT_POINT}/opt/hermetic"
    os.makedirs(hermetic_dir, exist_ok=True)

    hermetic_source = "https://github.com/bobbyhiddn/Hermetic.git"
    log_cb(f"Cloning Hermetic from {hermetic_source}...")
    r = subprocess.run(
        ["git", "clone", "--depth=1", hermetic_source, hermetic_dir],
        capture_output=True, text=True, timeout=120
    )
    if r.returncode != 0:
        log_cb(f"Could not clone Hermetic (may not be public yet): {r.stderr}")
        log_cb("Creating Hermetic placeholder config instead...")
        # Create a minimal config that can be completed post-install
        os.makedirs(f"{MOUNT_POINT}/etc/hermetic", exist_ok=True)
        config_content = f"""# Hermetic Agent Platform Configuration
# Generated by HermitOS Installer

agent:
  name: "{prime_name}"
  display_name: "{prime_name.capitalize()}"

service:
  # Service will be: {prime_name}.service
  user: "{username}"

database:
  name: "{prime_name}"
  host: "localhost"
  port: 5432

web:
  host: "0.0.0.0"
  port: 7777

# Complete configuration after first boot:
# See: /opt/hermetic/README.md
"""
        with open(f"{MOUNT_POINT}/etc/hermetic/{prime_name}.yaml", "w") as f:
            f.write(config_content)

        # Create a placeholder systemd service
        service_content = f"""[Unit]
Description=Hermetic Agent Platform — {prime_name.capitalize()}
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User={username}
WorkingDirectory=/opt/hermetic
ExecStart=/usr/local/bin/hermetic run {prime_name} --config /etc/hermetic/{prime_name}.yaml
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
"""
        with open(f"{MOUNT_POINT}/etc/systemd/system/{prime_name}.service", "w") as f:
            f.write(service_content)

        log_cb(f"Hermetic placeholder created. Config: /etc/hermetic/{prime_name}.yaml")
        log_cb(f"After first boot, run: hermetic setup {prime_name}")
        return True, f"Hermetic configured (prime: {prime_name}). Complete setup post-install."

    # If we got the source, try to build it
    log_cb("Building Hermetic binary...")
    env = {**os.environ, "HOME": "/root", "GOPATH": "/root/go", "PATH": "/usr/local/go/bin:/usr/sbin:/usr/bin:/sbin:/bin"}
    r = subprocess.run(
        ["chroot", MOUNT_POINT, "bash", "-c", f"cd /opt/hermetic && go build -o /usr/local/bin/hermetic ./cmd/hermetic"],
        capture_output=True, text=True, env=env, timeout=300
    )
    if r.returncode == 0:
        log_cb("Hermetic binary built successfully.")
    else:
        log_cb(f"Build warning: {r.stderr[:200]}")

    return True, f"Hermetic agent platform installed (prime: {prime_name})."


class HermitOSStackScreen(Screen):
    """Step 6 — HermitOS stack selection and installation."""

    _stack_done: bool = False

    def compose(self) -> ComposeResult:
        yield Static("  HermitOS Installer", classes="wizard-title")
        yield Static("Step 6 of 9 — Install Hermit", classes="step-indicator")
        with Container(classes="content-area"):
            with Vertical():
                with Container(id="selection_area"):
                    with Container(classes="info-box"):
                        yield Label("The Hermit stack will be installed:", classes="bold")
                        yield Label(
                            "These are the core components of your Hermit system.",
                            classes="muted"
                        )

                    yield Static("")

                    with Container(classes="info-box"):
                        yield Label("  KDE Plasma 6      Wayland desktop + Konsole + Dolphin (NVIDIA-ready)", classes="bold")

                    with Container(classes="info-box"):
                        yield Label("  Incus             LXC/LXD-compatible hypervisor for VMs & containers", classes="bold")

                    with Container(classes="info-box"):
                        yield Label("  K3s               Single-node Kubernetes — runs Gitea, services, etc.", classes="bold")

                    with Container(classes="info-box"):
                        yield Label("  Hermetic          The agent platform — runs your named Prime agent", classes="bold")

                    with Container(classes="info-box"):
                        yield Label("  uv + Go           Python package manager + Go 1.22 toolchain", classes="bold")

                    yield Static("")

                    with Container(classes="info-box"):
                        yield Label("Optional:", classes="bold")
                        yield Checkbox(
                            "Ollama (local LLM runtime — pull models after install)",
                            value=False, id="cb_ollama"
                        )

                with Container(id="install_area"):
                    yield RichLog(id="stack_log", highlight=True, markup=True, max_lines=300)

        with Horizontal(classes="button-bar"):
            yield Button("← Back", id="btn_back", classes="secondary")
            yield Button("Install Hermit →", id="btn_next", classes="primary")

    def on_mount(self) -> None:
        self.query_one("#install_area").display = False

    def _log(self, msg: str) -> None:
        app = self.app
        if app is None:
            return
        app.call_from_thread(self._append_log, msg)

    def _append_log(self, msg: str) -> None:
        self.query_one("#stack_log", RichLog).write(msg)

    @work(exclusive=True, thread=True)
    def run_stack_install(self, install_sway_: bool, install_incus_: bool,
                          install_k3s_: bool, install_hermetic_: bool,
                          install_ollama_: bool, install_devtools_: bool) -> None:
        app = self.app
        if app is None:
            return
        state = app.state

        self._log("[bold cyan]Starting HermitOS stack installation...[/bold cyan]\n")

        steps = []
        if install_sway_:
            steps.append(("KDE Plasma 6 desktop", install_desktop))
        if install_incus_:
            steps.append(("Incus hypervisor", install_incus))
        if install_k3s_:
            steps.append(("K3s Kubernetes", install_k3s_script))
        if install_hermetic_:
            prime = state.get("prime_name", "prime")
            username = state.get("username", "hermit")
            steps.append(("Hermetic agent platform",
                           lambda log_cb: install_hermetic_platform(prime, username, log_cb)))
        if install_ollama_:
            steps.append(("Ollama LLM runtime", install_ollama))
        if install_devtools_:
            steps.append(("uv + Go toolchain", install_uv_go))

        # Critical steps that must succeed (no desktop = unusable system)
        critical_steps = {"KDE Plasma 6 desktop"}

        for name, fn in steps:
            self._log(f"\n[bold cyan]▶ Installing: {name}[/bold cyan]")
            try:
                ok, msg = fn(self._log)
                if ok:
                    self._log(f"[green]✓ {name} complete: {msg}[/green]")
                else:
                    if name in critical_steps:
                        self._log(f"[bold red]✗ {name} FAILED: {msg}[/bold red]")
                        self._log(f"[bold red]  This is a critical component — installation cannot continue.[/bold red]")
                        app.call_from_thread(self._on_stack_failed, f"{name}: {msg}")
                        return
                    self._log(f"[yellow]⚠ {name} warning: {msg}[/yellow]")
            except Exception as e:
                if name in critical_steps:
                    self._log(f"[bold red]✗ {name} FAILED: {e}[/bold red]")
                    app.call_from_thread(self._on_stack_failed, str(e))
                    return
                self._log(f"[yellow]⚠ {name} failed: {e} (non-fatal, continuing)[/yellow]")

        # Always add user to groups
        self._log("\n[bold cyan]▶ Configuring user groups...[/bold cyan]")
        try:
            add_user_to_groups(state, self._log)
        except Exception as e:
            self._log(f"[yellow]⚠ Group config warning: {e}[/yellow]")

        state["stack_done"] = True
        app.call_from_thread(self._on_stack_done)

    def _on_stack_failed(self, msg: str) -> None:
        self.query_one("#stack_log", RichLog).write(
            f"\n[bold red]✗ Stack installation failed: {msg}[/bold red]\n"
            "[bold red]Fix the issue and retry.[/bold red]"
        )
        btn = self.query_one("#btn_next", Button)
        btn.label = "Retry"
        btn.disabled = False
        btn.focus()

    def _on_stack_done(self) -> None:
        self._stack_done = True
        self.query_one("#stack_log", RichLog).write(
            "\n[bold green]✓ HermitOS stack installation complete![/bold green]"
        )
        btn = self.query_one("#btn_next", Button)
        btn.label = "Continue → Shore Registration"
        btn.disabled = False
        btn.focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn_back":
            self.app.go_back()
        elif event.button.id == "btn_next":
            if self._stack_done:
                self.app.go_next("shore_register")
                return

            # Core components are always installed
            self.app.state["install_sway"] = True
            self.app.state["install_incus"] = True
            self.app.state["install_k3s"] = True
            self.app.state["install_nvidia"] = False  # set in nvidia screen
            self.app.state["install_hermetic"] = True

            install_sway_ = True
            install_incus_ = True
            install_k3s_ = True
            install_hermetic_ = True
            install_ollama_ = self.query_one("#cb_ollama", Checkbox).value
            install_devtools_ = True

            self.query_one("#selection_area").display = False
            self.query_one("#install_area").display = True
            self.query_one("#btn_back").disabled = True
            self.query_one("#btn_next", Button).disabled = True
            self.query_one("#btn_next", Button).label = "Installing..."

            self.run_stack_install(
                install_sway_, install_incus_,
                install_k3s_, install_hermetic_, install_ollama_, install_devtools_
            )
