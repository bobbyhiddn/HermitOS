#!/usr/bin/env python3
"""
HermitOS Installer Wizard
A terminal UI installer that guides users through setting up HermitOS.
Built with Textual. Must run as root.

12-Step Installation Flow:
  1.  Welcome
  2.  Language & Locale
  3.  Timezone
  4.  Network
  5.  Name Your Prime (agent identity)
  6.  Drive Selection
  7.  Partitioning
  8.  User Account
  9.  Base System Install (debootstrap)
  10. HermitOS Stack (Sway, Incus, K3s, Hermetic, Ollama)
  11. Shore Registration (prime tile in Shore dashboard)
  12. Bootloader (GRUB EFI)
  (+) Nvidia Detection (auto, after bootloader)
  (+) Complete
"""

import sys
import os

# Must run as root
if os.geteuid() != 0:
    print("Error: The HermitOS installer must run as root.")
    print("Run: sudo python3 /opt/hermit-installer/wizard/main.py")
    sys.exit(1)

from textual.app import App, ComposeResult
from textual.screen import Screen

from screens.welcome import WelcomeScreen
from screens.locale import LocaleScreen
from screens.timezone import TimezoneScreen
from screens.network import NetworkScreen
from screens.prime_name import PrimeNameScreen
from screens.drive import DriveScreen
from screens.partition import PartitionScreen
from screens.user_account import UserAccountScreen
from screens.base_install import BaseInstallScreen
from screens.hermitos_stack import HermitOSStackScreen
from screens.shore_register import ShoreRegisterScreen
from screens.bootloader import BootloaderScreen
from screens.nvidia import NvidiaScreen
from screens.complete import CompleteScreen


SCREEN_REGISTRY = {
    "welcome":        WelcomeScreen,
    "locale":         LocaleScreen,
    "timezone":       TimezoneScreen,
    "network":        NetworkScreen,
    "prime_name":     PrimeNameScreen,
    "drive":          DriveScreen,
    "partition":      PartitionScreen,
    "user_account":   UserAccountScreen,
    "base_install":   BaseInstallScreen,
    "hermitos_stack": HermitOSStackScreen,
    "shore_register": ShoreRegisterScreen,
    "bootloader":     BootloaderScreen,
    "nvidia":         NvidiaScreen,
    "complete":       CompleteScreen,
}


class HermitInstaller(App):
    """
    The HermitOS installer application.

    CSS uses a dark GitHub-inspired palette:
      Background: #0d1117  (GitHub dark)
      Primary:    #58a6ff  (blue)
      Success:    #3fb950  (green)
      Warning:    #e3b341  (amber)
      Danger:     #f85149  (red)
    """

    CSS = """
    Screen {
        background: #0d1117;
    }

    .wizard-title {
        text-align: center;
        color: #58a6ff;
        text-style: bold;
        padding: 1 2;
        background: #161b22;
        border-bottom: solid #30363d;
    }

    .wizard-subtitle {
        text-align: center;
        color: #8b949e;
        padding: 0 2 1 2;
    }

    .step-indicator {
        text-align: center;
        color: #3fb950;
        background: #161b22;
        padding: 0 2;
        border-bottom: solid #21262d;
    }

    .content-area {
        padding: 1 4;
        height: 1fr;
        overflow-y: auto;
    }

    .button-bar {
        dock: bottom;
        height: 5;
        padding: 1 4;
        layout: horizontal;
        align: center middle;
        background: #161b22;
        border-top: solid #30363d;
    }

    Button {
        margin: 0 2;
        min-width: 16;
    }

    Button.primary {
        background: #238636;
        color: white;
        border: tall #2ea043;
    }

    Button.primary:hover {
        background: #2ea043;
    }

    Button.secondary {
        background: #21262d;
        color: #c9d1d9;
        border: tall #30363d;
    }

    Button.secondary:hover {
        background: #30363d;
    }

    Button.danger {
        background: #b62324;
        color: white;
        border: tall #da3633;
    }

    Button.danger:hover {
        background: #da3633;
    }

    .info-box {
        background: #161b22;
        border: solid #30363d;
        padding: 1 2;
        margin: 1 0;
    }

    .warning-box {
        background: #2d1b00;
        border: solid #e3b341;
        padding: 1 2;
        margin: 1 0;
        color: #e3b341;
    }

    .success-box {
        background: #0d1f0d;
        border: solid #3fb950;
        padding: 1 2;
        margin: 1 0;
        color: #3fb950;
    }

    .error-box {
        background: #1f0d0d;
        border: solid #f85149;
        padding: 1 2;
        margin: 1 0;
        color: #f85149;
    }

    Label {
        color: #c9d1d9;
    }

    .muted {
        color: #8b949e;
    }

    .bold {
        text-style: bold;
    }

    .hermit-logo {
        text-align: center;
        color: #58a6ff;
        padding: 1;
        background: #0d1117;
    }

    Input {
        background: #0d1117;
        border: tall #30363d;
        color: #c9d1d9;
        margin: 0 0 1 0;
    }

    Input:focus {
        border: tall #58a6ff;
    }

    Select {
        background: #0d1117;
        border: tall #30363d;
        margin: 0 0 1 0;
    }

    DataTable {
        background: #0d1117;
        border: solid #30363d;
        margin: 1 0;
        height: 12;
    }

    DataTable > .datatable--header {
        background: #161b22;
        color: #58a6ff;
    }

    DataTable > .datatable--cursor {
        background: #1f4a8a;
    }

    Checkbox {
        color: #c9d1d9;
        margin: 0 0 1 0;
    }

    Checkbox:focus {
        border: none;
    }

    RichLog {
        background: #0d1117;
        border: solid #21262d;
        height: 1fr;
        padding: 1;
    }

    LoadingIndicator {
        color: #58a6ff;
    }
    """

    TITLE = "HermitOS Installer"

    def __init__(self):
        super().__init__()
        self.state: dict = {
            # Locale
            "locale": "en_US.UTF-8",
            "keyboard": "us",
            "timezone": "America/Chicago",
            # Prime agent identity
            "prime_name": "",           # e.g. "nova"
            "prime_name_display": "",   # e.g. "Nova"
            # Network
            "network_connected": False,
            "network_interface": "",
            "network_type": "",         # "ethernet" | "wifi"
            # Drive
            "target_drive": "",         # e.g. "/dev/nvme0n1"
            # Partitioning
            "efi_partition": "",
            "root_partition": "",
            "home_partition": "",
            "swap_size_mb": 0,
            # User account
            "hostname": "hermit",
            "username": "hermit",
            "password": "",
            # Stack selection
            "install_k3s": True,
            "install_incus": True,
            "install_sway": True,
            "install_hermetic": True,
            "install_ollama": False,
            "install_nvidia": False,
            # Shore registration
            "prime_port": 7777,
            "shore_url": "http://localhost:7778",
            # Progress flags
            "debootstrap_done": False,
            "stack_done": False,
            "grub_done": False,
        }

    def on_mount(self) -> None:
        self.push_screen(WelcomeScreen())

    def go_next(self, screen_name: str) -> None:
        """Navigate forward to a named screen."""
        if screen_name in SCREEN_REGISTRY:
            self.push_screen(SCREEN_REGISTRY[screen_name]())
        else:
            raise ValueError(f"Unknown screen: {screen_name}")

    def go_back(self) -> None:
        """Return to the previous screen."""
        self.pop_screen()


def main():
    app = HermitInstaller()
    app.run()


if __name__ == "__main__":
    main()
