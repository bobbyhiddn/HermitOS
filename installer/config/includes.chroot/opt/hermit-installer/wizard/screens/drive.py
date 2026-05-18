"""Step 3 — Drive selection screen."""

import subprocess
import re
from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Button, Static, Label, DataTable, Select
from textual.containers import Container, Vertical, Horizontal
from textual.worker import get_current_worker
from textual import work


def get_block_devices() -> list[dict]:
    """Get all block devices using lsblk."""
    result = subprocess.run(
        ["lsblk", "-d", "-o", "NAME,SIZE,MODEL,TRAN,TYPE", "--json"],
        capture_output=True, text=True
    )
    devices = []
    if result.returncode == 0:
        import json
        try:
            data = json.loads(result.stdout)
            for dev in data.get("blockdevices", []):
                if dev.get("type") != "disk":
                    continue
                name = dev.get("name", "")
                # Skip USB drives (likely our installer)
                tran = dev.get("tran", "") or ""
                # Skip loop devices
                if name.startswith("loop"):
                    continue
                devices.append({
                    "name": name,
                    "path": f"/dev/{name}",
                    "size": dev.get("size", "?"),
                    "model": (dev.get("model") or "Unknown").strip(),
                    "tran": tran.upper() if tran else "?",
                })
        except json.JSONDecodeError:
            pass

    # Fallback: parse text output
    if not devices:
        result = subprocess.run(
            ["lsblk", "-d", "-o", "NAME,SIZE,MODEL,TRAN", "--noheadings"],
            capture_output=True, text=True
        )
        for line in result.stdout.splitlines():
            parts = line.split()
            if not parts:
                continue
            name = parts[0]
            if name.startswith("loop") or name.startswith("sr"):
                continue
            size = parts[1] if len(parts) > 1 else "?"
            model = " ".join(parts[2:-1]) if len(parts) > 3 else "Unknown"
            tran = parts[-1].upper() if len(parts) > 2 else "?"
            devices.append({
                "name": name,
                "path": f"/dev/{name}",
                "size": size,
                "model": model.strip() or "Unknown",
                "tran": tran,
            })

    return devices


def get_partition_info(dev_path: str) -> str:
    """Get a summary of existing partitions on the device."""
    result = subprocess.run(
        ["lsblk", "-o", "NAME,SIZE,TYPE,FSTYPE,MOUNTPOINT", dev_path],
        capture_output=True, text=True
    )
    if result.returncode == 0:
        lines = result.stdout.strip().splitlines()
        if len(lines) > 1:
            return "\n".join(lines[1:])
    return "No partition info available"


def has_existing_data(dev_path: str) -> bool:
    """Returns True if the device has existing partitions."""
    result = subprocess.run(
        ["lsblk", "-n", "-o", "TYPE", dev_path],
        capture_output=True, text=True
    )
    for line in result.stdout.splitlines():
        if line.strip() == "part":
            return True
    return False


class DriveScreen(Screen):
    """Step 3 — Drive selection."""

    _devices: list[dict] = []
    _selected_device: dict | None = None

    def compose(self) -> ComposeResult:
        yield Static("  HermitOS Installer", classes="wizard-title")
        yield Static("Step 3 of 9 — Drive Selection", classes="step-indicator")
        with Container(classes="content-area"):
            with Vertical():
                with Container(classes="warning-box"):
                    yield Label(
                        "⚠  All data on the selected drive will be PERMANENTLY ERASED. "
                        "Choose carefully."
                    )
                yield Static("")
                yield Label("Available drives:", classes="bold")
                yield DataTable(id="drive_table", show_cursor=True)
                yield Static("", id="drive_detail")
                yield Static("", id="selection_status")

        with Horizontal(classes="button-bar"):
            yield Button("← Back", id="btn_back", classes="secondary")
            yield Button("Refresh", id="btn_refresh", classes="secondary")
            yield Button("Select Drive →", id="btn_next", classes="primary")

    def on_mount(self) -> None:
        table = self.query_one("#drive_table", DataTable)
        table.add_columns("Device", "Size", "Interface", "Model")
        self.load_drives()
        # Focus the table so arrow keys work immediately
        table.focus()

    @work(exclusive=True, thread=True)
    def load_drives(self) -> None:
        app = self.app
        if app is None:
            return
        devices = get_block_devices()
        self._devices = devices
        app.call_from_thread(self._populate_table, devices)

    def _populate_table(self, devices: list[dict]) -> None:
        table = self.query_one("#drive_table", DataTable)
        table.clear()
        if not devices:
            self.query_one("#selection_status", Static).update(
                "No drives detected. Check hardware connections."
            )
            return

        for dev in devices:
            has_data = has_existing_data(dev["path"])
            warning = " ⚠ DATA" if has_data else ""
            table.add_row(
                dev["path"],
                dev["size"],
                dev["tran"],
                dev["model"] + warning,
                key=dev["path"],
            )

        self.query_one("#selection_status", Static).update(
            "Use ↑/↓ to highlight a drive, Enter to select it, then press 'Select Drive'."
        )
        # Re-focus table AFTER rows are populated so cursor keys work
        table.focus()
        # Move cursor to first row so it's visibly highlighted
        if devices:
            table.move_cursor(row=0)

    def _show_drive_detail(self, dev_path: str) -> None:
        """Show partition detail for the given drive path."""
        dev = None
        for d in self._devices:
            if d["path"] == dev_path:
                dev = d
                break
        if not dev:
            return

        has_data = has_existing_data(dev_path)
        part_info = get_partition_info(dev_path)

        detail = self.query_one("#drive_detail", Static)
        if has_data:
            detail.update(
                f"Highlighted: {dev_path} ({dev['size']})\n\n"
                f"⚠  This drive has existing partitions:\n{part_info}"
            )
            detail.remove_class("success-box")
            detail.add_class("warning-box")
        else:
            detail.update(
                f"Highlighted: {dev_path} ({dev['size']})\n"
                f"Drive appears empty — no existing partitions."
            )
            detail.remove_class("warning-box")
            detail.add_class("success-box")

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        """Show detail as user navigates with arrow keys."""
        if event.row_key is not None:
            self._show_drive_detail(str(event.row_key.value))

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle drive selection (Enter key) from the table."""
        dev_path = str(event.row_key.value)
        for dev in self._devices:
            if dev["path"] == dev_path:
                self._selected_device = dev
                break

        if not self._selected_device:
            return

        self._show_drive_detail(dev_path)

        self.query_one("#selection_status", Static).update(
            f"→ {dev_path} selected. Press 'Select Drive' to continue."
        )
        # Focus the continue button so Tab+Enter or Enter proceeds
        self.query_one("#btn_next", Button).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn_back":
            self.app.go_back()
        elif event.button.id == "btn_refresh":
            self._devices = []
            self._selected_device = None
            table = self.query_one("#drive_table", DataTable)
            table.clear()
            self.load_drives()
        elif event.button.id == "btn_next":
            self._confirm_selection()

    def _confirm_selection(self) -> None:
        if not self._selected_device:
            self.query_one("#selection_status", Static).update(
                "⚠  Please select a drive first."
            )
            return

        dev = self._selected_device
        has_data = has_existing_data(dev["path"])

        # Push confirmation screen
        from screens.drive_confirm import DriveConfirmScreen
        self.app.push_screen(
            DriveConfirmScreen(dev, has_data),
            callback=self._on_confirm_result,
        )

    def _on_confirm_result(self, confirmed: bool) -> None:
        if confirmed:
            self.app.state["target_drive"] = self._selected_device["path"]
            self.app.go_next("partition")
