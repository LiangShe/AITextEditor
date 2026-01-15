import tkinter as tk
from tkinter import scrolledtext, filedialog, messagebox, simpledialog
import difflib
import re
from datetime import datetime
import textwrap
import yaml
import os

try:
    from ollama import Client
except ImportError:
    print("Please install the ollama package (pip install ollama).")
    Client = None

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
            
            # Show inline diff to the text widget
            self.show_inline_diff(user_text, response)

            # Log to scratchpad with bold for differences
            bold_user_text, bold_edited_text = self.generate_bold_diff(user_text, response)
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


    def show_inline_diff(self, old_text, new_text):
        """
        Compute a diff using difflib and insert inline color-coded changes
        into the text widget. Deletions in red, additions in green.
        """
        self.text_area.delete("1.0", tk.END)

        # Split on whitespace while keeping the whitespace tokens so that
        # newline characters and other spacing are preserved in the output
        old_tokens = re.split(r'(\s+)', old_text)
        new_tokens = re.split(r'(\s+)', new_text)

        diff = difflib.ndiff(old_tokens, new_tokens)

        for token in diff:
            # token starts with '  ' (no change), '- ' (deletion), or '+ ' (addition)
            text = token[2:]
            if token.startswith("  "):
                # no change
                self.text_area.insert(tk.END, text)
            elif token.startswith("- "):
                # deletion
                self.text_area.insert(tk.END, text, ("deletion",))
            elif token.startswith("+ "):
                # addition
                self.text_area.insert(tk.END, text, ("addition",))

        # Tag styles
        self.text_area.tag_config("deletion", foreground="red", overstrike=True)
        self.text_area.tag_config("addition", foreground="green")

    def generate_bold_diff(self, original_text, edited_text):
        """
        Generate two strings:
         - In the 'User Text', highlight removed words in bold
         - In the 'Edited Text', highlight added words in bold
        """
        # Split on whitespace while preserving it to maintain formatting
        original_tokens = re.split(r'(\s+)', original_text)
        edited_tokens = re.split(r'(\s+)', edited_text)
        diff = difflib.ndiff(original_tokens, edited_tokens)

        user_text_bold = []
        edited_text_bold = []

        for token in diff:
            word = token[2:]
            if token.startswith("  "):
                # No change
                user_text_bold.append(word)
                edited_text_bold.append(word)
            elif token.startswith("- "):
                # Removed word
                if word.strip():  # Only bold non-whitespace
                    user_text_bold.append(f"**{word}**")
                else:
                    user_text_bold.append(word)
            elif token.startswith("+ "):
                # Added word
                if word.strip(): # Only bold non-whitespace
                    edited_text_bold.append(f"**{word}**")
                else:
                    edited_text_bold.append(word)

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
