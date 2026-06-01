"""
audio/sd_mixer.py — Mixer de UN SOLO GRAFO (motor audio-pro).

A diferencia de VLC (dos reproductores que mezcla el SO, lo que causaba tartamudeo
y caídas al solapar), aquí TODO se mezcla en numpy y sale por UNA sola salida de
audio (sounddevice/PortAudio). Cada "voz" (deck A/B para el crossfade, cuñas,
pisador/mic) tiene:

* `vol`  — amplitud estable (la usa el PISADOR/ducking: baja a 0.30 suave).
* `fade` — progreso 0..1 para fundidos; la amplitud aplica **potencia constante**
           `sin(fade·π/2)`. En un crossfade el entrante va fade 0→1 y el saliente
           1→0: la suma de potencias es constante (sin bache) y, al ser una sola
           mezcla por muestra, **no hay tartamudeo** entre streams.

Las ganancias se interpolan **por muestra** dentro de cada bloque (sample-accurate),
así que no hay saltos ni zipper. El núcleo (`Mixer`, `Voice`) usa SOLO numpy: se
puede `render()` a memoria/WAV sin tarjeta de sonido (tests). `SoundDeviceOutput`
importa sounddevice de forma diferida, solo al reproducir en vivo.
"""

from __future__ import annotations

import threading
import wave

import numpy as np

_HALF_PI = np.pi / 2.0


def _ramp(cur: float, target: float, step: float, n: int):
    """Devuelve (envolvente de n muestras de `cur`->`target` a `step`/muestra, nuevo cur)."""
    if step <= 0.0 or cur == target:
        return np.full(n, cur, dtype=np.float32), cur
    idx = np.arange(1, n + 1, dtype=np.float32)
    if cur < target:
        vals = cur + step * idx
        np.minimum(vals, target, out=vals)
    else:
        vals = cur - step * idx
        np.maximum(vals, target, out=vals)
    return vals, float(vals[-1])


class Voice:
    def __init__(self, source, samplerate: int, vol: float = 1.0,
                 fade: float = 1.0, on_finish=None, tag: str = "") -> None:
        self.source = source
        self.samplerate = samplerate
        self.vol = float(vol)
        self.vol_target = float(vol)
        self.vol_step = 0.0
        self.fade = float(fade)
        self.fade_target = float(fade)
        self.fade_step = 0.0
        self.stop_when_silent = False
        self.finished = False
        self.on_finish = on_finish
        self.tag = tag

    def set_fade(self, target: float, ms: float) -> None:
        target = max(0.0, min(1.0, target))
        dur = max(1.0, ms) / 1000.0
        self.fade_step = abs(target - self.fade) / (dur * self.samplerate) if ms > 0 else 1.0
        self.fade_target = target

    def set_vol(self, target: float, ms: float) -> None:
        target = max(0.0, min(1.0, target))
        dur = max(1.0, ms) / 1000.0
        self.vol_step = abs(target - self.vol) / (dur * self.samplerate) if ms > 0 else 1.0
        self.vol_target = target


class Mixer:
    def __init__(self, samplerate: int = 44100, channels: int = 2,
                 blocksize: int = 1024) -> None:
        self.samplerate = int(samplerate)
        self.channels = int(channels)
        self.blocksize = int(blocksize)
        self.master = 1.0
        self.level_l = 0.0          # VU REAL (pico por canal del último bloque mezclado)
        self.level_r = 0.0
        self._voices: list[Voice] = []
        self._lock = threading.RLock()

    # ----------------------------------------------------------------- voces
    def add(self, voice: Voice) -> Voice:
        with self._lock:
            self._voices.append(voice)
        return voice

    def remove(self, voice: Voice) -> None:
        with self._lock:
            if voice in self._voices:
                self._voices.remove(voice)

    def voices(self, tag: str | None = None) -> list[Voice]:
        with self._lock:
            if tag is None:
                return list(self._voices)
            return [v for v in self._voices if v.tag == tag]

    def clear(self) -> None:
        with self._lock:
            vs = list(self._voices)
            self._voices.clear()
        for v in vs:
            self._close(v)

    @staticmethod
    def _close(v: Voice) -> None:
        try:
            v.source.close()
        except Exception:
            pass

    # ----------------------------------------------------------------- mezcla
    def mix(self, frames: int) -> np.ndarray:
        out = np.zeros((frames, self.channels), dtype=np.float32)
        with self._lock:
            voices = list(self._voices)
        finished: list[Voice] = []
        for v in voices:
            data = v.source.read(frames)                       # (frames, ch)
            vol_env, v.vol = _ramp(v.vol, v.vol_target, v.vol_step, frames)
            fade_env, v.fade = _ramp(v.fade, v.fade_target, v.fade_step, frames)
            amp = vol_env * np.sin(np.clip(fade_env, 0.0, 1.0) * _HALF_PI)   # equal-power
            out += data * amp[:, None]
            if getattr(v.source, "finished", False):
                v.finished = True
            if v.stop_when_silent and v.fade_target <= 0.0 and v.fade <= 1e-4:
                v.finished = True
            if v.finished:
                finished.append(v)
        if finished:
            with self._lock:
                for v in finished:
                    if v in self._voices:
                        self._voices.remove(v)
            for v in finished:
                self._close(v)
                if v.on_finish:
                    try:
                        v.on_finish(v)
                    except Exception:
                        pass
        out *= self.master
        np.clip(out, -1.0, 1.0, out=out)
        if frames:
            self.level_l = float(np.abs(out[:, 0]).max())
            self.level_r = float(np.abs(out[:, -1]).max())
        return out

    # --------------------------------------------------- render offline (tests)
    def render(self, frames_total: int, block: bool = True) -> np.ndarray:
        """Mezcla `frames_total` muestras a memoria (tests/demo). `block=True` deja
        que el decoder espere a ffmpeg (sin falsos huecos al ir más rápido que el
        tiempo real)."""
        if block:
            for v in self.voices():
                if hasattr(v.source, "blocking"):
                    v.source.blocking = True
        chunks = []
        done = 0
        while done < frames_total:
            n = min(self.blocksize, frames_total - done)
            chunks.append(self.mix(n))
            done += n
        return np.concatenate(chunks, axis=0) if chunks else np.zeros((0, self.channels), np.float32)


def write_wav(path: str, samples: np.ndarray, samplerate: int) -> None:
    """Escribe un WAV PCM16 desde float32 [-1,1] (para tests / demo audible)."""
    data = np.clip(samples, -1.0, 1.0)
    pcm = (data * 32767.0).astype("<i2")
    ch = samples.shape[1] if samples.ndim > 1 else 1
    with wave.open(path, "wb") as w:
        w.setnchannels(ch)
        w.setsampwidth(2)
        w.setframerate(samplerate)
        w.writeframes(pcm.tobytes())


class SoundDeviceOutput:
    """Salida real por PortAudio. Importa sounddevice de forma diferida (solo en vivo)."""

    def __init__(self, mixer: Mixer, device=None) -> None:
        self.mixer = mixer
        self.device = device
        self._stream = None

    def start(self) -> None:
        import sounddevice as sd
        self._stream = sd.OutputStream(
            samplerate=self.mixer.samplerate, channels=self.mixer.channels,
            blocksize=self.mixer.blocksize, dtype="float32",
            device=self.device, callback=self._callback,
        )
        self._stream.start()

    def _callback(self, outdata, frames, time_info, status) -> None:  # noqa: ARG002
        outdata[:] = self.mixer.mix(frames)

    def stop(self) -> None:
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None
