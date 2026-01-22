"""Interactive terminal UI for browsing and adding models.

Provides a simplified interface for adding custom OpenAI-compatible models.
"""

import json
import os
import sys
import time
from pathlib import Path
from typing import List, Optional

from prompt_toolkit.application import Application
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Dimension, Layout, VSplit, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.widgets import Frame

from code_puppy.command_line.utils import safe_input
from code_puppy.config import EXTRA_MODELS_FILE, set_config_value
from code_puppy.messaging import emit_error, emit_info, emit_warning
from code_puppy.models_dev_parser import ModelInfo, ProviderInfo
from code_puppy.tools.command_runner import set_awaiting_user_input

class AddModelMenu:
    """Interactive TUI for adding custom OpenAI-compatible models."""

    def __init__(self):
        """Initialize the model browser menu."""
        self.kb = KeyBindings()
        self.providers: List[ProviderInfo] = [
            ProviderInfo(
                id="custom-openai",
                name="Custom OpenAI Compatible",
                env=["CUSTOM_OPENAI_API_KEY"],
                api="N/A"
            )
        ]
        self.current_provider: Optional[ProviderInfo] = self.providers[0]
        self.current_models: List[ModelInfo] = []

        # State management
        self.view_mode = "providers"
        self.selected_provider_idx = 0
        self.selected_model_idx = 0
        self.result = None

    def _render_provider_list(self) -> List:
        """Render the provider list panel."""
        lines = []
        lines.append(("", " Providers\n\n"))

        provider = self.providers[0]
        prefix = " > "
        label = f"{prefix}{provider.name}"
        lines.append(("fg:ansicyan bold", label))
        lines.append(("", "\n"))

        lines.append(("", "\n"))
        self._render_navigation_hints(lines)
        return lines

    def _render_navigation_hints(self, lines: List):
        """Render navigation hints."""
        lines.append(("", "\n"))
        lines.append(("fg:green", "  Enter  "))
        lines.append(("", "Select/Add\n"))
        lines.append(("fg:ansibrightred", "  Ctrl+C "))
        lines.append(("", "Cancel"))

    def _render_model_details(self) -> List:
        """Render details panel."""
        lines = []
        lines.append(("dim cyan", " DETAILS\n\n"))

        lines.append(("bold", "  Custom OpenAI Compatible Endpoint\n\n"))
        lines.append(("fg:ansibrightblack", "  Add any model that supports the OpenAI API format.\n"))
        lines.append(("fg:ansibrightblack", "  You will need:\n"))
        lines.append(("fg:ansibrightblack", "  1. API Endpoint URL\n"))
        lines.append(("fg:ansibrightblack", "  2. API Key\n"))
        lines.append(("fg:ansibrightblack", "  3. Model ID (e.g. gpt-4, llama-3)\n"))

        return lines

    def update_display(self):
        """Update the display."""
        self.menu_control.text = self._render_provider_list()
        self.preview_control.text = self._render_model_details()

    def run(self) -> bool:
        """Run the menu."""
        # Build UI
        self.menu_control = FormattedTextControl(text="")
        self.preview_control = FormattedTextControl(text="")

        menu_window = Window(content=self.menu_control, wrap_lines=True, width=Dimension(weight=30))
        preview_window = Window(content=self.preview_control, wrap_lines=True, width=Dimension(weight=70))

        menu_frame = Frame(menu_window, width=Dimension(weight=30), title="Select Type")
        preview_frame = Frame(preview_window, width=Dimension(weight=70), title="Info")

        root_container = VSplit([menu_frame, preview_frame])

        kb = KeyBindings()

        @kb.add("enter")
        def _(event):
            self.result = "add_custom"
            event.app.exit()

        @kb.add("c-c")
        def _(event):
            event.app.exit()

        layout = Layout(root_container)
        app = Application(layout=layout, key_bindings=kb, full_screen=False, mouse_support=False)

        set_awaiting_user_input(True)

        sys.stdout.write("\033[?1049h")
        sys.stdout.write("\033[2J\033[H")
        sys.stdout.flush()

        try:
            self.update_display()
            app.run(in_thread=True)
        finally:
            sys.stdout.write("\033[?1049l")
            sys.stdout.flush()
            set_awaiting_user_input(False)

        if self.result == "add_custom":
            return self._prompt_custom_flow()

        return False

    def _prompt_custom_flow(self) -> bool:
        """Handle the custom model input flow."""
        try:
            emit_info("\n✨ Add Custom OpenAI-Compatible Model\n")

            # 1. Base URL
            base_url = safe_input("  API Base URL (e.g., https://api.openai.com/v1): ")
            if not base_url: return False

            # 2. Model ID
            model_id = safe_input("  Model ID (e.g., gpt-4o): ")
            if not model_id: return False

            # 3. API Key (Environment Variable Name)
            env_var_name = safe_input("  Environment Variable for API Key (e.g., OPENAI_API_KEY): ")
            if not env_var_name: return False

            # 4. Context Length
            ctx_input = safe_input("  Context Length [128000]: ")
            context_length = 128000
            if ctx_input:
                try:
                    context_length = int(ctx_input)
                except ValueError:
                    pass

            # Check if env var is set
            if not os.environ.get(env_var_name):
                 key_val = safe_input(f"  Enter value for {env_var_name} (will be saved): ")
                 if key_val:
                     set_config_value(env_var_name, key_val)
                     os.environ[env_var_name] = key_val

            # Save config
            config = {
                "type": "custom_openai",
                "name": model_id,
                "custom_endpoint": {
                    "url": base_url,
                    "api_key": f"${env_var_name}"
                },
                "context_length": context_length,
                "supported_settings": ["temperature", "top_p"]
            }

            self._save_config(f"custom-{model_id}", config)
            return True

        except (KeyboardInterrupt, EOFError):
            emit_warning("\nCancelled.")
            return False

    def _save_config(self, key: str, config: dict):
        extra_models_path = Path(EXTRA_MODELS_FILE)
        extra_models = {}

        if extra_models_path.exists():
            try:
                with open(extra_models_path, "r", encoding="utf-8") as f:
                    extra_models = json.load(f)
            except Exception:
                pass

        extra_models[key] = config
        extra_models_path.parent.mkdir(parents=True, exist_ok=True)

        with open(extra_models_path, "w", encoding="utf-8") as f:
            json.dump(extra_models, f, indent=4)

        emit_info(f"✅ Added {key} to configuration.")

def interactive_model_picker() -> bool:
    menu = AddModelMenu()
    return menu.run()
