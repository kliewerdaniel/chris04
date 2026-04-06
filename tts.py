import os
import time
import uuid
import numpy as np
from pathlib import Path
from typing import Optional

OUTPUT_DIR = Path("audio_outputs")
REFERENCE_AUDIO = Path("chris.wav")
REF_TEXT = "go get some carrots and yeah and the the bunny took off me but so I need well I got well I got the carrots but I lost my rabbit"

_tts_available = False


def _ensure_output_dir():
    OUTPUT_DIR.mkdir(exist_ok=True)


def generate_speech(text: str) -> Optional[str]:
    """Generate speech from text. Returns path to wav file or None."""
    _ensure_output_dir()

    global _tts_available
    if not _tts_available:
        try:
            from mlx_audio.tts.generate import generate_audio
            _tts_available = True
        except Exception as e:
            print(f"TTS unavailable: {e}")
            return _make_silent_wav()

    try:
        filename = f"{uuid.uuid4().hex}.wav"

        kwargs = {
            "text": text,
            "model": "mlx-community/Qwen3-TTS-12Hz-1.7B-Base-4bit",
            "output_path": str(OUTPUT_DIR),
            "file_prefix": Path(filename).stem,
            "audio_format": "wav",
            "verbose": False,
        }

        if REFERENCE_AUDIO.exists():
            kwargs["ref_audio"] = str(REFERENCE_AUDIO)
            kwargs["ref_text"] = REF_TEXT

        from mlx_audio.tts.generate import generate_audio
        generate_audio(**kwargs)

        wav_path = OUTPUT_DIR / f"{Path(filename).stem}_000.wav"
        if wav_path.exists():
            clean_path = OUTPUT_DIR / filename
            wav_path.rename(clean_path)
            _cleanup_old_files()
            return str(clean_path)

        return _make_silent_wav()

    except Exception as e:
        print(f"TTS error: {e}")
        return _make_silent_wav()


def _make_silent_wav() -> Optional[str]:
    """Create a short silent wav as fallback."""
    try:
        import soundfile as sf
        duration_s = 0.5
        sr = 24000
        samples = int(duration_s * sr)
        audio = np.zeros((samples,), dtype=np.float32)
        filename = f"{uuid.uuid4().hex}.wav"
        filepath = OUTPUT_DIR / filename
        sf.write(str(filepath), audio, samplerate=sr)
        return str(filepath)
    except Exception as e:
        print(f"Silent wav fallback failed: {e}")
        return None


def _cleanup_old_files():
    """Delete .wav files older than 1 hour."""
    try:
        cutoff = time.time() - 3600
        for filepath in OUTPUT_DIR.glob("*.wav"):
            if filepath.stat().st_mtime < cutoff:
                filepath.unlink()
    except Exception:
        pass
