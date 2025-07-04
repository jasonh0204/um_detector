import threading
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import io

import speech_recognition as sr
import openai

from .detector import count_fillers, FILLER_WORDS


class UmDetectorApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Um Detector")
        self.recognizer = sr.Recognizer()
        self.microphone_names = sr.Microphone.list_microphone_names()
        if not self.microphone_names:
            messagebox.showerror("Microphone Error", "No input devices found.")
            self.microphone_names = []
        self.device_var = tk.StringVar(value=self.microphone_names[0] if self.microphone_names else "")
        self.microphone = None

        self.is_listening = False
        self.listen_thread = None
        self.buffer = []
        self.transcripts = {}
        self.current_speaker = ""

        # UI elements
        main = ttk.Frame(root, padding=10)
        main.grid(row=0, column=0, sticky="nsew")

        ttk.Label(main, text="Speaker name:").grid(row=0, column=0, sticky="w")
        self.speaker_var = tk.StringVar()
        ttk.Entry(main, textvariable=self.speaker_var).grid(row=0, column=1, sticky="ew")
        ttk.Button(main, text="Add", command=self.add_speaker).grid(row=0, column=2, padx=(5, 0))

        ttk.Label(main, text="Current speaker:").grid(row=1, column=0, sticky="w")
        self.current_speaker_label = ttk.Label(main, text="")
        self.current_speaker_label.grid(row=1, column=1, sticky="w")

        ttk.Label(main, text="Input device:").grid(row=2, column=0, sticky="w")
        self.device_combo = ttk.Combobox(main, textvariable=self.device_var, values=self.microphone_names, state="readonly")
        self.device_combo.grid(row=2, column=1, sticky="ew")

        self.start_button = ttk.Button(main, text="Start", command=self.start,
                                        state="normal" if self.microphone_names else "disabled")
        self.start_button.grid(row=3, column=0, pady=5)
        self.stop_button = ttk.Button(main, text="End", command=self.stop, state="disabled")
        self.stop_button.grid(row=3, column=1, pady=5)

        self.show_button = ttk.Button(main, text="Show Results", command=self.show_results)
        self.show_button.grid(row=4, column=0, columnspan=2, pady=5)

        self.status_var = tk.StringVar(value="Idle")
        ttk.Label(main, textvariable=self.status_var).grid(row=5, column=0, columnspan=2, sticky="w")

        columns = ["Speaker"] + FILLER_WORDS
        self.tree = ttk.Treeview(main, columns=columns, show="headings", height=5)
        for col in columns:
            self.tree.heading(col, text=col)
            self.tree.column(col, anchor="center")
        self.tree.grid(row=6, column=0, columnspan=2, sticky="nsew", pady=(5, 0))
        self.tree.bind("<<TreeviewSelect>>", self.on_tree_select)

        self.text_box = scrolledtext.ScrolledText(main, height=5, state="disabled", wrap="word")
        self.text_box.grid(row=7, column=0, columnspan=2, sticky="nsew", pady=(5, 0))

        main.columnconfigure(1, weight=1)
        main.rowconfigure(6, weight=1)
        main.rowconfigure(7, weight=1)

    def add_speaker(self):
        """Add a new speaker to the list and update UI widgets."""
        name = self.speaker_var.get().strip()
        if not name:
            return
        if name not in self.transcripts:
            self.transcripts[name] = ""
            self.update_table()
        self.speaker_var.set("")

    def on_tree_select(self, event):
        """Handle table selection and set the current speaker."""
        selection = self.tree.selection()
        if not selection:
            return
        item = self.tree.item(selection[0])
        self.current_speaker = item["values"][0]
        self.current_speaker_label.config(text=self.current_speaker)

    def start(self):
        if self.is_listening:
            return
        if not self.microphone_names:
            messagebox.showerror("Microphone Error", "No input device available")
            return
        device_name = self.device_var.get()
        try:
            device_index = self.microphone_names.index(device_name)
        except ValueError:
            messagebox.showerror("Microphone Error", "Selected input device is not available")
            return
        try:
            self.microphone = sr.Microphone(device_index=device_index)
        except Exception as exc:
            messagebox.showerror("Microphone Error", f"Unable to access microphone: {exc}")
            return
        self.is_listening = True
        self.status_var.set("Listening...")
        self.start_button.config(state="disabled")
        self.stop_button.config(state="normal")
        self.buffer = []
        if not self.current_speaker:
            messagebox.showerror("Speaker Error", "Please select a speaker from the table.")
            self.start_button.config(state="normal")
            self.stop_button.config(state="disabled")
            self.is_listening = False
            return
        self.transcripts.setdefault(self.current_speaker, "")
        self.text_box.config(state="normal")
        self.text_box.delete("1.0", "end")
        self.text_box.config(state="disabled")
        self.listen_thread = threading.Thread(target=self.listen_loop, daemon=True)
        self.listen_thread.start()

    def listen_loop(self):
        with self.microphone as source:
            self.recognizer.adjust_for_ambient_noise(source)
            while self.is_listening:
                try:
                    audio = self.recognizer.listen(
                        source, timeout=3, phrase_time_limit=5
                    )
                except sr.WaitTimeoutError:
                    # Stop if no speech is detected for the timeout period
                    self.root.after(0, self.stop)
                    break
                # Transcribe in a background thread so we don't block audio capture
                threading.Thread(
                    target=self.process_audio, args=(audio,), daemon=True
                ).start()

    def process_audio(self, audio: sr.AudioData) -> None:
        """Transcribe audio and update the UI when finished."""
        try:
            wav_data = audio.get_wav_data()
            audio_file = io.BytesIO(wav_data)
            audio_file.name = "audio.wav"
            response = openai.audio.transcriptions.create(
                model="gpt-4o-transcribe"
                ,file=audio_file)
            text = response.text
            self.buffer.append(text)
            self.root.after(0, self.handle_text, text)
        except (sr.UnknownValueError, openai.OpenAIError):
            pass

    def handle_text(self, text: str):
        """Update transcripts, text box and table with recognized text."""
        if not self.current_speaker:
            return
        self.transcripts[self.current_speaker] += " " + text
        self.text_box.config(state="normal")
        self.text_box.insert("end", text + " ")
        self.text_box.see("end")
        self.text_box.config(state="disabled")
        self.update_table()

    def update_table(self):
        counts = {spk: count_fillers(txt) for spk, txt in self.transcripts.items()}
        self.tree.delete(*self.tree.get_children())
        for spk, data in counts.items():
            values = [spk] + [data[word] for word in FILLER_WORDS]
            self.tree.insert("", "end", iid=spk, values=values)
        if self.current_speaker and self.current_speaker in self.tree.get_children():
            self.tree.selection_set(self.current_speaker)

    def stop(self):
        if not self.is_listening:
            return
        self.is_listening = False
        # Don't block the UI thread waiting for the listener thread to finish.
        # The thread will exit on its own once `is_listening` is False.
        self.listen_thread = None
        if self.microphone is not None:
            self.microphone = None

        self.buffer = []
        self.current_speaker = ""
        self.current_speaker_label.config(text="")
        self.status_var.set("Idle")
        self.start_button.config(state="normal")
        self.stop_button.config(state="disabled")

    def show_results(self):
        if not self.transcripts:
            messagebox.showinfo("Results", "No data collected.")
            return
        self.update_table()
        counts = {spk: count_fillers(text) for spk, text in self.transcripts.items()}
        headers = ["Speaker"] + FILLER_WORDS
        lines = ["\t".join(headers)]
        for spk, data in counts.items():
            row = [spk] + [str(data[word]) for word in FILLER_WORDS]
            lines.append("\t".join(row))
        messagebox.showinfo("Results", "\n".join(lines))


def main():
    root = tk.Tk()
    app = UmDetectorApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
