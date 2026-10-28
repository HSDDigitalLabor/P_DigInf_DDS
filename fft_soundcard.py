import re
import shutil
import subprocess
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation

SAMPLERATE = 44100
CHUNK = 4096
SMOOTHING = 0.65
PEAK_DECAY = 0.4
CENTER_ZERO = True


def find_analog_soundcard():
    """Durchsucht das System automatisch nach einer analogen Soundkarte (Card & Device)."""
    try:
        result = subprocess.run(["arecord", "-l"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
    except Exception as e:
        print(f"Fehler beim Aufruf von 'arecord -l': {e}")
        return 1, 0

    cards = []
    pattern = re.compile(r"card\s+(\d+):\s+([^\[]+).*?device\s+(\d+):\s+([^\n]+)")
    
    for match in pattern.finditer(result.stdout):
        card_id = int(match.group(1))
        card_name = match.group(2).strip()
        dev_id = int(match.group(3))
        dev_name = match.group(4).strip()
        
        full_desc = f"{card_name} {dev_name}".lower()
        if any(bad in full_desc for bad in ["hdmi", "digital", "spdif", "loopback", "dummy"]):
            continue
            
        score = 0
        if any(good in full_desc for good in ["analog", "alc", "built-in", "pch", "intel", "realtek", "codec"]):
            score += 10
        if "usb" in full_desc:
            score += 5
            
        cards.append({"card": card_id, "device": dev_id, "name": f"{card_name} -> {dev_name}", "score": score})

    if not cards:
        print("Keine eindeutige analoge Soundkarte gefunden! Verwende Standard (Card 0, Device 0).")
        return 0, 0

    cards.sort(key=lambda x: x["score"], reverse=True)
    best = cards[0]
    
    print(f"Automatisch erkannte Soundkarte: Card {best['card']}, Device {best['device']} ({best['name']})")
    return best["card"], best["device"]


def setup_mixer_smart(card):
    """Konfiguriert den Mixer der erkannten Karte dynamisch (schaltet Loopback/Boosts ab)."""
    print(f"Konfiguriere Hardware-Mixer für Card {card}...")
    
    try:
        ctrls_res = subprocess.run(["amixer", "-c", str(card), "scontrols"], stdout=subprocess.PIPE, text=True, check=True)
        controls = ctrls_res.stdout
    except Exception:
        controls = ""

    mixer_commands = [
        ["Loopback Mixing", "Disabled"],
        ["Line", "0%", "mute"],
        ["Rear Mic", "0%", "mute"],
        ["Front Mic", "0%", "mute"],
        ["Mic", "0%", "mute"],
        ["Line Boost", "0%"],
        ["Rear Mic Boost", "0%"],
        ["Front Mic Boost", "0%"],
        ["Mic Boost", "0%"],
        ["Capture", "65%", "cap", "unmute"],
    ]

    for args in mixer_commands:
        if len(args) > 1 and (args[0].lower() in controls.lower() or "loopback" in args[0].lower() or "capture" in args[0].lower()):
            subprocess.run(["amixer", "-c", str(card), "sset"] + args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    for src in ["Line", "Rear Mic", "Mic", "Front Mic"]:
        res = subprocess.run(["amixer", "-c", str(card), "sset", "Input Source,0", src], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if res.returncode == 0:
            print(f"Aufnahmequelle erfolgreich auf '{src}' gesetzt.")
            break

    if shutil.which("pactl"):
        subprocess.run(["pactl", "unload-module", "module-loopback"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def start_audio_capture(card, device, rate, chunk):
    alsa_dev = f"plughw:{card},{device}"
    base_cmd = ["arecord", "-D", alsa_dev, "-f", "S16_LE", "-c", "1", "-r", str(rate), "-t", "raw", "-q"]
    cmd = ["pasuspender", "--"] + base_cmd if shutil.which("pasuspender") else base_cmd

    print(f"Starte Audio-Capture auf {alsa_dev}...")
    return subprocess.Popen(cmd, stdout=subprocess.PIPE, bufsize=chunk * 2)


# --- 1. AUTOMATISCHER START & HARDWARE SETUP ---
CARD_NUM, DEVICE_NUM = find_analog_soundcard()
setup_mixer_smart(CARD_NUM)
proc = start_audio_capture(CARD_NUM, DEVICE_NUM, SAMPLERATE, CHUNK)

# --- 2. PLOT SETUP (Oszilloskop + Volles Spiegelspektrum) ---
fig, (ax_osc, ax_fft) = plt.subplots(2, 1, figsize=(12, 7), gridspec_kw={'height_ratios': [1, 2.2]})
fig.canvas.manager.set_window_title(f"Audio-Diagnose (Auto-Detected plughw:{CARD_NUM},{DEVICE_NUM})")

# Oszilloskop (10 ms Ausschnitt)
osc_samples = int(SAMPLERATE * 0.010)
t_ms = np.arange(osc_samples) * 1000.0 / SAMPLERATE
line_osc, = ax_osc.plot(t_ms, np.zeros(osc_samples), color='#00b0ff', lw=1.5)
ax_osc.axhline(1.0, color='#ff1744', ls='--', lw=1.0, label='Clipping-Grenze (0 dBFS)')
ax_osc.axhline(-1.0, color='#ff1744', ls='--', lw=1.0)
ax_osc.set_xlim(0, 10)
ax_osc.set_ylim(-1.15, 1.15)
ax_osc.set_ylabel('Amplitude')
ax_osc.set_xlabel('Zeit [ms]')
ax_osc.set_title('Live-Oszilloskop (Zeitsignal)')
ax_osc.grid(True, linestyle='--', alpha=0.4)
ax_osc.legend(loc='upper right', fontsize=8)
clip_warning = ax_osc.text(0.02, 0.80, '', transform=ax_osc.transAxes, color='white',
                           fontweight='bold', bbox=dict(facecolor='#d50000', alpha=0.9))

# Volles FFT-Spektrum mit Spiegelung
nyquist = SAMPLERATE / 2.0
freqs = np.fft.fftshift(np.fft.fftfreq(CHUNK, d=1.0 / SAMPLERATE)) if CENTER_ZERO else np.arange(CHUNK) * (SAMPLERATE / CHUNK)
mask_pos = (freqs >= 0) if CENTER_ZERO else (freqs <= nyquist)
mask_mirror = (freqs <= 0) if CENTER_ZERO else (freqs >= nyquist)

if CENTER_ZERO:
    ax_fft.axvspan(-nyquist, 0, color='#3d5afe', alpha=0.07, label='Spiegelbereich (-f)')
    ax_fft.axvspan(0, nyquist, color='#00e676', alpha=0.07, label='Nutzsignal (+f)')
    ax_fft.axvline(0, color='#ffab00', lw=1.5, ls='-.', label='0 Hz (Symmetrieachse)')
    ax_fft.set_xlim(-nyquist, nyquist)
else:
    ax_fft.axvspan(0, nyquist, color='#00e676', alpha=0.07, label='Nutzsignal')
    ax_fft.axvspan(nyquist, SAMPLERATE, color='#3d5afe', alpha=0.07, label='Spiegelbereich')
    ax_fft.axvline(nyquist, color='#ffab00', lw=1.5, ls='-.', label='Nyquist-Grenze')
    ax_fft.set_xlim(0, SAMPLERATE)

line_pos, = ax_fft.plot(freqs[mask_pos], np.full(np.sum(mask_pos), -100.0), color='#00c853', lw=1.5, label='Reales Spektrum')
line_mirror, = ax_fft.plot(freqs[mask_mirror], np.full(np.sum(mask_mirror), -100.0), color='#536dfe', lw=1.5, alpha=0.85, label='Gespiegeltes Spektrum')
line_peak, = ax_fft.plot(freqs, np.full(CHUNK, -100.0), color='#ff5252', lw=0.8, alpha=0.6, ls='--', label='Peak Hold')

peak_text = ax_fft.text(0.02, 0.90, '', transform=ax_fft.transAxes, color='black',
                        fontweight='bold', bbox=dict(facecolor='white', alpha=0.85, edgecolor='#cccccc'))

ax_fft.set_ylim(-100, 5)
ax_fft.axhline(0, color='#ff1744', ls=':', lw=1.0)
ax_fft.set_xlabel('Frequenz [Hz]')
ax_fft.set_ylabel('Pegel [dBFS]')
ax_fft.grid(True, which='both', linestyle='--', alpha=0.4)
ax_fft.legend(loc='upper right', fontsize=8)

window = np.blackman(CHUNK)
smoothed_db = np.full(CHUNK, -90.0)
peak_hold_db = np.full(CHUNK, -90.0)

def update_plot(frame):
    global smoothed_db, peak_hold_db

    raw_bytes = proc.stdout.read(CHUNK * 2)
    if len(raw_bytes) == CHUNK * 2:
        data = np.frombuffer(raw_bytes, dtype=np.int16) / 32768.0
        
        # Übersteuerungs-Warnung
        max_amp = np.max(np.abs(data))
        if max_amp >= 0.98:
            clip_warning.set_text(f" WARNUNG: EINGANG ÜBERSTEUERT ({max_amp*100:.0f}%)! Pegel an der Quelle oder im Alsamixer reduzieren! ")
        else:
            clip_warning.set_text("")

        # Trigger für Oszilloskop
        zero_crossings = np.where((data[:-osc_samples-1] < 0) & (data[1:-osc_samples] >= 0))[0]
        start_idx = zero_crossings[0] if len(zero_crossings) > 0 else 0
        line_osc.set_ydata(data[start_idx : start_idx + osc_samples])
        
        # Voll-FFT mit korrigierter Normierung
        data_ac = data - np.mean(data)
        fft_complex = np.fft.fft(data_ac * window) * 2.0 / np.sum(window)
        if CENTER_ZERO:
            fft_complex = np.fft.fftshift(fft_complex)
            
        current_db = 20 * np.log10(np.maximum(np.abs(fft_complex), 1e-10))
        
        smoothed_db = SMOOTHING * smoothed_db + (1.0 - SMOOTHING) * current_db
        peak_hold_db = np.maximum(peak_hold_db - PEAK_DECAY, smoothed_db)
        
        line_pos.set_ydata(smoothed_db[mask_pos])
        line_mirror.set_ydata(smoothed_db[mask_mirror])
        line_peak.set_ydata(peak_hold_db)
        
        valid_pos = np.where((freqs > 30) & (freqs < nyquist))[0]
        max_idx = valid_pos[np.argmax(smoothed_db[valid_pos])]
        noise_floor = np.median(smoothed_db)
        snr = smoothed_db[max_idx] - noise_floor
        
        peak_text.set_text(
            f"Peak: {freqs[max_idx]:.1f} Hz ({smoothed_db[max_idx]:.1f} dBFS) | "
            f"Noise Floor: {noise_floor:.1f} dBFS | SNR: {snr:.1f} dB"
        )

    return line_osc, clip_warning, line_pos, line_mirror, line_peak, peak_text

try:
    ani = FuncAnimation(fig, update_plot, interval=20, blit=False, cache_frame_data=False)
    plt.tight_layout()
    plt.show()
finally:
    proc.terminate()
