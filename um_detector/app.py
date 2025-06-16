import threading
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext

import pyaudio
import openai
import base64

from .detector import count_fillers, FILLER_WORDS


class UmDetectorApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Um Detector")
        self.audio = pyaudio.PyAudio()
        self.client = openai.OpenAI()
        self.realtime_manager = None
        self.realtime_conn = None
        self.event_thread = None
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
        self.speakers = []
        self.transcripts = {}
        self.current_speaker = ""

        # UI elements
        main = ttk.Frame(root, padding=10)
        main.grid(row=0, column=0, sticky="nsew")

        ttk.Label(main, text="Add speaker:").grid(row=0, column=0, sticky="w")
        self.new_speaker_var = tk.StringVar()
        ttk.Entry(main, textvariable=self.new_speaker_var).grid(row=0, column=1, sticky="ew")
        ttk.Button(main, text="Add", command=self.add_speaker).grid(row=0, column=2, padx=(5, 0))

        ttk.Label(main, text="Current speaker:").grid(row=1, column=0, sticky="w")
        self.speaker_var = tk.StringVar()
        self.speaker_combo = ttk.Combobox(main, textvariable=self.speaker_var, values=self.speakers, state="readonly")
        self.speaker_combo.grid(row=1, column=1, columnspan=2, sticky="ew")

        ttk.Label(main, text="Input device:").grid(row=2, column=0, sticky="w")
        self.device_combo = ttk.Combobox(main, textvariable=self.device_var, values=self.microphone_names, state="readonly")
        self.device_combo.grid(row=2, column=1, columnspan=2, sticky="ew")

        self.start_button = ttk.Button(main, text="Start", command=self.start,
                                        state="normal" if self.microphone_names else "disabled")
        self.start_button.grid(row=3, column=0, pady=5)
        self.stop_button = ttk.Button(main, text="End", command=self.stop, state="disabled")
        self.stop_button.grid(row=3, column=1, pady=5)

        self.show_button = ttk.Button(main, text="Show Results", command=self.show_results)
        self.show_button.grid(row=4, column=0, columnspan=3, pady=5)

        self.status_var = tk.StringVar(value="Idle")
        ttk.Label(main, textvariable=self.status_var).grid(row=5, column=0, columnspan=3, sticky="w")

        columns = ["Speaker"] + FILLER_WORDS
        self.tree = ttk.Treeview(main, columns=columns, show="headings", height=5)
        for col in columns:
            self.tree.heading(col, text=col)
            self.tree.column(col, anchor="center")
        self.tree.grid(row=6, column=0, columnspan=3, sticky="nsew", pady=(5, 0))

        self.text_box = scrolledtext.ScrolledText(main, height=5, state="disabled", wrap="word")
        self.text_box.grid(row=7, column=0, columnspan=3, sticky="nsew", pady=(5, 0))

        main.columnconfigure(1, weight=1)
        main.columnconfigure(2, weight=1)
        main.rowconfigure(6, weight=1)
        main.rowconfigure(7, weight=1)

        self.speaker_var.trace_add("write", self.on_speaker_selected)

    def add_speaker(self):
        name = self.new_speaker_var.get().strip()
        if not name:
            return
        if name not in self.speakers:
            self.speakers.append(name)
            self.transcripts.setdefault(name, "")
            self.speaker_combo["values"] = self.speakers
        self.speaker_var.set(name)
        self.new_speaker_var.set("")

    def on_speaker_selected(self, *args):
        self.current_speaker = self.speaker_var.get().strip() or "Unknown"
        self.transcripts.setdefault(self.current_speaker, "")
        if self.current_speaker not in self.speakers:
            self.speakers.append(self.current_speaker)
            self.speaker_combo["values"] = self.speakers
            self.speaker_var.set(self.current_speaker)

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
                rate=24000,
                input=True,
                input_device_index=device_index,
                frames_per_buffer=1024,
            )
        except Exception as exc:
            messagebox.showerror("Microphone Error", f"Unable to access microphone: {exc}")
            return
        self.is_listening = True
        self.status_var.set("Listening...")
        self.realtime_manager = self.client.beta.realtime.connect(model="gpt-4o-realtime-preview")
        self.realtime_conn = self.realtime_manager.enter()
        try:
            self.realtime_conn.session.update(session={"turn_detection": {"type": "server_vad"}})
        except Exception:
            pass
        self.event_thread = threading.Thread(target=self.event_loop, daemon=True)
        self.event_thread.start()
        self.start_button.config(state="disabled")
        self.stop_button.config(state="normal")
        self.current_speaker = self.speaker_var.get().strip() or "Unknown"
        self.transcripts.setdefault(self.current_speaker, "")
        self.text_box.config(state="normal")
        self.text_box.delete("1.0", "end")
        self.text_box.config(state="disabled")
        self.listen_thread = threading.Thread(target=self.listen_loop, daemon=True)
        self.listen_thread.start()

    def listen_loop(self):
        while self.is_listening:
            try:
                data = self.stream.read(1024, exception_on_overflow=False)
            except Exception:
                continue
            if self.realtime_conn is not None:
                try:
                    audio_b64 = base64.b64encode(data).decode("utf-8")
                    self.realtime_conn.input_audio_buffer.append(audio=audio_b64)
                except Exception:
                    pass

    def event_loop(self):
        if self.realtime_conn is None:
            return
        try:
            for event in self.realtime_conn:
                if not self.is_listening:
                    break
                if event.type == "conversation.item.input_audio_transcription.completed":
                    if getattr(event, "transcript", ""):
                        self.root.after(0, self.handle_text, event.transcript)
        finally:
            try:
                self.realtime_conn.close()
            except Exception:
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
        if self.event_thread is not None:
            self.event_thread = None
        if self.realtime_conn is not None:
            try:
                self.realtime_conn.close()
            except Exception:
                pass
            self.realtime_conn = None
        if self.realtime_manager is not None:
            self.realtime_manager = None
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
