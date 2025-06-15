FILLER_WORDS = [
    "um",
    "uh",
    "i think",
    "you know",
    "like",
]

def count_fillers(text: str, fillers=FILLER_WORDS):
    """Return a dict mapping filler words to occurrence counts in text."""
    normalized = text.lower()
    counts = {}
    for word in fillers:
        counts[word] = normalized.count(word)
    return counts

def count_fillers_by_speaker(transcripts: dict, fillers=FILLER_WORDS):
    """Return nested mapping of speaker->filler->count."""
    result = {}
    for speaker, text in transcripts.items():
        result[speaker] = count_fillers(text, fillers)
    return result
