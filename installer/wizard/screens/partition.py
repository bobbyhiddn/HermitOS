"""Step 4 — Partitioning screen."""

import subprocess
from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Button, Static, Label, Select, Switch, Input
from textual.containers import Container, Vertical, Horizontal
from textual.worker import get_current_worker
from textual import work


def get_drive_size_gb(dev_path: str) -> float:
    """Get drive size in GB."""
    result = subprocess.run(
        ["lsblk", "-b", "-d", "-o", "SIZE", "--noheadings", dev_path],
        capture_output=True, text=True
    )
    try:
        size_bytes = int(result.stdout.strip())
        return size_bytes / (1024 ** 3)
    except (ValueError, AttributeError):
        return 0.0


def do_partition(dev_path: str, scheme: str, swap_mb: int = 0) -> tuple[bool, str]:
    """
    Partition the drive.
    scheme: "simple" = EFI + root only
            "home"   = EFI + root + home
            "swap"   = EFI + swap + root
    Returns (success, message)
    """
    log_lines = []

    def log(msg: str) -> None:
        log_lines.append(msg)

    try:
        # Wipe existing partition table
        log(f"Wiping {dev_path}...")
        subprocess.run(["wipefs", "-a", dev_path], check=True, capture_output=True)
        subprocess.run(["sgdisk", "--zap-all", dev_path], capture_output=True)

        # Create GPT partition table
        log("Creating GPT partition table...")
        cmds = [
            # EFI partition: 512M
            ["sgdisk", "-n", "1:0:+512M", "-t", "1:ef00", "-c", "1:EFI", dev_path],
        ]

        part_num = 2
        if scheme == "swap" and swap_mb > 0:
            cmds.append([
                "sgdisk", "-n", f"{part_num}:0:+{swap_mb}M",
                "-t", f"{part_num}:8200", "-c", f"{part_num}:swap", dev_path
            ])
            part_num += 1

        if scheme == "home":
            # Root: 40G, then rest for /home
            cmds.append([
                "sgdisk", "-n", f"{part_num}:0:+40G",
                "-t", f"{part_num}:8300", "-c", f"{part_num}:root", dev_path
            ])
            part_num += 1
            cmds.append([
                "sgdisk", "-n", f"{part_num}:0:0",
                "-t", f"{part_num}:8300", "-c", f"{part_num}:home", dev_path
            ])
        else:
            # Root: fill remaining
            cmds.append([
                "sgdisk", "-n", f"{part_num}:0:0",
                "-t", f"{part_num}:8300", "-c", f"{part_num}:root", dev_path
            ])

        for cmd in cmds:
            log(f"Running: {' '.join(cmd)}")
            subprocess.run(cmd, check=True, capture_output=True)

        # Inform kernel of new partition table
        subprocess.run(["partprobe", dev_path], capture_output=True)
        subprocess.run(["sleep", "2"])
        subprocess.run(["udevadm", "settle"], capture_output=True)

        # Determine partition names (nvme uses p1, p2; sda uses 1, 2)
        is_nvme = "nvme" in dev_path
        p = "p" if is_nvme else ""

        efi_part = f"{dev_path}{p}1"
        part_num = 2

        swap_part = ""
        if scheme == "swap" and swap_mb > 0:
            swap_part = f"{dev_path}{p}{part_num}"
            part_num += 1

        root_part = f"{dev_path}{p}{part_num}"
        home_part = ""
        if scheme == "home":
            part_num += 1
            home_part = f"{dev_path}{p}{part_num}"

        # Format partitions
        log(f"Formatting EFI partition {efi_part} as FAT32...")
        subprocess.run(["mkfs.fat", "-F32", "-n", "EFI", efi_part], check=True, capture_output=True)

        if swap_part:
            log(f"Formatting swap partition {swap_part}...")
            subprocess.run(["mkswap", "-L", "swap", swap_part], check=True, capture_output=True)

        log(f"Formatting root partition {root_part} as ext4...")
        subprocess.run(
            ["mkfs.ext4", "-L", "hermit-root", "-F", root_part],
            check=True, capture_output=True
        )

        if home_part:
            log(f"Formatting home partition {home_part} as ext4...")
            subprocess.run(
                ["mkfs.ext4", "-L", "hermit-home", "-F", home_part],
                check=True, capture_output=True
            )

        return True, f"Partitioned successfully.\n" + "\n".join(log_lines)

    except subprocess.CalledProcessError as e:
        return False, f"Command failed: {e.cmd}\n{e.stderr}\n\n{''.join(log_lines)}"
    except Exception as e:
        return False, f"Error: {e}\n\n{''.join(log_lines)}"


class PartitionScreen(Screen):
    """Step 4 — Partitioning configuration and execution."""

    def compose(self) -> ComposeResult:
        yield Static("  HermitOS Installer", classes="wizard-title")
        yield Static("Step 4 of 9 — Partitioning", classes="step-indicator")
        with Container(classes="content-area"):
            with Vertical():
                with Container(id="config_area"):
                    with Container(classes="info-box"):
                        target = self.app.state.get("target_drive", "?")
                        size = get_drive_size_gb(target)
                        yield Label(f"Target drive: {target} ({size:.1f} GB)", classes="bold")
                        yield Label("")
                        yield Label("Default partition scheme:")
                        yield Label("  • Partition 1: 512 MB  — EFI System (FAT32)")
                        yield Label("  • Partition 2: remainder — Root filesystem (ext4)")

                    yield Static("")
                    yield Label("Partition Scheme:", classes="bold")
                    yield Select(
                        [
                            ("Simple: EFI + Root (recommended)", "simple"),
                            ("With Swap: EFI + Swap + Root", "swap"),
                            ("With /home: EFI + Root (40G) + /home", "home"),
                        ],
                        id="scheme_select",
                        value="simple",
                    )

                    with Container(id="swap_config"):
                        yield Static("")
                        yield Label("Swap size (MB):")
                        yield Input(value="4096", id="swap_size", placeholder="e.g. 4096 for 4GB")

                with Container(id="progress_area"):
                    yield Static("", id="progress_log", classes="info-box")

        with Horizontal(classes="button-bar"):
            yield Button("← Back", id="btn_back", classes="secondary")
            yield Button("Partition & Format Drive →", id="btn_next", classes="primary")

    def on_mount(self) -> None:
        self.query_one("#swap_config").display = False
        self.query_one("#progress_area").display = False
        # Idempotency: if partitioning was already completed, show success state
        if self.app.state.get("root_partition"):
            self._partitioned = True
            self.query_one("#config_area").display = False
            self.query_one("#progress_area").display = True
            target = self.app.state.get("target_drive", "?")
            efi = self.app.state.get("efi_partition", "?")
            root = self.app.state.get("root_partition", "?")
            log = self.query_one("#progress_log", Static)
            log.update(
                f"✓ Partitioning already complete!\n\n"
                f"Drive: {target}\n"
                f"EFI:   {efi}\n"
                f"Root:  {root}"
            )
            log.remove_class("info-box")
            log.add_class("success-box")
            btn = self.query_one("#btn_next", Button)
            btn.label = "Continue →"
            btn.focus()

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "scheme_select":
            show_swap = (event.value == "swap")
            self.query_one("#swap_config").display = show_swap

    @work(exclusive=True, thread=True)
    def run_partitioning(self, dev_path: str, scheme: str, swap_mb: int) -> None:
        """Background: execute partitioning."""
        app = self.app
        if app is None:
            return
        app.call_from_thread(self._update_log, "Starting partitioning... please wait.")

        ok, msg = do_partition(dev_path, scheme, swap_mb)

        if ok:
            # Store partition paths in state (via main thread)
            is_nvme = "nvme" in dev_path
            p = "p" if is_nvme else ""

            def _save_partition_state():
                self.app.state["efi_partition"] = f"{dev_path}{p}1"
                part_num = 2
                if scheme == "swap" and swap_mb > 0:
                    part_num = 3
                self.app.state["root_partition"] = f"{dev_path}{p}{part_num}"
                if scheme == "home":
                    self.app.state["home_partition"] = f"{dev_path}{p}{part_num + 1}"
                if scheme == "swap":
                    self.app.state["swap_size_mb"] = swap_mb

            app.call_from_thread(_save_partition_state)
            app.call_from_thread(self._on_partition_success, msg)
        else:
            app.call_from_thread(self._on_partition_error, msg)

    def _update_log(self, msg: str) -> None:
        self.query_one("#progress_log", Static).update(msg)

    def _on_partition_success(self, msg: str) -> None:
        log = self.query_one("#progress_log", Static)
        log.update(f"✓ Partitioning complete!\n\n{msg}")
        log.remove_class("info-box")
        log.add_class("success-box")
        btn = self.query_one("#btn_next", Button)
        btn.label = "Continue →"
        btn.disabled = False
        btn.focus()
        self._partitioned = True

    def _on_partition_error(self, msg: str) -> None:
        log = self.query_one("#progress_log", Static)
        log.update(f"✗ Partitioning failed!\n\n{msg}")
        log.remove_class("info-box")
        log.add_class("error-box")

    _partitioned: bool = False

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn_back":
            self.app.go_back()
        elif event.button.id == "btn_next":
            if self._partitioned:
                self.app.go_next("user_account")  # Step 8: set up user/hostname before installing
                return

            target = self.app.state.get("target_drive", "")
            if not target:
                return

            scheme_select = self.query_one("#scheme_select", Select)
            scheme = scheme_select.value or "simple"

            swap_mb = 0
            if scheme == "swap":
                try:
                    swap_mb = int(self.query_one("#swap_size", Input).value)
                except ValueError:
                    swap_mb = 4096

            self.query_one("#config_area").display = False
            self.query_one("#progress_area").display = True
            self.query_one("#btn_next", Button).disabled = True

            self.run_partitioning(target, str(scheme), swap_mb)
