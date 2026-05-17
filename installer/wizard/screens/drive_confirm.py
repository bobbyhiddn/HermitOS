"""Drive confirmation dialog screen."""

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Button, Static, Label
from textual.containers import Container, Vertical, Horizontal


class DriveConfirmScreen(Screen):
    """Confirmation screen before destructive drive operation."""

    def __init__(self, device: dict, has_data: bool):
        super().__init__()
        self._device = device
        self._has_data = has_data

    def compose(self) -> ComposeResult:
        dev_path = self._device["path"]
        dev_size = self._device["size"]
        dev_model = self._device["model"]

        yield Static("  ⚠  DESTRUCTIVE OPERATION WARNING", classes="wizard-title")
        with Container(classes="content-area"):
            with Vertical():
                yield Static("")
                with Container(classes="error-box"):
                    yield Label("ALL DATA WILL BE PERMANENTLY DESTROYED", classes="bold")
                    yield Label("")
                    yield Label(f"Target drive: {dev_path}")
                    yield Label(f"Model: {dev_model}")
                    yield Label(f"Capacity: {dev_size}")
                    yield Label("")
                    if self._has_data:
                        yield Label(
                            "This drive contains existing partitions and data. "
                            "Everything will be overwritten.",
                            classes="bold"
                        )
                    yield Label("")
                    yield Label(
                        f"Type the device path to confirm: {dev_path}",
                        classes="muted"
                    )
                yield Static("")
                yield Label("Are you absolutely sure you want to continue?", classes="bold")

        with Horizontal(classes="button-bar"):
            yield Button("← Cancel (Keep my data)", id="btn_cancel", classes="primary")
            yield Button(
                f"YES, ERASE {dev_path}",
                id="btn_confirm",
                classes="danger",
            )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn_confirm":
            self.dismiss(True)
        else:
            self.dismiss(False)
