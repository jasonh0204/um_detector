# um_detector

A small desktop application that listens to speech and counts common filler words ("um", "uh", "I think", "you know", "like").

## Requirements

- Python 3.11+
- [SpeechRecognition](https://pypi.org/project/SpeechRecognition/)
- [PyAudio](https://pypi.org/project/PyAudio/) (requires PortAudio development headers)

Install dependencies with:

```bash
pip install -r requirements.txt
```

On Linux you may need `portaudio` packages, e.g. `apt-get install portaudio19-dev` before installing `pyaudio`.

## Running

Execute the application using:

```bash
python -m um_detector.app
```

Enter the speaker name, choose the desired input device from the drop-down list and click **Start** to begin recording. Click **End** when the speaker finishes. When all speakers are done, click **Show Results** to display a table of filler word counts per participant.

## Tests

Run unit tests with:

```bash
pytest
```
