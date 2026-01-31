import tkinter as tk
from tkinter import scrolledtext, filedialog, messagebox, simpledialog
from diff_match_patch import diff_match_patch
import re
from datetime import datetime
import textwrap
import yaml
import os
import threading

try:
    from ollama import Client
    try:
        # Prefer top-level list API when available
        from ollama import list as ollama_list, ListResponse
    except Exception:
        ollama_list = None
        ListResponse = None
except ImportError:
    print("Please install the ollama package (pip install ollama).")
    Client = None
    ollama_list = None
    ListResponse = None

def load_settings():
    """Loads settings from setting.yaml"""
    SETTING_FILE = "settings.yaml"
    if not yaml:
        messagebox.showerror("Error", "PyYAML package is not installed. (pip install pyyaml).")
        return None, None, None
    try:
        with open(SETTING_FILE, "r") as f:
            settings = yaml.safe_load(f)
            return settings.get("model_name"), settings.get("scratchpad_dir"), settings.get("prompts", {}), settings.get("ollama_host", "localhost:11434")
    except FileNotFoundError:
        messagebox.showerror("Error", "setting.yaml not found!")
        return None, None, None, None

def text_length(text):
    return len(text) if text is not None else 0

# --------------
# Custom dialog to allow an 80-character-wide prompt entry
# --------------
class LargerPromptDialog(simpledialog._QueryString):
    def body(self, master):
        # Let the superclass build the main layout
        super().body(master)
        # Force the entry to be a wider text field
        self.entry.config(width=80)

def ask_custom_string(title, prompt, parent=None):
    """Ask for a string in a custom 80-char wide prompt dialog."""
    d = LargerPromptDialog(title, prompt)
    return d.result


# --------------
# Simple Tooltip class
# --------------
class ToolTip:
    """
    A simple tooltip for tkinter widgets.
    Usage: create_tooltip(widget, text='Hello!')
    """
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tip_window = None
        self.id = None
        self.x = self.y = 0

        self.widget.bind("<Enter>", self.enter)
        self.widget.bind("<Leave>", self.leave)

    def enter(self, event=None):
        self.showtip()

    def leave(self, event=None):
        self.hidetip()

    def showtip(self):
        if self.tip_window or not self.text:
            return
        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() + self.widget.winfo_height() - 45
        self.tip_window = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)  # removes the window decorations
        tw.geometry(f"+{x}+{y}")
        label = tk.Label(
            tw,
            text=self.text,
            justify=tk.LEFT,
            background="#ffffe0",
            relief=tk.SOLID,
            borderwidth=1,
            font=("tahoma", "8", "normal")
        )
        label.pack(ipadx=1)

    def hidetip(self):
        tw = self.tip_window
        self.tip_window = None
        if tw:
            tw.destroy()


def create_tooltip(widget, text):
    """Helper to attach a tooltip with given text to a widget."""
    ToolTip(widget, text)


# --------------
# Main application class
# --------------
class EditorApp:
    def __init__(self, root):
        # Load settings from YAML
        self.model_name, self.scratchpad_dir, self.prompts, self.ollama_host = load_settings()
        if not all([self.model_name, self.scratchpad_dir, self.prompts, self.ollama_host]):
            root.quit()
            return

        self.root = root
        self.root.title("AITextEditor with Local LLM - V 0.11")

        # ----------------------
        # 1) Set starting size and use it as the minimum
        # ----------------------
        self.root.geometry("1280x720")
        self.root.minsize(800, 600)

        # 2) Initialize widgets and buttons

        # Ollama client (make sure you've installed and are running your local LLM server)
        self.ollama_client = Client(host=self.ollama_host) if Client else None

        # Top bar: model selection
        top_bar = tk.Frame(self.root)
        top_bar.pack(fill=tk.X, padx=5, pady=5)
        model_label = tk.Label(top_bar, text="Model:")
        model_label.pack(side=tk.LEFT, padx=(0, 2))
        self.model_var = tk.StringVar(value=self.model_name)
        self.model_optionmenu = tk.OptionMenu(top_bar, self.model_var, self.model_name)
        self.model_optionmenu.pack(side=tk.LEFT, padx=(0, 6))
        refresh_btn = tk.Button(top_bar, text="Refresh", command=self.populate_model_menu)
        refresh_btn.pack(side=tk.LEFT, padx=(0, 8))
        
        # Load models initially
        self.populate_model_menu()

        # Check for running models and set as default if configured
        running_models = self.get_running_models()
        if running_models:
            # Picking first running model:
            selected_model = list(running_models.keys())[0]

        # Map model names from list API to ps API (they might return different formats)
        try:
            # Update the model_var if needed
            if selected_model and selected_model != self.model_var.get():
                self.model_var.set(selected_model)
                # Also update self.model_name for future queries
                self.model_name = selected_model
        except Exception as e:
            print(f"Error selecting the running models use default {e}")

        # Frame for buttons
        btn_frame = tk.Frame(self.root)
        btn_frame.pack(fill=tk.X, padx=5, pady=5)

        # Create button groups from prompts
        for group_name, group_prompts in self.prompts.items():
            # Create a labeled frame for each group
            group_frame = tk.LabelFrame(btn_frame, text=group_name, padx=5, pady=5)
            group_frame.pack(side=tk.LEFT, padx=5, fill=tk.Y)

            if isinstance(group_prompts, dict):
                for label, prompt_text in group_prompts.items():
                    b = tk.Button(
                        group_frame,
                        text=label,
                        # Pass both group and label to the command
                        command=lambda gn=group_name, lbl=label: self.run_llm(gn, lbl)
                    )
                    b.pack(side=tk.LEFT, padx=2)
                    # Show the full prompt in a tooltip
                    create_tooltip(b, prompt_text)

        # Quit button
        tk.Button(
            btn_frame, text="Quit", command=self.root.quit
        ).pack(side=tk.RIGHT, padx=2)

        # Text area (scrolled)
        self.text_area = scrolledtext.ScrolledText(self.root, wrap=tk.WORD, width=80, height=25, font=("Calibri", 14))
        self.text_area.pack(padx=5, pady=5, fill=tk.BOTH, expand=True)

        # Frame for apply-changes options
        self.accept_reject_frame = tk.Frame(self.root)
        self.accept_reject_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # 3) Make the Accept/Reject button text colored
        tk.Button(
            self.accept_reject_frame,
            text="Accept All Changes",
            command=self.accept_all_changes,
            fg='green'
        ).pack(side=tk.LEFT, padx=2)

        tk.Button(
            self.accept_reject_frame,
            text="Reject All Changes",
            command=self.reject_all_changes,
            fg='red'
        ).pack(side=tk.LEFT, padx=2)
        
        # We store the “diff-annotated” version of the text in a separate place
        # so we can choose to accept or reject changes piecewise.
        self.diff_text = ""
        self.temp_html = ""  # If you want to store a temporary HTML version

        # For scratchpad logging:
        self.scratchpad_filename = None
        self.first_change_time = None

        # Status label
        self.status_var = tk.StringVar(value="Ready")
        self.status_label = tk.Label(self.root, textvariable=self.status_var, anchor="w")
        self.status_label.pack(fill=tk.X, padx=5, pady=(0,5))

    # --------------
    # Button callbacks
    # --------------
    def run_llm(self, group_name, prompt_label):
        """ Based on task type, use different system prompt, send query, and process responses """
        if not self.ollama_client:
            messagebox.showerror("Error", "Ollama client not initialized or not installed.")
            return

        user_text = self.text_area.get("1.0", tk.END).strip()
        Instruction = self.prompts[group_name][prompt_label]

        if group_name == 'Edit':
            # Send the editing prompt + current text to the LLM and display the changes inline
        
            system_prompt = (
                "You are a helpful, experienced assistant that carefully edits text."
                "based on instructions. Return only the edited text, without extra commentary."
            )
            
            response = self.send_llm_query(system_prompt, Instruction, user_text)

            # compute diffs
            diffs = self.compute_diffs(user_text, response)

            # Show inline diff to the text widget
            self.show_inline_diff(diffs)

            # Log to scratchpad with bold for differences
            bold_user_text, bold_edited_text = self.generate_bold_diff(diffs)
            self.log_to_scratchpad(
                f"#Instruction: {Instruction} #\n\n"
                f"##User Text:##\n{bold_user_text}\n\n"
                f"##Edited Text:##\n{bold_edited_text}\n\n"
            )

        else:
            system_prompt = ()
            response = self.send_llm_query(system_prompt, Instruction, user_text)
            self.text_area.insert(tk.END, "\n" + response, ("addition",))
            self.text_area.tag_config("addition", foreground="green")

 
    # --------------
    # LLM
    # --------------
    def send_llm_query(self, system_prompt, instruction, user_text, diff=False):
        """
        Query the local LLM
        if editing, compare and highlight the changes, and logs to scratchpad with bold Markdown for the changes.
        """
        # If it's the first time we are modifying text, create the scratchpad
        if not self.first_change_time:
            self.first_change_time = datetime.now().strftime("%Y%m%d_%H%M%S")
            # Ensure the scratchpad directory exists
            os.makedirs(self.scratchpad_dir, exist_ok=True)
            
            # Construct the full path for the scratchpad file
            filename = f"AITextEditor-scratchpad_{self.first_change_time}.md"
            self.scratchpad_filename = os.path.join(self.scratchpad_dir, filename)

        # Prepare the conversation
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Instruction:\n{instruction}\n\nText:\n{user_text}"}
        ]

        # --- Dynamically set context size based on input length ---
        # Estimate token count (1 token ~= 4 chars) and add a buffer.
        # This ensures the context window is large enough for the prompt + response.
        num_predict = 2048  # Max tokens for the model to generate
        prompt_chars = text_length(system_prompt) + text_length(instruction) + text_length(user_text)
        estimated_tokens = prompt_chars // 4 
        print(f"estimated tokens: {estimated_tokens}")

        # Choose a context size (num_ctx) that fits the prompt and the expected output.
        # We'll use powers of 2, which is common practice.
        required_size = estimated_tokens + num_predict
        if required_size <= 2048:
            context_size = 2048
        elif required_size <= 4096:
            context_size = 4096
        else:
            context_size = 8192 # Default to a larger size for very long inputs

        # Check if the selected model is already running and has sufficient context
        running_models = self.get_running_models()
        selected_model = (self.model_var.get() or "").strip()
        if selected_model and selected_model in running_models:
            running_context = running_models[selected_model]
            if running_context >= required_size:
                context_size = running_context

        try:
            selected_model = (self.model_var.get() or "").strip()
        except Exception:
            selected_model = ""
        if selected_model:
            self.model_name = selected_model

        response = {}
        try:
            response = self.ollama_client.chat(
                model=self.model_name,
                messages=messages,
                options={
                    'num_ctx': context_size,
                    'num_predict': num_predict,
                    'temperature': 0.7, # You could also make these configurable
                    'top_p': 0.9,       # in settings.yaml
                },
            )
        except Exception as e:
            messagebox.showerror("LLM Error", f"An error occurred: {e}")
            return

        # The "message" content from the LLM (the new text)
        content = ""
        if "message" in response and "content" in response["message"]:
            content = response["message"]["content"].strip()
        else:
            messagebox.showinfo("LLM Error", "No content received from LLM.")
            return
        
        return content

    def get_available_models(self):
        """Return a list of available local Ollama model names."""
        models = []
        # 1) Try official top-level API first
        if ollama_list is not None:
            try:
                resp = ollama_list()
                # Newer package: ListResponse with .models attribute
                if hasattr(resp, 'models'):
                    for m in getattr(resp, 'models') or []:
                        # objects have .model (name)
                        name = getattr(m, 'model', None) or getattr(m, 'name', None)
                        if isinstance(name, str):
                            models.append(name)
                # Fallback: dict with 'models'
                elif isinstance(resp, dict) and 'models' in resp:
                    for m in resp.get('models') or []:
                        if isinstance(m, dict):
                            name = m.get('name') or m.get('model')
                        else:
                            name = str(m)
                        if isinstance(name, str):
                            models.append(name)
            except Exception:
                # ignore and fallback to client
                pass
        # 2) Fallback to client.list() if needed
        if not models and self.ollama_client and hasattr(self.ollama_client, 'list'):
            try:
                resp = self.ollama_client.list()
                items = []
                if hasattr(resp, 'models'):
                    items = resp.models  # type: ignore[attr-defined]
                elif isinstance(resp, dict) and 'models' in resp:
                    items = resp['models'] or []
                elif isinstance(resp, list):
                    items = resp
                for m in items:
                    name = None
                    if isinstance(m, dict):
                        name = m.get('name') or m.get('model')
                    else:
                        name = getattr(m, 'model', None) or getattr(m, 'name', None) or (str(m) if m else None)
                    if isinstance(name, str):
                        models.append(name)
            except Exception:
                pass
        if not models:
            models = [self.model_name]
        return sorted(set(models))

    def get_running_models(self):
        """Return dictionary of running models and their context lengths."""
        running_models = {}
        try:
            resp = self.ollama_client.ps() if self.ollama_client else None
            if resp and hasattr(resp, 'models'):
                for m in resp.models:
                    name = getattr(m, 'model', None) or getattr(m, 'name', None)
                    if isinstance(name, str):
                        if hasattr(m, 'context_length'):
                            running_models[name] = m.context_length
        except Exception:
            pass
        return running_models


    def populate_model_menu(self):
        """Load models from Ollama and update the dropdown."""
        models = self.get_available_models()
        try:
            menu = self.model_optionmenu["menu"]
            menu.delete(0, "end")
            for m in models:
                menu.add_command(label=m, command=lambda v=m: self.model_var.set(v))
            if self.model_var.get() not in models:
                self.model_var.set(models[0])
        except Exception:
            if models:
                self.model_var.set(models[0])

    def compute_diffs(self, old_text, new_text):
        differ = diff_match_patch()
        diffs = differ.diff_main(old_text, new_text)
        differ.diff_cleanupSemantic(diffs)
        return diffs

    def show_inline_diff(self, diffs):
        """
        Compute a diff using diff-match-patch and insert inline color-coded changes
        into the text widget. Deletions in red, additions in green.
        """
        self.text_area.delete("1.0", tk.END)

        for operation, text in diffs:
            if operation == diff_match_patch.DIFF_EQUAL:
                self.text_area.insert(tk.END, text)
            elif operation == diff_match_patch.DIFF_DELETE:
                self.text_area.insert(tk.END, text, ("deletion",))
            elif operation == diff_match_patch.DIFF_INSERT:
                self.text_area.insert(tk.END, text, ("addition",))

        # Tag styles
        self.text_area.tag_config("deletion", foreground="red", overstrike=True)
        self.text_area.tag_config("addition", foreground="green")

    def generate_bold_diff(self, diffs):
        """
        Generate two strings:
         - In the 'User Text', highlight removed words in bold
         - In the 'Edited Text', highlight added words in bold
        """

        user_text_bold = []
        edited_text_bold = []

        for operation, text in diffs:
            if operation == diff_match_patch.DIFF_EQUAL:
                user_text_bold.append(text)
                edited_text_bold.append(text)
            elif operation == diff_match_patch.DIFF_DELETE:
                # Removed word
                if text.strip():  # Only bold non-whitespace
                    user_text_bold.append(f"**{text}**")
                else:
                    user_text_bold.append(text)
            elif operation == diff_match_patch.DIFF_INSERT:
                # Added word
                if text.strip(): # Only bold non-whitespace
                    edited_text_bold.append(f"**{text}**")
                else:
                    edited_text_bold.append(text)

        # Rebuild as strings, joining without extra spaces
        return "".join(user_text_bold), "".join(edited_text_bold)

    # --------------
    # Accept / Reject changes
    # --------------
    def accept_all_changes(self):
        """Accept all changes by removing diff markup and using the 'plus' words only."""
        final_text = self.get_text_excluding_tag("deletion")
        self.text_area.delete("1.0", tk.END)
        self.text_area.insert("1.0", final_text)

        # Log acceptance
        self.log_to_scratchpad("User accepted all changes.\n\n")

    def reject_all_changes(self):
        """Reject all changes by removing diff markup and using the 'original' words only."""
        final_text = self.get_text_excluding_tag("addition")
        self.text_area.delete("1.0", tk.END)
        self.text_area.insert("1.0", final_text)

        # Log rejection
        self.log_to_scratchpad("User rejected all changes.\n\n")

    def get_text_excluding_tag(self, tag_to_exclude):
        """
        Helper to rebuild text from the text widget while excluding a particular tag’s text.
        This is a more efficient implementation than iterating character by character.
        """
        # dump() provides a sequence of (type, value, index) tuples.
        # We can iterate through them and build the string, skipping text
        # that falls under the tag we want to exclude.
        content = self.text_area.dump("1.0", "end-1c", text=True, tag=True)

        result_parts = []
        is_excluded = False

        for item_type, value, index in content:
            if item_type == "tagon" and value == tag_to_exclude:
                is_excluded = True
            elif item_type == "tagoff" and value == tag_to_exclude:
                is_excluded = False
            elif item_type == "text" and not is_excluded:
                result_parts.append(value)

        return "".join(result_parts)

    # --------------
    # Logging / Scratchpad
    # --------------
    def log_to_scratchpad(self, *texts):
        """Write changes and actions to the scratchpad file."""
        if not self.scratchpad_filename:
            return
        with open(self.scratchpad_filename, "a", encoding="utf-8") as f:
            for text in texts:
                f.write(text)
            f.write("\n")


# --------------
# Main entry point
# --------------
if __name__ == "__main__":
    root = tk.Tk()
    app = EditorApp(root)
    root.mainloop()
