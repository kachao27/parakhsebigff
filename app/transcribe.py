"""Audio transcription for videos and voice notes (faster-whisper, CPU, tiny
int8). The spoken pitch is where a deepfake's fraud actually lives - so the
claim-check must read it, not just the caption.

Graceful: if the model isn't available (e.g. the mac dev box without the
package), returns "" and the pipeline falls back to fingerprint + OCR. The
transcript only ever feeds the deterministic rules layer; it never becomes a
verdict on its own.
"""
import logging

log = logging.getLogger("parakh.transcribe")
_model = None


def _get_model():
    global _model
    if _model is None:
        from faster_whisper import WhisperModel
        _model = WhisperModel("tiny", device="cpu", compute_type="int8")
    return _model


def transcribe(media_path: str) -> str:
    """Return transcript text (en/hi auto-detected), or '' on any failure."""
    try:
        segments, _info = _get_model().transcribe(
            media_path, beam_size=1, vad_filter=True, language=None)
        return " ".join(s.text for s in segments).strip()
    except Exception as e:
        log.warning("transcription unavailable: %s", e)
        return ""
