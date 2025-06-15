import threading
import tkinter as tk
from tkinter import ttk, messagebox

import speech_recognition as sr

from .detector import count_fillers, FILLER_WORDS


class UmDetectorApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Um Detector")
        self.recognizer = sr.Recognizer()
        try:
            self.microphone = sr.Microphone()
        except Exception as exc:
            messagebox.showerror("Microphone Error", f"Unable to access microphone: {exc}")
            raise

        self.is_listening = False
        self.listen_thread = None
        self.buffer = []
        self.transcripts = {}

        # UI elements
        main = ttk.Frame(root, padding=10)
        main.grid(row=0, column=0, sticky="nsew")

        ttk.Label(main, text="Speaker name:").grid(row=0, column=0, sticky="w")
        self.speaker_var = tk.StringVar()
        ttk.Entry(main, textvariable=self.speaker_var).grid(row=0, column=1, sticky="ew")

        self.start_button = ttk.Button(main, text="Start", command=self.start)
        self.start_button.grid(row=1, column=0, pady=5)
        self.stop_button = ttk.Button(main, text="End", command=self.stop, state="disabled")
        self.stop_button.grid(row=1, column=1, pady=5)

        self.show_button = ttk.Button(main, text="Show Results", command=self.show_results)
        self.show_button.grid(row=2, column=0, columnspan=2, pady=5)

        self.status_var = tk.StringVar(value="Idle")
        ttk.Label(main, textvariable=self.status_var).grid(row=3, column=0, columnspan=2, sticky="w")

        main.columnconfigure(1, weight=1)

    def start(self):
        if self.is_listening:
            return
        self.is_listening = True
        self.status_var.set("Listening...")
        self.start_button.config(state="disabled")
        self.stop_button.config(state="normal")
        self.buffer = []
        self.listen_thread = threading.Thread(target=self.listen_loop, daemon=True)
        self.listen_thread.start()

    def listen_loop(self):
        with self.microphone as source:
            self.recognizer.adjust_for_ambient_noise(source)
            while self.is_listening:
                audio = self.recognizer.listen(source, phrase_time_limit=5)
                try:
                    text = self.recognizer.recognize_google(audio)
                    self.buffer.append(text)
                except sr.UnknownValueError:
                    continue

    def stop(self):
        if not self.is_listening:
            return
        self.is_listening = False
        if self.listen_thread is not None:
            self.listen_thread.join()

        speaker = self.speaker_var.get().strip() or "Unknown"
        transcript = " ".join(self.buffer)
        self.transcripts.setdefault(speaker, "")
        self.transcripts[speaker] += " " + transcript
        self.status_var.set("Idle")
        self.start_button.config(state="normal")
        self.stop_button.config(state="disabled")

    def show_results(self):
        if not self.transcripts:
            messagebox.showinfo("Results", "No data collected.")
            return
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
