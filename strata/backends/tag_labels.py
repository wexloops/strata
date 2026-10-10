"""Zero-shot label vocabularies for CLAP tagging."""

GENRES = [
    "pop", "rock", "hip hop", "trap", "r&b", "soul", "funk", "disco", "house", "techno", "trance", "drum and bass",
    "dubstep", "uk garage", "ambient", "downtempo", "trip hop", "jazz", "classical", "orchestral", "cinematic score",
    "folk", "country", "metal", "punk", "indie rock", "psychedelic", "electronica", "idm", "experimental", "lo-fi",
    "reggae", "dub", "afrobeat", "latin", "baroque pop", "synthwave", "footwork", "jungle", "breakbeat", "gospel",
]
MOODS = [
    "euphoric", "melancholic", "aggressive", "tender", "dark", "dreamy", "tense", "triumphant", "playful", "calm",
    "anxious", "hypnotic", "nostalgic", "sensual", "eerie", "uplifting", "brooding", "chaotic", "serene", "epic",
]
INSTRUMENTS = [
    "drum machine", "acoustic drums", "bass guitar", "synth bass", "808", "electric guitar", "acoustic guitar",
    "piano", "electric piano", "organ", "synthesizer pads", "lead synth", "strings", "brass", "french horn",
    "saxophone", "flute", "harp", "harpsichord", "choir", "male vocals", "female vocals", "rap vocals",
    "vocal chops", "percussion", "bells", "sub bass", "arpeggiator", "turntable scratches", "field recordings",
]
PROMPTS = {
    "genre": "This is a {} track.",
    "mood": "The mood of this music is {}.",
    "instruments": "This music features {}.",
}
