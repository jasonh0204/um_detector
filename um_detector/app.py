import threading
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext

import pyaudio
import wave
import openai
import tempfile
import time

from .detector import count_fillers, FILLER_WORDS


class UmDetectorApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Um Detector")
        self.audio = pyaudio.PyAudio()
        self.devices = []
        for i in range(self.audio.get_device_count()):
            info = self.audio.get_device_info_by_index(i)
            if info.get("maxInputChannels", 0) > 0:
                self.devices.append((i, info["name"]))
        self.microphone_names = [name for _, name in self.devices]
        if not self.microphone_names:
            messagebox.showerror("Microphone Error", "No input devices found.")
            self.microphone_names = []
        self.device_var = tk.StringVar(value=self.microphone_names[0] if self.microphone_names else "")
        self.stream = None

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

        ttk.Label(main, text="Input device:").grid(row=1, column=0, sticky="w")
        self.device_combo = ttk.Combobox(main, textvariable=self.device_var, values=self.microphone_names, state="readonly")
        self.device_combo.grid(row=1, column=1, sticky="ew")

        self.start_button = ttk.Button(main, text="Start", command=self.start,
                                        state="normal" if self.microphone_names else "disabled")
        self.start_button.grid(row=2, column=0, pady=5)
        self.stop_button = ttk.Button(main, text="End", command=self.stop, state="disabled")
        self.stop_button.grid(row=2, column=1, pady=5)

        self.show_button = ttk.Button(main, text="Show Results", command=self.show_results)
        self.show_button.grid(row=3, column=0, columnspan=2, pady=5)

        self.status_var = tk.StringVar(value="Idle")
        ttk.Label(main, textvariable=self.status_var).grid(row=4, column=0, columnspan=2, sticky="w")

        columns = ["Speaker"] + FILLER_WORDS
        self.tree = ttk.Treeview(main, columns=columns, show="headings", height=5)
        for col in columns:
            self.tree.heading(col, text=col)
            self.tree.column(col, anchor="center")
        self.tree.grid(row=5, column=0, columnspan=2, sticky="nsew", pady=(5, 0))

        self.text_box = scrolledtext.ScrolledText(main, height=5, state="disabled", wrap="word")
        self.text_box.grid(row=6, column=0, columnspan=2, sticky="nsew", pady=(5, 0))

        main.columnconfigure(1, weight=1)
        main.rowconfigure(5, weight=1)
        main.rowconfigure(6, weight=1)

    def start(self):
        if self.is_listening:
            return
        if not self.microphone_names:
            messagebox.showerror("Microphone Error", "No input device available")
            return
        device_name = self.device_var.get()
        try:
            device_index = next(i for i, name in self.devices if name == device_name)
        except StopIteration:
            messagebox.showerror("Microphone Error", "Selected input device is not available")
            return
        try:
            self.stream = self.audio.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=16000,
                input=True,
                input_device_index=device_index,
                frames_per_buffer=1024,
            )
        except Exception as exc:
            messagebox.showerror("Microphone Error", f"Unable to access microphone: {exc}")
            return
        self.is_listening = True
        self.status_var.set("Listening...")
        self.start_button.config(state="disabled")
        self.stop_button.config(state="normal")
        self.buffer = []
        self.current_speaker = self.speaker_var.get().strip() or "Unknown"
        self.transcripts.setdefault(self.current_speaker, "")
        self.text_box.config(state="normal")
        self.text_box.delete("1.0", "end")
        self.text_box.config(state="disabled")
        self.listen_thread = threading.Thread(target=self.listen_loop, daemon=True)
        self.listen_thread.start()

    def listen_loop(self):
        frames = []
        start_time = time.time()
        while self.is_listening:
            try:
                data = self.stream.read(1024, exception_on_overflow=False)
            except Exception:
                continue
            frames.append(data)
            if time.time() - start_time >= 5:
                audio_bytes = b"".join(frames)
                frames = []
                start_time = time.time()
                threading.Thread(
                    target=self.process_audio, args=(audio_bytes,), daemon=True
                ).start()
        if frames:
            threading.Thread(
                target=self.process_audio, args=(b"".join(frames),), daemon=True
            ).start()

    def process_audio(self, data: bytes) -> None:
        """Transcribe raw audio bytes and update the UI when finished."""
        if not data:
            return
        with tempfile.NamedTemporaryFile(suffix=".wav") as tmp:
            wf = wave.open(tmp.name, "wb")
            wf.setnchannels(1)
            wf.setsampwidth(self.audio.get_sample_size(pyaudio.paInt16))
            wf.setframerate(16000)
            wf.writeframes(data)
            wf.close()
            tmp.seek(0)
            try:
                result = openai.Audio.transcribe("whisper-1", tmp)
                text = result.get("text", "")
                if text:
                    self.buffer.append(text)
                    self.root.after(0, self.handle_text, text)
            except openai.OpenAIError:
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
            self.tree.insert("", "end", values=values)

    def stop(self):
        if not self.is_listening:
            return
        self.is_listening = False
        # Don't block the UI thread waiting for the listener thread to finish.
        # The thread will exit on its own once `is_listening` is False.
        self.listen_thread = None
        if self.stream is not None:
            try:
                self.stream.stop_stream()
                self.stream.close()
            finally:
                self.stream = None
        if self.audio is not None:
            try:
                self.audio.terminate()
            except Exception:
                pass
            self.audio = pyaudio.PyAudio()

        self.buffer = []
        self.current_speaker = ""
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
