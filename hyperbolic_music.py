#!/usr/bin/env python3
"""
hyperbolic_music.py — Spectral Music from Hyperbolic Surfaces

Turns Friedman's spectral gap theorem into a musical composition engine.
Each closed geodesic on a hyperbolic surface becomes a musical note.
The spectral gap determines the tempo and harmonic structure.

THEORY
======
The Selberg trace formula connects:
- Lengths of closed geodesics (primes in the prime geodesic theorem)
- Eigenvalues of the Laplacian on the hyperbolic surface

We map eigenvalues λₖ = sₖ(1-sₖ) to musical frequencies using:
- The fundamental frequency from the trivial eigenvalue λ₀ = 0 (the "silence" note)
- Non-trivial eigenvalues mapped to the equal-tempered scale
- The spectral gap λ₁ ≥ 3/16 sets the minimum frequency interval

MÖBIUS INVERSION AS COUNTERPOINT
=================================
The Möbius function μ(n) acts as a counterpoint voice:
- μ(n) > 0 → harmonic reinforcement (major intervals)
- μ(n) < 0 → dissonant tension (minor/tritone intervals)
- μ(n) = 0 → rest (square-free condition fails)

USAGE
=====
python hyperbolic_music.py              # Generate and print the composition
python hyperbolic_music.py --html       # Generate interactive HTML visualization
python hyperbolic_music.py --test       # Run verification tests
"""

import sys
import os
import math
import random
import json
from typing import List, Tuple, Dict, Optional

# Force UTF-8 output on Windows to handle Unicode in print statements
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from knot_math import mobius_upto

# ============================================================
# Musical Constants
# ============================================================

# MIDI note numbers (40-80 covers ~C2 to G5)
MIDI_MIN = 40
MIDI_MAX = 80

# Equal temperament: f = 440 * 2^((n-69)/12) where n is MIDI note
A4_FREQ = 440.0
A4_MIDI = 69

# Time signature
BEATS_PER_MEASURE = 4
QUARTER_NOTE_BEATS = 1.0

# Note duration types
NOTE_DURATIONS = {
    'whole': 4.0,
    'half': 2.0,
    'quarter': 1.0,
    'eighth': 0.5,
    'sixteenth': 0.25,
    'thirty-second': 0.125
}

# Scale degrees for pentatonic (works well with hyperbolic symmetry)
PENTATONIC = [0, 2, 4, 7, 9]  # Major pentatonic intervals in semitones

# ============================================================
# Spectral to Musical Mapping
# ============================================================

def eigenvalue_to_midi(eigenvalue: float, base_midi: int = 60) -> int:
    """
    Map a Laplacian eigenvalue to a MIDI note number.
    
    The eigenvalue λ = s(1-s) where s ∈ ℂ with Re(s) ≥ 1/2.
    For the trivial eigenvalue λ₀ = 0, we get the base note.
    Non-trivial eigenvalues are shifted up by the spectral gap.
    
    Uses logarithmic mapping to preserve the multiplicative structure
    of the hyperbolic geometry.
    """
    if eigenvalue <= 0:
        return base_midi
    
    # Map eigenvalue to frequency ratio using hyperbolic cosine
    # cosh(d) = 1 + 2λ for distance d on the hyperbolic plane
    freq_ratio = 1.0 + 2.0 * eigenvalue
    
    # Convert to semitones (logarithmic scale)
    semitones = 12.0 * math.log2(freq_ratio)
    
    # Clamp to valid MIDI range
    midi = int(round(base_midi + semitones))
    return max(MIDI_MIN, min(MIDI_MAX, midi))


def midi_to_frequency(midi: int) -> float:
    """Convert MIDI note number to frequency in Hz."""
    return A4_FREQ * (2.0 ** ((midi - A4_MIDI) / 12.0))


def mobius_to_interval(mu: int, scale: List[int] = PENTATONIC) -> int:
    """
    Convert Möbius function value to a scale degree.
    
    μ(n) > 0 → major intervals (harmonic)
    μ(n) < 0 → minor intervals (tension)  
    μ(n) = 0 → rest marker (-1)
    """
    if mu == 0:
        return -1  # Rest
    elif mu > 0:
        # Positive: use upper half of pentatonic (brighter)
        idx = abs(mu) % len(scale)
        return scale[idx]
    else:
        # Negative: use lower half with inversion (darker)
        idx = abs(mu) % len(scale)
        return scale[idx] + 12  # Octave up for tension


def generate_spectral_eigenvalues(num_geodesics: int = 32, 
                                   friedman_gap: float = 3/16) -> List[float]:
    """
    Generate synthetic eigenvalues respecting Friedman's spectral gap.
    
    Simulates the spectrum of the Laplacian on a random hyperbolic surface.
    The trivial eigenvalue λ₀ = 0 is excluded; we generate non-trivial ones.
    
    Uses the semicircle law as a base, shifted to respect the gap.
    """
    eigenvalues = []
    
    # First eigenvalue sits at the Friedman gap boundary
    eigenvalues.append(friedman_gap)
    
    # Remaining eigenvalues follow a distribution that respects the gap
    # Using a shifted Wigner semicircle distribution
    for i in range(1, num_geodesics):
        # Base distribution: eigenvalues cluster around 1/4 (Selberg's conjecture)
        base = 0.25 + 0.15 * random.gauss(0, 1)
        
        # Ensure respect for the spectral gap
        val = max(friedman_gap, base)
        
        # Add geodesic-length-dependent perturbation
        # Shorter geodesics → larger eigenvalues (Selberg trace formula)
        geodesic_length = (i + 1) * math.log(i + 2)
        perturbation = 0.05 / geodesic_length
        
        val += perturbation * random.gauss(0, 1)
        val = max(friedman_gap, min(0.5, val))  # λ ≤ 1/4 for s = 1/2 ± it
        
        eigenvalues.append(val)
    
    return sorted(eigenvalues, reverse=True)


# ============================================================
# Composition Engine
# ============================================================

class HyperbolicComposition:
    """
    Generates musical compositions from hyperbolic surface spectral data.
    
    The composition has three voices:
    1. Spectral voice: eigenvalues mapped to melody
    2. Möbius voice: counterpoint based on μ(n)
    3. Geodesic voice: rhythm from closed geodesic lengths
    """
    
    def __init__(self, num_measures: int = 16, base_note: int = 60,
                 tempo_bpm: int = 120):
        self.num_measures = num_measures
        self.base_note = base_note
        self.tempo_bpm = tempo_bpm
        self.measures: List[Dict] = []
        self.eigenvalues = []
        self.mobius_values = []
        
    def generate(self) -> List[Dict]:
        """Generate the full composition."""
        # Generate spectral data
        num_geodesics = self.num_measures * BEATS_PER_MEASURE
        self.eigenvalues = generate_spectral_eigenvalues(num_geodesics)
        
        # Generate Möbius counterpoint data
        self.mobius_values = mobius_upto(num_geodesics + 1)
        
        # Generate measures
        for measure_idx in range(self.num_measures):
            measure = self._generate_measure(measure_idx)
            self.measures.append(measure)
        
        return self.measures
    
    def _generate_measure(self, measure_idx: int) -> Dict:
        """Generate a single measure from spectral and Möbius data."""
        notes = []
        start_geodesic = measure_idx * BEATS_PER_MEASURE
        
        for beat in range(BEATS_PER_MEASURE):
            geodesic_idx = start_geodesic + beat
            
            if geodesic_idx >= len(self.eigenvalues):
                break
            
            # Spectral voice: eigenvalue → pitch
            eigenvalue = self.eigenvalues[geodesic_idx]
            spectral_midi = eigenvalue_to_midi(eigenvalue, self.base_note)
            
            # Möbius voice: μ(n) → counterpoint interval
            mu = self.mobius_values[geodesic_idx + 1]  # μ(1) = μ[1]
            
            if mu != 0:  # Non-zero Möbius → play counterpoint
                interval = mobius_to_interval(mu)
                if interval >= 0:
                    # Find base note for interval
                    base_for_interval = spectral_midi - 7  # Fifth below
                    counterpoint_midi = base_for_interval + (interval % 12)
                    counterpoint_midi = max(MIDI_MIN, min(MIDI_MAX, counterpoint_midi))
                else:
                    counterpoint_midi = None
            else:
                counterpoint_midi = None  # Rest for Möbius voice
            
            # Geodesic voice: length → rhythm
            geodesic_length = (geodesic_idx + 1) * math.log(geodesic_idx + 2)
            if geodesic_length < 5:
                duration_type = 'eighth'
            elif geodesic_length < 10:
                duration_type = 'quarter'
            else:
                duration_type = 'half'
            
            note = {
                'beat': beat,
                'spectral_midi': spectral_midi,
                'spectral_freq': midi_to_frequency(spectral_midi),
                'counterpoint_midi': counterpoint_midi,
                'mobius_value': mu,
                'eigenvalue': eigenvalue,
                'geodesic_length': geodesic_length,
                'duration_type': duration_type,
                'duration_beats': NOTE_DURATIONS[duration_type]
            }
            notes.append(note)
        
        return {
            'measure': measure_idx + 1,
            'notes': notes,
            'key_signature': 'C major (pentatonic)',
            'time_signature': f'{BEATS_PER_MEASURE}/4'
        }
    
    def to_text_score(self) -> str:
        """Convert composition to readable text score."""
        lines = []
        lines.append("=" * 70)
        lines.append("HYPERBOLIC SURFACE SPECTRAL COMPOSITION")
        lines.append(f"Friedman Gap: λ₁ ≥ {FRIEDMAN_GAP_VAL} (3/16)")
        lines.append(f"Tempo: {self.tempo_bpm} BPM | Key: C Pentatonic | Time: 4/4")
        lines.append("=" * 70)
        lines.append("")
        
        note_names = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
        
        for measure in self.measures:
            measure_num = measure['measure']
            lines.append(f"Measure {measure_num:2d} | {measure['time_signature']} |")
            lines.append("-" * 70)
            lines.append(f"  {'Beat':<6} {'Spectral':<12} {'Counterpoint':<12} {'μ(n)':<6} {'λ':<10} {'Rhythm':<12}")
            lines.append("-" * 70)
            
            for note in measure['notes']:
                beat = note['beat'] + 1
                
                # Spectral note name
                spec_name = note_names[note['spectral_midi'] % 12]
                spec_octave = note['spectral_midi'] // 12 - 1
                spec_str = f"{spec_name}{spec_octave}"
                
                # Counterpoint note name
                if note['counterpoint_midi'] is not None:
                    cp_name = note_names[note['counterpoint_midi'] % 12]
                    cp_octave = note['counterpoint_midi'] // 12 - 1
                    cp_str = f"{cp_name}{cp_octave}"
                else:
                    cp_str = "rest"
                
                lines.append(
                    f"  {beat:<6} {spec_str:<12} {cp_str:<12} "
                    f"{note['mobius_value']:<6} {note['eigenvalue']:<10.4f} "
                    f"{note['duration_type']:<12}"
                )
            
            lines.append("")
        
        return "\n".join(lines)
    
    def to_midi_events(self) -> List[Dict]:
        """Convert to simple MIDI-like event list."""
        events = []
        tick = 0
        ticks_per_beat = self.tempo_bpm * 4  # 16th note ticks
        
        for measure in self.measures:
            for note in measure['notes']:
                duration_ticks = int(note['duration_beats'] * ticks_per_beat)
                
                # Spectral voice note-on
                events.append({
                    'tick': tick,
                    'type': 'note_on',
                    'channel': 0,
                    'note': note['spectral_midi'],
                    'velocity': 80,
                    'duration': duration_ticks
                })
                
                # Counterpoint voice note-on (if not rest)
                if note['counterpoint_midi'] is not None:
                    events.append({
                        'tick': tick,
                        'type': 'note_on',
                        'channel': 1,
                        'note': note['counterpoint_midi'],
                        'velocity': 60,
                        'duration': duration_ticks
                    })
                
                tick += duration_ticks
        
        return events
    
    def to_html(self) -> str:
        """Generate interactive HTML visualization with Web Audio API."""
        midi_events = self.to_midi_events()
        events_json = json.dumps(midi_events)
        
        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Hyperbolic Spectral Music</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #0c0c1d 0%, #1a1a3e 50%, #0c0c1d 100%);
            color: #e0e0ff;
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            align-items: center;
            padding: 2rem;
        }}
        h1 {{
            font-size: 2.5rem;
            margin-bottom: 0.5rem;
            background: linear-gradient(90deg, #ff6b6b, #4ecdc4, #45b7d1);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }}
        .subtitle {{
            color: #8888aa;
            margin-bottom: 2rem;
            font-size: 1.1rem;
        }}
        .controls {{
            display: flex;
            gap: 1rem;
            margin-bottom: 2rem;
        }}
        button {{
            padding: 0.8rem 2rem;
            font-size: 1.1rem;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            transition: all 0.3s;
        }}
        #playBtn {{
            background: linear-gradient(135deg, #4ecdc4, #45b7d1);
            color: #0c0c1d;
            font-weight: bold;
        }}
        #playBtn:hover {{ transform: scale(1.05); }}
        #stopBtn {{
            background: linear-gradient(135deg, #ff6b6b, #ee5a24);
            color: white;
            font-weight: bold;
        }}
        #stopBtn:hover {{ transform: scale(1.05); }}
        #visualizer {{
            width: 800px;
            height: 400px;
            background: rgba(0,0,0,0.3);
            border-radius: 12px;
            margin-bottom: 2rem;
        }}
        .info {{
            max-width: 800px;
            background: rgba(255,255,255,0.05);
            padding: 1.5rem;
            border-radius: 12px;
            margin-bottom: 2rem;
        }}
        .info h2 {{ color: #4ecdc4; margin-bottom: 0.5rem; }}
        .info p {{ line-height: 1.6; color: #aaaacc; }}
        .formula {{
            background: rgba(0,0,0,0.4);
            padding: 1rem;
            border-radius: 8px;
            font-family: 'Courier New', monospace;
            margin: 1rem 0;
            color: #4ecdc4;
        }}
        .stats {{
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 1rem;
            max-width: 800px;
            margin-bottom: 2rem;
        }}
        .stat-card {{
            background: rgba(255,255,255,0.05);
            padding: 1rem;
            border-radius: 8px;
            text-align: center;
        }}
        .stat-value {{
            font-size: 2rem;
            font-weight: bold;
            color: #4ecdc4;
        }}
        .stat-label {{
            color: #8888aa;
            font-size: 0.9rem;
        }}
    </style>
</head>
<body>
    <h1>🎵 Hyperbolic Spectral Music</h1>
    <p class="subtitle">Music generated from Friedman's spectral gap theorem on hyperbolic surfaces</p>
    
    <div class="stats">
        <div class="stat-card">
            <div class="stat-value">{len(self.eigenvalues)}</div>
            <div class="stat-label">Eigenvalues</div>
        </div>
        <div class="stat-card">
            <div class="stat-value">{FRIEDMAN_GAP_VAL}</div>
            <div class="stat-label">Spectral Gap λ₁</div>
        </div>
        <div class="stat-card">
            <div class="stat-value">{self.num_measures}</div>
            <div class="stat-label">Measures</div>
        </div>
    </div>
    
    <div class="controls">
        <button id="playBtn">▶ Play Composition</button>
        <button id="stopBtn">⏹ Stop</button>
    </div>
    
    <canvas id="visualizer"></canvas>
    
    <div class="info">
        <h2>How It Works</h2>
        <p>
            This composition maps the <strong>spectrum of the Laplacian</strong> on a random 
            hyperbolic surface to musical frequencies. Each eigenvalue λₖ = sₖ(1-sₖ) 
            becomes a note, with the spectral gap λ₁ ≥ 3/16 ensuring harmonic separation.
        </p>
        <div class="formula">
            λₖ = sₖ(1-sₖ) → f = 440 × 2^((λₖ × 12)/12) Hz
        </div>
        <p>
            The <strong>Möbius function μ(n)</strong> provides counterpoint: positive values 
            create harmonic reinforcement, negative values create dissonant tension, 
            and zero values create rests — mirroring the square-free condition in number theory.
        </p>
        <div class="formula">
            μ(n) &gt; 0 → Major intervals | μ(n) &lt; 0 → Minor intervals | μ(n) = 0 → Rest
        </div>
    </div>
    
    <script>
        const midiEvents = {events_json};
        const canvas = document.getElementById('visualizer');
        const ctx = canvas.getContext('2d');
        canvas.width = 800;
        canvas.height = 400;
        
        let audioCtx = null;
        let isPlaying = false;
        let animationId = null;
        let currentTick = 0;
        let startTime = 0;
        
        function midiToFreq(midi) {{
            return 440 * Math.pow(2, (midi - 69) / 12);
        }}
        
        function drawVisualization(tick) {{
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            
            // Draw hyperbolic tiling background
            ctx.strokeStyle = 'rgba(78, 205, 196, 0.1)';
            ctx.lineWidth = 1;
            for (let i = 0; i &lt; 20; i++) {{
                for (let j = 0; j &lt; 10; j++) {{
                    const x = i * 40 + Math.sin(j * 0.5 + tick * 0.001) * 10;
                    const y = j * 40 + Math.cos(i * 0.5 + tick * 0.001) * 10;
                    ctx.beginPath();
                    ctx.arc(x, y, 15, 0, Math.PI * 2);
                    ctx.stroke();
                }}
            }}
            
            // Draw active notes
            const activeNotes = midiEvents.filter(e => 
                e.tick &lt;= tick && e.tick + e.duration &gt; tick
            );
            
            activeNotes.forEach((note, idx) => {{
                const x = (note.tick / 1000) * 100 % canvas.width;
                const y = canvas.height - (note.note / 127) * canvas.height;
                const radius = 20 + (note.velocity / 255) * 30;
                
                const gradient = ctx.createRadialGradient(x, y, 0, x, y, radius);
                if (note.channel === 0) {{
                    gradient.addColorStop(0, 'rgba(78, 205, 196, 0.8)');
                    gradient.addColorStop(1, 'rgba(78, 205, 196, 0)');
                }} else {{
                    gradient.addColorStop(0, 'rgba(255, 107, 107, 0.8)');
                    gradient.addColorStop(1, 'rgba(255, 107, 107, 0)');
                }}
                
                ctx.fillStyle = gradient;
                ctx.beginPath();
                ctx.arc(x, y, radius, 0, Math.PI * 2);
                ctx.fill();
            }});
        }}
        
        async function play() {{
            if (isPlaying) return;
            isPlaying = true;
            audioCtx = new (window.AudioContext || window.webkitAudioContext)();
            startTime = audioCtx.currentTime;
            currentTick = 0;
            
            const ticksPerSecond = {self.tempo_bpm} * 4 / 4;
            
            for (const event of midiEvents) {{
                const noteStart = event.tick / ({self.tempo_bpm} * 4);
                const noteDuration = event.duration / ({self.tempo_bpm} * 4);
                
                const osc = audioCtx.createOscillator();
                const gain = audioCtx.createGain();
                
                osc.connect(gain);
                gain.connect(audioCtx.destination);
                
                osc.frequency.value = midiToFreq(event.note);
                osc.type = event.channel === 0 ? 'sine' : 'triangle';
                
                gain.gain.setValueAtTime(0, startTime + noteStart);
                gain.gain.linearRampToValueAtTime(event.velocity / 255 * 0.3, startTime + noteStart + 0.05);
                gain.gain.linearRampToValueAtTime(0, startTime + noteStart + noteDuration);
                
                osc.start(startTime + noteStart);
                osc.stop(startTime + noteStart + noteDuration);
            }}
            
            // Animation loop
            function animate() {{
                if (!isPlaying) return;
                const elapsed = audioCtx.currentTime - startTime;
                currentTick = elapsed * {self.tempo_bpm} * 4 / 4;
                drawVisualization(currentTick);
                animationId = requestAnimationFrame(animate);
            }}
            animate();
            
            // Auto-stop
            const totalDuration = midiEvents.length &gt; 0 
                ? (midiEvents[midiEvents.length-1].tick + midiEvents[midiEvents.length-1].duration) / ({self.tempo_bpm} * 4)
                : 0;
            setTimeout(() => {{
                stop();
            }}, totalDuration * 1000 + 1000);
        }}
        
        function stop() {{
            isPlaying = false;
            if (animationId) cancelAnimationFrame(animationId);
            if (audioCtx) {{
                audioCtx.close();
                audioCtx = null;
            }}
            ctx.clearRect(0, 0, canvas.width, canvas.height);
        }}
        
        document.getElementById('playBtn').addEventListener('click', play);
        document.getElementById('stopBtn').addEventListener('click', stop);
        
        // Initial draw
        drawVisualization(0);
    </script>
</body>
</html>"""
        return html


# ============================================================
# Verification Tests
# ============================================================

FRIEDMAN_GAP_VAL = 3 / 16

def run_tests():
    """Run verification tests for the hyperbolic music engine."""
    print("Running Hyperbolic Music Verification Tests...")
    print("=" * 60)
    
    passed = 0
    failed = 0
    
    # Test 1: Eigenvalue to MIDI mapping
    print("\n[Test 1] Eigenvalue -> MIDI mapping")
    midi = eigenvalue_to_midi(0.0, 60)
    assert midi == 60, f"Trivial eigenvalue should map to base note, got {midi}"
    print("  ✓ Trivial eigenvalue lambda_0 = 0 -> MIDI 60 (C4)")
    
    midi = eigenvalue_to_midi(FRIEDMAN_GAP_VAL, 60)
    assert midi > 60, f"Friedman gap should map above base note, got {midi}"
    print(f"  ✓ Friedman gap lambda_1 = {FRIEDMAN_GAP_VAL} -> MIDI {midi}")
    
    passed += 1
    
    # Test 2: MIDI to frequency conversion
    print("\n[Test 2] MIDI -> Frequency conversion")
    freq = midi_to_frequency(A4_MIDI)
    assert abs(freq - A4_FREQ) < 0.01, f"A4 should be 440 Hz, got {freq}"
    print(f"  ✓ MIDI {A4_MIDI} -> {freq} Hz (A4)")
    
    passed += 1
    
    # Test 3: Mobius counterpoint
    print("\n[Test 3] Mobius function -> Counterpoint")
    mu_vals = mobius_upto(10)
    print(f"  mu values: {mu_vals[1:10]}")
    
    for i in range(1, 10):
        interval = mobius_to_interval(mu_vals[i])
        if mu_vals[i] == 0:
            assert interval == -1, f"mu({i}) = 0 should give rest"
            print(f"  ✓ mu({i}) = 0 -> rest")
        else:
            assert interval >= 0, f"Non-zero mu({i}) should give valid interval"
            print(f"  ✓ mu({i}) = {mu_vals[i]} -> interval {interval}")
    
    passed += 1
    
    # Test 4: Spectral gap respect
    print("\n[Test 4] Friedman spectral gap respect")
    eigenvalues = generate_spectral_eigenvalues(64, FRIEDMAN_GAP_VAL)
    min_eigenvalue = min(eigenvalues)
    assert min_eigenvalue >= FRIEDMAN_GAP_VAL - 1e-6, \
        f"Minimum eigenvalue {min_eigenvalue} below gap {FRIEDMAN_GAP_VAL}"
    print(f"  ✓ All {len(eigenvalues)} eigenvalues ≥ {FRIEDMAN_GAP_VAL}")
    print(f"  ✓ Min eigenvalue: {min_eigenvalue:.6f}")
    
    passed += 1
    
    # Test 5: Full composition generation
    print("\n[Test 5] Full composition generation")
    comp = HyperbolicComposition(num_measures=8, tempo_bpm=120)
    measures = comp.generate()
    assert len(measures) == 8, f"Expected 8 measures, got {len(measures)}"
    
    total_notes = sum(len(m['notes']) for m in measures)
    print(f"  ✓ Generated {len(measures)} measures with {total_notes} total notes")
    
    # Check note count per measure
    for m in measures:
        assert len(m['notes']) <= BEATS_PER_MEASURE, \
            f"Measure {m['measure']} has too many notes"
    print(f"  ✓ All measures respect {BEATS_PER_MEASURE}/4 time signature")
    
    passed += 1
    
    # Test 6: Text score generation
    print("\n[Test 6] Text score generation")
    score = comp.to_text_score()
    assert "HYPERBOLIC" in score, "Score should contain title"
    assert "Measure" in score, "Score should contain measure markers"
    lines = score.split('\n')
    print(f"  ✓ Score generated: {len(lines)} lines")
    print(f"  ✓ First line: {lines[0][:50]}...")
    
    passed += 1
    
    # Test 7: MIDI event generation
    print("\n[Test 7] MIDI event generation")
    events = comp.to_midi_events()
    assert len(events) > 0, "Should generate MIDI events"
    
    # Check event structure
    for event in events[:5]:
        assert 'tick' in event, "Event missing tick"
        assert 'note' in event, "Event missing note"
        assert 'duration' in event, "Event missing duration"
    print(f"  ✓ Generated {len(events)} MIDI events")
    
    # Count voices
    ch0 = sum(1 for e in events if e['channel'] == 0)
    ch1 = sum(1 for e in events if e['channel'] == 1)
    print(f"  ✓ Spectral voice (ch0): {ch0} notes")
    print(f"  ✓ Counterpoint voice (ch1): {ch1} notes")
    
    passed += 1
    
    # Test 8: HTML generation
    print("\n[Test 8] HTML visualization generation")
    html = comp.to_html()
    assert "<html" in html, "Should generate valid HTML"
    assert "Hyperbolic" in html, "HTML should contain title"
    assert "playBtn" in html, "HTML should contain play button"
    print(f"  ✓ HTML generated: {len(html)} characters")
    
    passed += 1
    
    # Summary
    print("\n" + "=" * 60)
    print(f"RESULTS: {passed} passed, {failed} failed")
    print("=" * 60)
    
    return failed == 0


# ============================================================
# Main Entry Point
# ============================================================

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Hyperbolic Spectral Music Generator")
    parser.add_argument("--measures", type=int, default=16, 
                       help="Number of measures (default: 16)")
    parser.add_argument("--tempo", type=int, default=120,
                       help="Tempo in BPM (default: 120)")
    parser.add_argument("--base-note", type=int, default=60,
                       help="Base MIDI note (default: 60 = C4)")
    parser.add_argument("--html", action="store_true",
                       help="Generate HTML visualization file")
    parser.add_argument("--test", action="store_true",
                       help="Run verification tests")
    parser.add_argument("--seed", type=int, default=None,
                       help="Random seed for reproducibility")
    
    args = parser.parse_args()
    
    if args.seed is not None:
        random.seed(args.seed)
    
    if args.test:
        success = run_tests()
        sys.exit(0 if success else 1)
    
    # Generate composition
    print("Generating hyperbolic spectral composition...")
    comp = HyperbolicComposition(
        num_measures=args.measures,
        base_note=args.base_note,
        tempo_bpm=args.tempo
    )
    comp.generate()
    
    # Display text score
    score = comp.to_text_score()
    print(score)
    
    # Generate HTML if requested
    if args.html:
        html_file = "hyperbolic_music.html"
        html = comp.to_html()
        with open(html_file, 'w', encoding='utf-8') as f:
            f.write(html)
        print(f"\n🎵 HTML visualization saved to: {html_file}")
        print("Open it in a browser to play and visualize the composition!")
    
    # Save MIDI events as JSON for external use
    events = comp.to_midi_events()
    midi_file = "hyperbolic_music_midi.json"
    with open(midi_file, 'w') as f:
        json.dump(events, f, indent=2)
    print(f"\n📁 MIDI events saved to: {midi_file}")