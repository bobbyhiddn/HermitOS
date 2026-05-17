"""Step 2 — Network setup screen."""

import subprocess
import re
from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Button, Static, Label, Select, Input, LoadingIndicator
from textual.containers import Container, Vertical, Horizontal
from textual.worker import Worker, get_current_worker
from textual import work


def run_cmd(cmd: list[str], timeout: int = 30) -> tuple[int, str, str]:
    """Run a command, return (returncode, stdout, stderr)."""
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except subprocess.TimeoutExpired:
        return -1, "", "Command timed out"
    except Exception as e:
        return -1, "", str(e)


def get_interfaces() -> list[dict]:
    """Get network interfaces via 'ip link'."""
    rc, out, _ = run_cmd(["ip", "-o", "link", "show"])
    interfaces = []
    for line in out.splitlines():
        # Format: 2: eth0: <FLAGS> ...
        m = re.match(r"\d+: (\w+):", line)
        if m:
            name = m.group(1)
            if name == "lo":
                continue
            state = "UP" if "UP" in line else "DOWN"
            is_wifi = False
            # Check if wireless
            rc2, _, _ = run_cmd(["iw", "dev", name, "info"])
            if rc2 == 0:
                is_wifi = True
            interfaces.append({
                "name": name,
                "state": state,
                "wifi": is_wifi,
            })
    return interfaces


def check_ethernet_dhcp() -> tuple[bool, str]:
    """Check if any ethernet interface already has an IP via DHCP."""
    rc, out, _ = run_cmd(["ip", "-o", "-4", "addr", "show"])
    for line in out.splitlines():
        # skip loopback
        if "lo " in line or "127.0.0.1" in line:
            continue
        m = re.search(r"(\w+)\s+inet\s+([\d.]+/\d+)", line)
        if m:
            iface, addr = m.group(1), m.group(2)
            return True, iface
    return False, ""


def ping_check(host: str = "8.8.8.8", count: int = 2) -> bool:
    """Return True if we can reach the internet."""
    rc, _, _ = run_cmd(["ping", "-c", str(count), "-W", "3", host], timeout=15)
    return rc == 0


def scan_wifi_ssids() -> list[str]:
    """Scan for available WiFi SSIDs via nmcli."""
    rc, out, _ = run_cmd(
        ["nmcli", "-t", "-f", "SSID", "dev", "wifi", "list", "--rescan", "yes"],
        timeout=20
    )
    ssids = []
    seen = set()
    for line in out.splitlines():
        ssid = line.strip()
        if ssid and ssid not in seen:
            ssids.append(ssid)
            seen.add(ssid)
    return ssids


def connect_wifi(iface: str, ssid: str, password: str) -> tuple[bool, str]:
    """Connect to a WiFi network via nmcli."""
    rc, out, err = run_cmd(
        ["nmcli", "dev", "wifi", "connect", ssid, "password", password, "ifname", iface],
        timeout=30
    )
    if rc == 0:
        return True, "Connected successfully"
    return False, err or "Connection failed"


class NetworkScreen(Screen):
    """Step 2 — Network configuration."""

    # UI state
    _interfaces: list[dict] = []
    _ssids: list[str] = []
    _wifi_iface: str = ""
    _status_msg: str = ""
    _mode: str = "checking"  # "checking" | "ethernet_ok" | "wifi_needed" | "wifi_select" | "connected"

    def compose(self) -> ComposeResult:
        yield Static("  HermitOS Installer", classes="wizard-title")
        yield Static("Step 2 of 9 — Network Setup", classes="step-indicator")
        with Container(classes="content-area"):
            with Vertical(id="main_content"):
                yield LoadingIndicator(id="loader")
                yield Static("Detecting network interfaces...", id="status_label", classes="muted")
                yield Static("", id="detail_area")
                # WiFi controls (hidden initially)
                with Container(id="wifi_controls"):
                    yield Label("Select WiFi Network:", id="ssid_label")
                    yield Select([], id="ssid_select", prompt="-- Select SSID --")
                    yield Label("WiFi Password:")
                    yield Input(placeholder="Enter WiFi passphrase", password=True, id="wifi_password")
                    yield Static("", id="wifi_error", classes="error-box")

        with Horizontal(classes="button-bar"):
            yield Button("← Back", id="btn_back", classes="secondary")
            yield Button("Refresh", id="btn_refresh", classes="secondary")
            yield Button("Connect WiFi", id="btn_connect_wifi", classes="secondary")
            yield Button("Next →", id="btn_next", classes="primary")

    def on_mount(self) -> None:
        # Hide wifi controls initially
        self.query_one("#wifi_controls").display = False
        self.query_one("#wifi_error").display = False
        self.query_one("#btn_connect_wifi").display = False
        self.detect_network()

    @work(exclusive=True, thread=True)
    def detect_network(self) -> None:
        """Background: detect network state."""
        worker = get_current_worker()

        self.call_from_thread(self._set_status, "Checking ethernet connectivity...")

        connected, iface = check_ethernet_dhcp()
        if connected:
            has_internet = ping_check()
            if has_internet:
                self.call_from_thread(self._set_mode_ethernet_ok, iface)
                return

        self.call_from_thread(self._set_status, "Scanning interfaces...")
        interfaces = get_interfaces()
        self._interfaces = interfaces

        wifi_ifaces = [i for i in interfaces if i["wifi"]]
        if wifi_ifaces:
            self._wifi_iface = wifi_ifaces[0]["name"]
            self.call_from_thread(self._set_mode_wifi_needed)
        else:
            self.call_from_thread(self._set_mode_no_wifi)

    @work(exclusive=True, thread=True)
    def scan_wifi(self) -> None:
        """Background: scan for SSIDs."""
        self.call_from_thread(self._set_status, f"Scanning for WiFi networks on {self._wifi_iface}...")
        ssids = scan_wifi_ssids()
        self._ssids = ssids
        self.call_from_thread(self._update_ssid_list, ssids)

    @work(exclusive=True, thread=True)
    def do_wifi_connect(self, ssid: str, password: str) -> None:
        """Background: connect to WiFi."""
        self.call_from_thread(self._set_status, f"Connecting to '{ssid}'...")
        ok, msg = connect_wifi(self._wifi_iface, ssid, password)
        if ok:
            has_internet = ping_check()
            if has_internet:
                self.app.state["network_connected"] = True
                self.app.state["network_interface"] = self._wifi_iface
                self.app.state["network_type"] = "wifi"
                self.call_from_thread(self._set_mode_connected, self._wifi_iface, "WiFi")
            else:
                self.call_from_thread(self._show_wifi_error, "Connected but no internet — check your network.")
        else:
            self.call_from_thread(self._show_wifi_error, f"Failed: {msg}")

    # --- UI update helpers (called from thread) ---

    def _set_status(self, msg: str) -> None:
        self.query_one("#status_label", Static).update(msg)

    def _set_mode_ethernet_ok(self, iface: str) -> None:
        self.query_one("#loader").display = False
        self.query_one("#wifi_controls").display = False
        self.query_one("#btn_connect_wifi").display = False
        self.app.state["network_connected"] = True
        self.app.state["network_interface"] = iface
        self.app.state["network_type"] = "ethernet"
        self.query_one("#status_label", Static).update(
            f"✓ Ethernet connected on {iface} — internet access confirmed."
        )
        detail = self.query_one("#detail_area", Static)
        detail.update(
            "Your network connection is already active. You can proceed to the next step."
        )
        detail.add_class("success-box")

    def _set_mode_wifi_needed(self) -> None:
        self.query_one("#loader").display = False
        self.query_one("#wifi_controls").display = True
        self.query_one("#btn_connect_wifi").display = True
        self.query_one("#status_label", Static).update(
            f"No active ethernet found. WiFi detected: {self._wifi_iface}"
        )
        detail = self.query_one("#detail_area", Static)
        detail.update("Scanning for WiFi networks...")
        self.scan_wifi()

    def _set_mode_no_wifi(self) -> None:
        self.query_one("#loader").display = False
        self.query_one("#status_label", Static).update(
            "⚠  No active network detected and no WiFi adapter found."
        )
        detail = self.query_one("#detail_area", Static)
        detail.update(
            "Plug in an ethernet cable and click Refresh, or ensure your WiFi adapter is supported."
        )
        detail.add_class("warning-box")

    def _set_mode_connected(self, iface: str, conn_type: str) -> None:
        self.query_one("#loader").display = False
        self.query_one("#wifi_controls").display = False
        self.query_one("#btn_connect_wifi").display = False
        self.query_one("#status_label", Static).update(
            f"✓ Connected via {conn_type} on {iface} — internet access confirmed."
        )
        detail = self.query_one("#detail_area", Static)
        detail.update("Network is ready. Click Next to continue.")
        detail.add_class("success-box")

    def _update_ssid_list(self, ssids: list[str]) -> None:
        select = self.query_one("#ssid_select", Select)
        options = [(s, s) for s in ssids]
        select.set_options(options)
        self.query_one("#status_label", Static).update(
            f"Found {len(ssids)} WiFi network(s). Select one and enter the password."
        )

    def _show_wifi_error(self, msg: str) -> None:
        self.query_one("#loader").display = False
        err = self.query_one("#wifi_error", Static)
        err.display = True
        err.update(f"✗ {msg}")

    # --- Button handlers ---

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn_back":
            self.app.go_back()
        elif event.button.id == "btn_refresh":
            self.detect_network()
        elif event.button.id == "btn_connect_wifi":
            self._handle_wifi_connect()
        elif event.button.id == "btn_next":
            if not self.app.state.get("network_connected"):
                self.query_one("#status_label", Static).update(
                    "⚠  Please establish a network connection before continuing."
                )
                return
            self.app.go_next("prime_name")  # Step 5: name the Prime agent

    def _handle_wifi_connect(self) -> None:
        select = self.query_one("#ssid_select", Select)
        password_input = self.query_one("#wifi_password", Input)
        ssid = select.value
        password = password_input.value

        if not ssid or ssid == Select.BLANK:
            self._show_wifi_error("Please select a WiFi network.")
            return
        if not password:
            self._show_wifi_error("Please enter the WiFi password.")
            return

        self.query_one("#wifi_error").display = False
        self.query_one("#loader").display = True
        self.do_wifi_connect(ssid, password)
