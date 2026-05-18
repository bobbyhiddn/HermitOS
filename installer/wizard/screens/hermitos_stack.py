"""Step 6 — HermitOS stack selection and installation."""

import subprocess
import os
from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Button, Static, Label, Checkbox, RichLog, Switch
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


def install_hyprland(log_cb) -> tuple[bool, str]:
    """Install Hyprland desktop environment."""
    packages = [
        "hyprland",
        "waybar",
        "wofi",
        "foot",
        "grim",
        "slurp",
        "wl-clipboard",
        "xdg-desktop-portal-hyprland",
        "xdg-desktop-portal-gtk",
        "pipewire",
        "pipewire-pulse",
        "wireplumber",
        "pavucontrol",
        "thunar",
        "firefox-esr",
        "swaybg",
        "swaylock",
        "mako-notifier",
        "brightnessctl",
        "playerctl",
        "polkit-gnome",
        "noto-fonts",
        "fonts-noto-color-emoji",
    ]
    log_cb("Installing Hyprland desktop environment...")
    rc = chroot_stream(
        ["apt-get", "install", "-y", "--no-install-recommends"] + packages,
        log_cb
    )
    if rc != 0:
        return False, "Hyprland installation failed."

    # Write a minimal Hyprland config
    hypr_cfg_dir = f"{MOUNT_POINT}/etc/skel/.config/hypr"
    os.makedirs(hypr_cfg_dir, exist_ok=True)
    with open(f"{hypr_cfg_dir}/hyprland.conf", "w") as f:
        f.write("""# HermitOS Hyprland Configuration
monitor=,preferred,auto,1

exec-once=waybar
exec-once=swaybg -c "#0d1117"
exec-once=/usr/lib/polkit-gnome/polkit-gnome-authentication-agent-1

input {
    kb_layout = us
    follow_mouse = 1
    touchpad {
        natural_scroll = yes
    }
    sensitivity = 0
}

general {
    gaps_in = 5
    gaps_out = 10
    border_size = 2
    col.active_border = rgba(58a6ffee)
    col.inactive_border = rgba(21262dee)
    layout = dwindle
}

decoration {
    rounding = 8
    blur {
        enabled = true
        size = 6
        passes = 3
    }
    drop_shadow = yes
    shadow_range = 10
    shadow_render_power = 3
    col.shadow = rgba(1a1a1aee)
}

animations {
    enabled = yes
    bezier = easeOut, 0.05, 0.9, 0.1, 1.05
    animation = windows, 1, 5, easeOut
    animation = fade, 1, 7, default
    animation = workspaces, 1, 6, default
}

dwindle {
    pseudotile = yes
    preserve_split = yes
}

# Key bindings
$mainMod = SUPER
bind = $mainMod, Return, exec, foot
bind = $mainMod, Q, killactive,
bind = $mainMod, M, exit,
bind = $mainMod, E, exec, thunar
bind = $mainMod, Space, exec, wofi --show drun
bind = $mainMod, F, fullscreen
bind = $mainMod SHIFT, Space, togglefloating

# Workspace binds
bind = $mainMod, 1, workspace, 1
bind = $mainMod, 2, workspace, 2
bind = $mainMod, 3, workspace, 3
bind = $mainMod, 4, workspace, 4
bind = $mainMod, 5, workspace, 5

bind = $mainMod SHIFT, 1, movetoworkspace, 1
bind = $mainMod SHIFT, 2, movetoworkspace, 2
bind = $mainMod SHIFT, 3, movetoworkspace, 3
bind = $mainMod SHIFT, 4, movetoworkspace, 4
bind = $mainMod SHIFT, 5, movetoworkspace, 5

# Scroll through workspaces
bind = $mainMod, mouse_down, workspace, e+1
bind = $mainMod, mouse_up, workspace, e-1

# Volume keys
binde = , XF86AudioRaiseVolume, exec, pactl set-sink-volume @DEFAULT_SINK@ +5%
binde = , XF86AudioLowerVolume, exec, pactl set-sink-volume @DEFAULT_SINK@ -5%
bind = , XF86AudioMute, exec, pactl set-sink-mute @DEFAULT_SINK@ toggle

# Screenshot
bind = , Print, exec, grim -g "$(slurp)" - | wl-copy
""")

    log_cb("Hyprland configured.")
    return True, "Hyprland installed."


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
    chroot_stream(["apt-get", "install", "-y", "python3", "python3-pip", "python3-venv", "pipx"], log_cb)

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

[agent]
name = "{prime_name}"
display_name = "{prime_name.capitalize()}"

[service]
# Service will be: {prime_name}.service
user = "{username}"

[database]
name = "{prime_name}"
host = "localhost"
port = 5432

[web]
host = "0.0.0.0"
port = 7777

# Complete configuration after first boot:
# See: /opt/hermetic/README.md
"""
        with open(f"{MOUNT_POINT}/etc/hermetic/{prime_name}.toml", "w") as f:
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
EnvironmentFile=-/etc/hermetic/{prime_name}.toml
ExecStart=/usr/local/bin/hermetic run {prime_name}
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
"""
        with open(f"{MOUNT_POINT}/etc/systemd/system/{prime_name}.service", "w") as f:
            f.write(service_content)

        log_cb(f"Hermetic placeholder created. Config: /etc/hermetic/{prime_name}.toml")
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
        yield Static("Step 6 of 9 — HermitOS Stack", classes="step-indicator")
        with Container(classes="content-area"):
            with Vertical():
                with Container(id="selection_area"):
                    with Container(classes="info-box"):
                        yield Label("Select components to install:", classes="bold")
                        yield Label(
                            "All checked items will be downloaded and installed. "
                            "You can add/remove components later.",
                            classes="muted"
                        )

                    yield Static("")

                    with Container(classes="info-box"):
                        yield Label("🖥  Desktop Environment", classes="bold")
                        yield Checkbox(
                            "Hyprland (Wayland compositor + Waybar + Wofi + Foot terminal)",
                            value=True, id="cb_hyprland"
                        )

                    yield Static("")

                    with Container(classes="info-box"):
                        yield Label("🔧  Virtualization", classes="bold")
                        yield Checkbox(
                            "Incus (LXC/LXD-compatible hypervisor for VMs & containers)",
                            value=True, id="cb_incus"
                        )

                    yield Static("")

                    with Container(classes="info-box"):
                        yield Label("☸  Orchestration", classes="bold")
                        yield Checkbox(
                            "K3s (single-node Kubernetes — runs Gitea, services, etc.)",
                            value=True, id="cb_k3s"
                        )

                    yield Static("")

                    with Container(classes="info-box"):
                        yield Label("🤖  Agent Platform", classes="bold")
                        yield Checkbox(
                            "Hermetic (the agent platform — runs your named Prime agent)",
                            value=True, id="cb_hermetic"
                        )

                    yield Static("")

                    with Container(classes="info-box"):
                        yield Label("🧠  AI / LLM", classes="bold")
                        yield Checkbox(
                            "Ollama (local LLM runtime — pull models after install)",
                            value=False, id="cb_ollama"
                        )

                    yield Static("")

                    with Container(classes="info-box"):
                        yield Label("🐍  Developer Tools", classes="bold")
                        yield Checkbox(
                            "uv + Go toolchain (Python package manager + Go 1.22)",
                            value=True, id="cb_devtools"
                        )

                with Container(id="install_area"):
                    yield RichLog(id="stack_log", highlight=True, markup=True, max_lines=300)

        with Horizontal(classes="button-bar"):
            yield Button("← Back", id="btn_back", classes="secondary")
            yield Button("Install Selected Components →", id="btn_next", classes="primary")

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
    def run_stack_install(self, install_hyprland_: bool, install_incus_: bool,
                          install_k3s_: bool, install_hermetic_: bool,
                          install_ollama_: bool, install_devtools_: bool) -> None:
        app = self.app
        if app is None:
            return
        state = app.state

        self._log("[bold cyan]Starting HermitOS stack installation...[/bold cyan]\n")

        steps = []
        if install_hyprland_:
            steps.append(("Hyprland desktop", install_hyprland))
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

        for name, fn in steps:
            self._log(f"\n[bold cyan]▶ Installing: {name}[/bold cyan]")
            try:
                ok, msg = fn(self._log)
                if ok:
                    self._log(f"[green]✓ {name} complete: {msg}[/green]")
                else:
                    self._log(f"[yellow]⚠ {name} warning: {msg}[/yellow]")
            except Exception as e:
                self._log(f"[yellow]⚠ {name} failed: {e} (non-fatal, continuing)[/yellow]")

        # Always add user to groups
        self._log("\n[bold cyan]▶ Configuring user groups...[/bold cyan]")
        try:
            add_user_to_groups(state, self._log)
        except Exception as e:
            self._log(f"[yellow]⚠ Group config warning: {e}[/yellow]")

        state["stack_done"] = True
        app.call_from_thread(self._on_stack_done)

    def _on_stack_done(self) -> None:
        self._stack_done = True
        self.query_one("#stack_log", RichLog).write(
            "\n[bold green]✓ HermitOS stack installation complete![/bold green]"
        )
        btn = self.query_one("#btn_next", Button)
        btn.label = "Continue → Shore Registration"
        btn.disabled = False

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn_back":
            self.app.go_back()
        elif event.button.id == "btn_next":
            if self._stack_done:
                self.app.go_next("shore_register")
                return

            # Save selections to state
            self.app.state["install_hyprland"] = self.query_one("#cb_hyprland", Checkbox).value
            self.app.state["install_incus"] = self.query_one("#cb_incus", Checkbox).value
            self.app.state["install_k3s"] = self.query_one("#cb_k3s", Checkbox).value
            self.app.state["install_nvidia"] = False  # set in nvidia screen

            install_hyprland_ = self.query_one("#cb_hyprland", Checkbox).value
            install_incus_ = self.query_one("#cb_incus", Checkbox).value
            install_k3s_ = self.query_one("#cb_k3s", Checkbox).value
            install_hermetic_ = self.query_one("#cb_hermetic", Checkbox).value
            install_ollama_ = self.query_one("#cb_ollama", Checkbox).value
            install_devtools_ = self.query_one("#cb_devtools", Checkbox).value

            self.app.state["install_hermetic"] = install_hermetic_

            self.query_one("#selection_area").display = False
            self.query_one("#install_area").display = True
            self.query_one("#btn_back").disabled = True
            self.query_one("#btn_next", Button).disabled = True
            self.query_one("#btn_next", Button).label = "Installing..."

            self.run_stack_install(
                install_hyprland_, install_incus_,
                install_k3s_, install_hermetic_, install_ollama_, install_devtools_
            )
