"""Step 3 — Timezone selection."""

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Button, Static, Label, Select, Input
from textual.containers import Container, Vertical, Horizontal

TIMEZONES = [
    # Americas
    ("US/Eastern     (New York)",      "America/New_York"),
    ("US/Central     (Chicago)",       "America/Chicago"),
    ("US/Mountain    (Denver)",        "America/Denver"),
    ("US/Pacific     (Los Angeles)",   "America/Los_Angeles"),
    ("US/Alaska      (Anchorage)",     "America/Anchorage"),
    ("US/Hawaii      (Honolulu)",      "Pacific/Honolulu"),
    ("Canada/Eastern (Toronto)",       "America/Toronto"),
    ("Canada/Pacific (Vancouver)",     "America/Vancouver"),
    ("Mexico         (Mexico City)",   "America/Mexico_City"),
    ("Brazil         (São Paulo)",     "America/Sao_Paulo"),
    ("Argentina      (Buenos Aires)",  "America/Argentina/Buenos_Aires"),
    # Europe
    ("UK / Ireland   (London)",        "Europe/London"),
    ("France         (Paris)",         "Europe/Paris"),
    ("Germany        (Berlin)",        "Europe/Berlin"),
    ("Spain          (Madrid)",        "Europe/Madrid"),
    ("Italy          (Rome)",          "Europe/Rome"),
    ("Sweden         (Stockholm)",     "Europe/Stockholm"),
    ("Finland        (Helsinki)",      "Europe/Helsinki"),
    ("Poland         (Warsaw)",        "Europe/Warsaw"),
    ("Russia         (Moscow)",        "Europe/Moscow"),
    # Asia / Pacific
    ("India          (Kolkata)",       "Asia/Kolkata"),
    ("Japan          (Tokyo)",         "Asia/Tokyo"),
    ("China          (Shanghai)",      "Asia/Shanghai"),
    ("Korea          (Seoul)",         "Asia/Seoul"),
    ("Australia/E    (Sydney)",        "Australia/Sydney"),
    ("Australia/W    (Perth)",         "Australia/Perth"),
    ("New Zealand    (Auckland)",      "Pacific/Auckland"),
    ("Singapore",                      "Asia/Singapore"),
    # Africa / Middle East
    ("South Africa   (Johannesburg)",  "Africa/Johannesburg"),
    ("UAE            (Dubai)",         "Asia/Dubai"),
    ("Israel         (Jerusalem)",     "Asia/Jerusalem"),
    # UTC
    ("UTC",                            "UTC"),
]


class TimezoneScreen(Screen):
    """Step 3 — Timezone selection."""

    def compose(self) -> ComposeResult:
        yield Static("  HermitOS Installer", classes="wizard-title")
        yield Static("Step 3 of 11 — Timezone", classes="step-indicator")
        with Container(classes="content-area"):
            with Vertical():
                with Container(classes="info-box"):
                    yield Label("Select your timezone.", classes="bold")
                    yield Label(
                        "This configures system time and affects log timestamps, "
                        "scheduled tasks, and time display.",
                        classes="muted"
                    )

                yield Static("")
                yield Label("Timezone:", classes="bold")
                yield Select(TIMEZONES, id="tz_select", value="America/Chicago")

        with Horizontal(classes="button-bar"):
            yield Button("← Back", id="btn_back", classes="secondary")
            yield Button("Next →", id="btn_next", classes="primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn_back":
            self.app.go_back()
        elif event.button.id == "btn_next":
            tz = self.query_one("#tz_select", Select).value
            self.app.state["timezone"] = str(tz) if tz else "America/Chicago"
            self.app.go_next("network")
