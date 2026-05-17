"""Step 2 — Language and locale selection."""

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Button, Static, Label, Select, Input
from textual.containers import Container, Vertical, Horizontal

LOCALES = [
    ("English (US)  — en_US.UTF-8", "en_US.UTF-8"),
    ("English (UK)  — en_GB.UTF-8", "en_GB.UTF-8"),
    ("English (AU)  — en_AU.UTF-8", "en_AU.UTF-8"),
    ("Spanish       — es_ES.UTF-8", "es_ES.UTF-8"),
    ("French        — fr_FR.UTF-8", "fr_FR.UTF-8"),
    ("German        — de_DE.UTF-8", "de_DE.UTF-8"),
    ("Italian       — it_IT.UTF-8", "it_IT.UTF-8"),
    ("Portuguese    — pt_BR.UTF-8", "pt_BR.UTF-8"),
    ("Japanese      — ja_JP.UTF-8", "ja_JP.UTF-8"),
    ("Chinese (CN)  — zh_CN.UTF-8", "zh_CN.UTF-8"),
    ("Korean        — ko_KR.UTF-8", "ko_KR.UTF-8"),
    ("Russian       — ru_RU.UTF-8", "ru_RU.UTF-8"),
    ("Polish        — pl_PL.UTF-8", "pl_PL.UTF-8"),
    ("Dutch         — nl_NL.UTF-8", "nl_NL.UTF-8"),
    ("Swedish       — sv_SE.UTF-8", "sv_SE.UTF-8"),
]

KEYBOARD_LAYOUTS = [
    ("US (QWERTY)", "us"),
    ("UK (QWERTY)", "gb"),
    ("US (Dvorak)", "us_dvorak"),
    ("US (Colemak)", "us_colemak"),
    ("German (QWERTZ)", "de"),
    ("French (AZERTY)", "fr"),
    ("Spanish (QWERTY)", "es"),
    ("Italian", "it"),
    ("Swedish", "se"),
    ("Norwegian", "no"),
    ("Danish", "dk"),
    ("Dutch", "nl"),
    ("Portuguese (BR)", "br"),
    ("Russian", "ru"),
    ("Japanese", "jp"),
]


class LocaleScreen(Screen):
    """Step 2 — Language and keyboard layout selection."""

    def compose(self) -> ComposeResult:
        yield Static("  HermitOS Installer", classes="wizard-title")
        yield Static("Step 2 of 11 — Language & Region", classes="step-indicator")
        with Container(classes="content-area"):
            with Vertical():
                with Container(classes="info-box"):
                    yield Label("Select your language and keyboard layout.", classes="bold")
                    yield Label(
                        "These settings configure the system locale and input method.",
                        classes="muted"
                    )

                yield Static("")
                yield Label("System Language / Locale:", classes="bold")
                yield Select(LOCALES, id="locale_select", value="en_US.UTF-8")

                yield Static("")
                yield Label("Keyboard Layout:", classes="bold")
                yield Select(KEYBOARD_LAYOUTS, id="kb_select", value="us")

        with Horizontal(classes="button-bar"):
            yield Button("← Back", id="btn_back", classes="secondary")
            yield Button("Next →", id="btn_next", classes="primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn_back":
            self.app.go_back()
        elif event.button.id == "btn_next":
            locale = self.query_one("#locale_select", Select).value
            kb = self.query_one("#kb_select", Select).value
            self.app.state["locale"] = str(locale) if locale else "en_US.UTF-8"
            self.app.state["keyboard"] = str(kb) if kb else "us"
            self.app.go_next("timezone")
