# Third-party backends

| Backend | Code license | Weights license | Profile |
|---|---|---|---|
| All-In-One (mir-aidj/all-in-one, vendored + PR #39) | MIT | MIT | core |
| Demucs (htdemucs) | MIT | MIT | core |
| Beat This! (CPJKU) | MIT | MIT | core |
| BTC chord recognition (vendored in strata/backends/btc) | MIT | MIT | core |
| S-KEY (Deezer) | MIT | MIT | core |
| basic-pitch (Spotify) | Apache-2.0 | Apache-2.0 | core |
| librosa | ISC | n/a | core |
| pyloudnorm | MIT | n/a | core |
| faster-whisper / Whisper large-v3-turbo | MIT | MIT | extra `[lyrics]` |
| LAION CLAP (larger_clap_music) | CC0 | Apache-2.0 | extra `[tags]`, disabled by default |
| madmom signal processing + DBN (used by allin1) | BSD-3 | none (no neural models loaded) | core |
| madmom neural beats / key / chords | BSD-3 | **CC BY-NC-SA 4.0** | NC: on in `full`, excluded by `commercial-safe` |

madmom's model files arrive with the user's own pip install; this repo never redistributes them. Only the three `madmom_*` backends load them.
