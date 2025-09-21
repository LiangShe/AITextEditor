# AITextEditor - Editor with Local LLM Integration #

A user-friendly, Python-based editor that leverages a locally hosted LLM (via [Ollama](https://github.com/ollama/ollama) for now) for fast text enhancements, proofreading, and rewriting. Whether you’re polishing a blog post, correcting grammar, or simplifying your wording, this editor enables you to harness the power of local generative AI right from your desktop—no cloud services needed.

Forked from [TextEnhanceAI](https://github.com/wenrolland/TextEnhanceAI)

![App Window - v0.1](/AITextEditor-v0.11.png)

## Key Features

1. **Inline Editing and Diff View**  
   - Type or paste your plain text into the editor, then click an editing action (Grammar, Proofread, Rewrite, etc.).  
   - The application compares your text against the AI-edited output and highlights changes inline.  
   - Deletions appear in red, additions in green.

2. **Multiple Editing Modes**  
   - Built-in prompts let you quickly fix grammar, streamline awkward phrases, or make your text more concise.  
   - A customizable “Custom Prompt” option allows you to craft specialized instructions for the LLM.

3. **Accept / Reject All Changes**  
   - Quickly apply all AI-suggested edits with “Accept All Changes,” or revert them entirely with “Reject All Changes.”  

4. **Scratchpad Logging**  
   - Every edit is logged to a Markdown scratchpad file. [Example](/TextEnhanceAI-scratchpad_20250605_191604.md)
   - The original user text and the LLM’s edited text are saved side by side, with any removed/added words highlighted in **bold** Markdown, helping you track changes over time.

5. **Local LLM Support**  
   - Connects to a locally hosted LLM through Ollama.  
   - No internet connection required—your content stays on your own machine.

## Getting Started

1. **Install Requirements**  
   - Ensure Python 3.7+ is [installed](https://www.python.org/downloads/).  
   - Install the [Ollama](https://github.com/ollama/ollama) package.
   - Download llama3.1:8b in Ollama :
      ```bash
      ollama pull gemma3:4b
      ```
   - Install other Python dependencies as needed (e.g., `tkinter`—usually bundled with Python, `difflib`—comes with standard library).

2. **Run the App**  
   Clone the repository or simply download AITextEditor.py to get the program. Launch it using :
      ```bash
      python AITextEditor.py
      ```
   If Ollama is running, you’ll see the main editor window.

4. **Use the Editing Buttons**  
   - Type or paste your text.  
   - Click on an editing button (e.g., “Grammar,” “Proofread”) to send a prompt to the local LLM.  
   - The edited text will be displayed inline, with suggested deletions in red and additions in green.

5. **Accept/Reject Changes**  
   - When ready, you can accept all or reject all the AI-suggested edits.
   - The edition scratchpad is saved in the same directory. This way, you can review the output, whatever your choices.
   - When done, simply copy the text and paste it where you want to use it.
