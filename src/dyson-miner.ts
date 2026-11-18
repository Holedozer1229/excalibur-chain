import { wsHub } from "./ws-hub";

/**
 * QUANTUM GRAVITY MINER — VALKNUT DIAL v9 + DYSON SPHERE EQUILIBRIUM
 * TypeScript port of the Quantum Gravity Miner with Spectral Lattice Correlation.
 *
 * Synthesizes:
 *  • Riemann zeta spectral gaps (Δtₙ)
 *  • Quaternion 1/2 prime resonator lattice (quantum gaps ΔEₙ)
 *  • R₉₀ rotational symmetry
 *  • Valknut dial v9: spectral cube, Berry flow, quantum-Fibonacci, Dyson equilibrium
 *  • Dyson Sphere relativistic pressure balance factor
 */

import { createHash } from "crypto";

// ─── Prime Generation (Miller-Rabin) ─────────────────────────────────────────

function isPrimeMR(n: number): boolean {
  if (n < 2) return false;
  if (n === 2 || n === 3) return true;
  if (n % 2 === 0) return false;
  let d = n - 1;
  let s = 0;
  while (d % 2 === 0) { d = Math.floor(d / 2); s++; }
  for (let i = 0; i < 5; i++) {
    const a = 2 + Math.floor(Math.random() * (n - 3));
    let x = modPow(a, d, n);
    if (x === 1 || x === n - 1) continue;
    let cont = false;
    for (let r = 0; r < s - 1; r++) {
      x = modPow(x, 2, n);
      if (x === n - 1) { cont = true; break; }
    }
    if (!cont) return false;
  }
  return true;
}

function modPow(base: number, exp: number, mod: number): number {
  let result = 1;
  base = base % mod;
  while (exp > 0) {
    if (exp % 2 === 1) result = (result * base) % mod;
    exp = Math.floor(exp / 2);
    base = (base * base) % mod;
  }
  return result;
}

function generatePrimes(n: number): number[] {
  const primes: number[] = [];
  let num = 2;
  while (primes.length < n) {
    if (isPrimeMR(num)) primes.push(num);
    num++;
  }
  return primes;
}

// ─── Riemann Zeta Zeros (Approximate) ────────────────────────────────────────

const KNOWN_ZEROS = [
  14.134725141734693, 21.022039638771554, 25.010857580145688,
  30.424876125859513, 32.935061587739189, 37.586178158825671,
  40.918719012147495, 43.327073280914999, 48.005150881167159,
  49.773832477672302,
];

function zetaZeroApprox(n: number): number {
  if (n <= KNOWN_ZEROS.length) return KNOWN_ZEROS[n - 1];
  const term = (n - 11 / 8) / Math.E;
  const w = Math.log(term) - Math.log(Math.log(term));
  return 2 * Math.PI * (n - 11 / 8) / w;
}

function spectralGaps(nZeros: number = 28): number[] {
  const zeros = Array.from({ length: nZeros + 1 }, (_, i) => zetaZeroApprox(i + 1));
  return zeros.slice(0, nZeros).map((z, i) => zeros[i + 1] - z);
}

// ─── Quaternion Algebra ───────────────────────────────────────────────────────

interface Quaternion { a: number; b: number; c: number; d: number; }

function qadd(p: Quaternion, q: Quaternion): Quaternion {
  return { a: p.a + q.a, b: p.b + q.b, c: p.c + q.c, d: p.d + q.d };
}

function qmul(p: Quaternion, q: Quaternion): Quaternion {
  return {
    a: p.a * q.a - p.b * q.b - p.c * q.c - p.d * q.d,
    b: p.a * q.b + p.b * q.a + p.c * q.d - p.d * q.c,
    c: p.a * q.c - p.b * q.d + p.c * q.a + p.d * q.b,
    d: p.a * q.d + p.b * q.c - p.c * q.b + p.d * q.a,
  };
}

function qnorm(q: Quaternion): number {
  return Math.sqrt(q.a ** 2 + q.b ** 2 + q.c ** 2 + q.d ** 2);
}

function fromAxisAngle(axis: [number, number, number], angle: number): Quaternion {
  const norm = Math.sqrt(axis[0] ** 2 + axis[1] ** 2 + axis[2] ** 2);
  if (norm < 1e-10) return { a: 1, b: 0, c: 0, d: 0 };
  const [x, y, z] = axis.map(v => v / norm);
  const h = angle / 2;
  const s = Math.sin(h);
  return { a: Math.cos(h), b: x * s, c: y * s, d: z * s };
}

// ─── R₉₀ Rotation (90° about z-axis) ────────────────────────────────────────

function rotatePos(pos: [number, number, number]): [number, number, number] {
  return [-pos[1], pos[0], pos[2]];
}

// ─── Prime Resonator ─────────────────────────────────────────────────────────

interface PrimeResonator {
  prime: number;
  spectralGap: number;
  pos: [number, number, number];
  frequency: number;
  state: Quaternion;
  energy: number;
}

function makePrimeResonator(prime: number, gap: number, pos: [number, number, number]): PrimeResonator {
  const frequency = Math.log(prime) * gap;
  const axis: [number, number, number] = [1 / Math.sqrt(3), 1 / Math.sqrt(3), 1 / Math.sqrt(3)];
  const state = fromAxisAngle(axis, frequency);
  const energy = Math.sqrt(Math.log(prime) ** 2 + (Math.PI / 2) ** 2) * gap;
  return { prime, spectralGap: gap, pos, frequency, state, energy };
}

function evolveResonator(r: PrimeResonator, dt: number, coupling: Quaternion): PrimeResonator {
  const cn = qnorm(coupling);
  if (cn > 0) {
    const axis: [number, number, number] = [coupling.b / cn, coupling.c / cn, coupling.d / cn];
    const evolution = fromAxisAngle(axis, cn * dt);
    return {
      ...r,
      state: qmul(evolution, r.state),
      frequency: r.frequency + 0.01 * (cn - 1) * dt,
    };
  }
  return r;
}

// ─── Golden-Ratio Spiral Positions ───────────────────────────────────────────

function goldenPositions(n: number): [number, number, number][] {
  const phi = (1 + Math.sqrt(5)) / 2;
  return Array.from({ length: n }, (_, i) => {
    const scale = 10.0 / (i + 1);
    return [
      phi * i * Math.cos(2 * Math.PI * phi * i) * scale,
      phi * i * Math.sin(2 * Math.PI * phi * i) * scale,
      phi * i * Math.sin(2 * Math.PI * phi ** 2 * i) * scale,
    ] as [number, number, number];
  });
}

// ─── Resonator Lattice ────────────────────────────────────────────────────────

interface ResonatorLattice {
  primes: number[];
  specGaps: number[];
  resonators: PrimeResonator[];
  resonatorsRot: PrimeResonator[];
  coupling: Map<string, Quaternion>;
  couplingRot: Map<string, Quaternion>;
  freqGaps: number[];
  freqGapsRot: number[];
  corr: number;
  corrRot: number;
}

function buildCoupling(positions: [number, number, number][], primes: number[]): Map<string, Quaternion> {
  const coup = new Map<string, Quaternion>();
  const n = positions.length;
  for (let i = 0; i < n; i++) {
    for (let j = i + 1; j < n; j++) {
      const [xi, yi, zi] = positions[i];
      const [xj, yj, zj] = positions[j];
      const dx = xj - xi, dy = yj - yi, dz = zj - zi;
      const dist = Math.sqrt(dx ** 2 + dy ** 2 + dz ** 2);
      if (dist < 1e-10) continue;
      const strength = Math.log(primes[j]) / Math.log(primes[i]) / dist;
      coup.set(`${i},${j}`, { a: 0, b: strength * dx / dist, c: strength * dy / dist, d: strength * dz / dist });
    }
  }
  return coup;
}

function calcFreqGaps(resonators: PrimeResonator[]): number[] {
  const freqs = resonators.map(r => r.frequency).sort((a, b) => a - b);
  return freqs.slice(0, -1).map((f, i) => freqs[i + 1] - f);
}

function normalize(arr: number[]): number[] {
  if (arr.length < 2) return arr;
  const m = arr.reduce((a, b) => a + b, 0) / arr.length;
  const s = Math.sqrt(arr.reduce((a, b) => a + (b - m) ** 2, 0) / arr.length) || 1;
  return arr.map(x => (x - m) / s);
}

function pearson(x: number[], y: number[]): number {
  const n = Math.min(x.length, y.length);
  if (n < 2) return 0;
  let sx = 0, sy = 0, sxy = 0, sx2 = 0, sy2 = 0;
  for (let i = 0; i < n; i++) {
    sx += x[i]; sy += y[i]; sxy += x[i] * y[i];
    sx2 += x[i] ** 2; sy2 += y[i] ** 2;
  }
  const den = Math.sqrt((n * sx2 - sx ** 2) * (n * sy2 - sy ** 2));
  return den !== 0 ? (n * sxy - sx * sy) / den : 0;
}

function correlate(latticeGaps: number[], specGaps: number[]): number {
  const m = Math.min(latticeGaps.length, specGaps.length);
  if (m < 2) return 0;
  return pearson(normalize(latticeGaps.slice(0, m)), normalize(specGaps.slice(0, m)));
}

function buildResonatorLattice(primes: number[], specGaps: number[]): ResonatorLattice {
  const n = Math.min(primes.length, specGaps.length);
  const positions = goldenPositions(n);
  const rotPositions = positions.map(p => rotatePos(p)) as [number, number, number][];

  const resonators = primes.slice(0, n).map((p, i) =>
    makePrimeResonator(p, specGaps[i % specGaps.length], positions[i])
  );
  const resonatorsRot = primes.slice(0, n).map((p, i) =>
    makePrimeResonator(p, specGaps[i % specGaps.length], rotPositions[i])
  );

  const coupling = buildCoupling(positions, primes);
  const couplingRot = buildCoupling(rotPositions, primes);

  const freqGaps = calcFreqGaps(resonators);
  const freqGapsRot = calcFreqGaps(resonatorsRot);

  return {
    primes,
    specGaps,
    resonators,
    resonatorsRot,
    coupling,
    couplingRot,
    freqGaps,
    freqGapsRot,
    corr: correlate(freqGaps, specGaps),
    corrRot: correlate(freqGapsRot, specGaps),
  };
}

function evolveLattice(lattice: ResonatorLattice, dt = 0.01, steps = 30): number[] {
  let resonators = [...lattice.resonators];
  const corrs: number[] = [];
  for (let step = 0; step < steps; step++) {
    resonators = resonators.map((r, i) => {
      let total: Quaternion = { a: 0, b: 0, c: 0, d: 0 };
      for (let j = 0; j < resonators.length; j++) {
        if (i === j) continue;
        const key = `${Math.min(i, j)},${Math.max(i, j)}`;
        const c = lattice.coupling.get(key);
        if (c) total = qadd(total, c);
      }
      return evolveResonator(r, dt, total);
    });
    const gaps = calcFreqGaps(resonators);
    corrs.push(correlate(gaps, lattice.specGaps));
  }
  return corrs;
}

// ─── Valknut v9 Components ────────────────────────────────────────────────────

function sha256Hex(data: string): string {
  return createHash("sha256").update(data).digest("hex");
}

function zetaLike(data: string): number {
  const h = sha256Hex(data);
  return parseInt(h.slice(0, 8), 16) / 2 ** 32;
}

function thueMorsePhase(data: string): number {
  const bytes = Buffer.from(data, "utf8").slice(0, 257);
  let cum = 0;
  for (const b of bytes) {
    cum = (cum + (b.toString(2).split("1").length - 1)) % 2;
  }
  return ((cum * 2 * Math.PI) % (2 * Math.PI)) / (2 * Math.PI);
}

function geomCurvAtFib(data: string, fib: number): number {
  const h = sha256Hex(data + String(fib));
  return parseInt(h.slice(0, 4), 16) / 65535;
}

/**
 * Dyson Sphere Equilibrium Factor
 * Computes dimensionless Dyson equilibrium from block data using
 * the exact relativistic thin shell pressure formula.
 * Returns [0, 2] centered at 1 for perfect equilibrium.
 */
function dysonFactor(data: string): number {
  const h = sha256Hex(data);
  const M_sun = (parseInt(h.slice(0, 4), 16) / 65535) * 10;
  const R_sun = (parseInt(h.slice(4, 8), 16) / 65535) * 20;
  const rho_gcm3 = (parseInt(h.slice(8, 12), 16) / 65535) * 100;

  const M_kg = M_sun * 1.989e30;
  const R_m = R_sun * 6.957e8;
  const rho_kgm3 = rho_gcm3 * 1000.0;

  const G = 6.6743e-11;
  const rho_c = 1000.0;

  const denom = 2.0 * (R_m - 2.0 * G * M_kg) * (1.0 + rho_kgm3 / rho_c);
  if (denom <= 0 || Math.abs(denom) < 1e-30) return 2.0;

  const P_t = (G * M_kg * rho_kgm3 * R_m) / denom;
  const P_ref = 1e10;
  const dyson = Math.tanh(P_t / P_ref) * 2.0;
  return Math.max(0, Math.min(2, dyson));
}

/**
 * Compute Valknut v9 xi score for block data.
 * xi = (spectral_cube + berry_flow + quantum_fibonacci + dyson_equilibrium) / 4
 * Valid mining candidate: |xi - 1| < 0.016
 */
function xiValknutV9(data: string): number {
  const hbar = 1.0545718e-34;
  const gamma = 1.0, m = 1.0, v_eff = 1.0;

  const specCube = zetaLike(data) ** 3;
  const berry = thueMorsePhase(data);
  const fibs = [1, 2, 3, 5, 8, 13, 21];
  const geomSum = fibs.reduce((s, f) => s + geomCurvAtFib(data, f), 0);
  const qFib = Math.max(0, Math.min(2, (hbar / (gamma * m * v_eff)) * geomSum));
  const dyson = dysonFactor(data);
  return (specCube + berry + qFib + dyson) / 4.0;
}

// ─── Quantum Spectral Correlator ──────────────────────────────────────────────

export interface DysonMinerState {
  primes: number[];
  specGaps: number[];
  latticeCorr: number;
  latticeCorrRot: number;
  quantumGaps: number[];
  chainCorrelation: number;
  finalCorrOrig: number;
  finalCorrRot: number;
  eigenvalues: number[];
  valknutPassRate: number;
  hashRateBoost: number;
  dysonEquilibrium: number;
  xiTolerance: number;
  epoch: number;
  lastUpdate: number;
}

export interface DysonMineResult {
  nonce: number | null;
  blockHash: string | null;
  xi: number;
  dysonFactor: number;
  berryPhase: number;
  specCube: number;
  quantumFib: number;
  valknutPass: boolean;
  attempts: number;
  hashRateBoost: number;
  chainCorrelation: number;
}

export interface ValknutCandidate {
  index: number;
  offset: number;
  xi: number;
  gap: number;
  passesFilter: boolean;
  hashRateBoost: number;
  dysonEquilibrium: number;
  berryPhase: number;
}

class QuantumGravityMinerV9 {
  private nModes: number;
  private primes: number[];
  private specGaps: number[];
  private lattice: ResonatorLattice;
  private quantumGaps: number[];
  private eigenvalues: number[];
  private finalCorrOrig: number = 0;
  private finalCorrRot: number = 0;
  private epoch: number = 0;
  private xiTolerance: number = 0.016;
  private lastUpdate: number = 0;

  constructor(nModes: number = 28) {
    this.nModes = nModes;
    this.primes = generatePrimes(nModes);
    this.specGaps = spectralGaps(nModes);
    this.lattice = buildResonatorLattice(this.primes, this.specGaps);
    this.eigenvalues = this._approxEigenvalues();
    this.quantumGaps = this._calcQuantumGaps();
    this.lastUpdate = Date.now();
  }

  private _approxEigenvalues(): number[] {
    const ev: number[] = [];
    for (let i = 0; i < this.nModes; i++) {
      const r = this.lattice.resonators[i];
      let coupSum = 0;
      for (let j = 0; j < this.nModes; j++) {
        if (i === j) continue;
        const key = `${Math.min(i, j)},${Math.max(i, j)}`;
        const c = this.lattice.coupling.get(key);
        if (c) coupSum += qnorm(c);
      }
      ev.push(r.energy + 0.5 * coupSum);
    }
    return ev.sort((a, b) => a - b);
  }

  private _calcQuantumGaps(): number[] {
    return this.eigenvalues.slice(0, -1).map((v, i) => this.eigenvalues[i + 1] - v);
  }

  /** Evolve the lattice once per epoch — updates correlations */
  evolve(dt = 0.01, steps = 20): void {
    const origCorrs = evolveLattice(this.lattice, dt, steps);
    this.finalCorrOrig = origCorrs[origCorrs.length - 1] || 0;
    // Rotate lattice evolution
    const rotLattice = {
      ...this.lattice,
      resonators: this.lattice.resonatorsRot,
      coupling: this.lattice.couplingRot,
    };
    const rotCorrs = evolveLattice(rotLattice, dt, steps);
    this.finalCorrRot = rotCorrs[rotCorrs.length - 1] || 0;
    this.epoch++;
    this.lastUpdate = Date.now();
  }

  /** Compute chain correlation product (quality signal) */
  get chainCorrelation(): number {
    const m = Math.min(this.quantumGaps.length, this.specGaps.length);
    const qn = normalize(this.quantumGaps.slice(0, m));
    const zn = normalize(this.specGaps.slice(0, m));
    const qZeta = pearson(qn, zn);
    return qZeta * this.lattice.corr * this.finalCorrOrig;
  }

  /** Hash rate boost multiplier from Dyson equilibrium (1.0 = baseline) */
  get hashRateBoost(): number {
    const cc = Math.abs(this.chainCorrelation);
    return 1.0 + cc * 4.5; // up to 5.5x boost at perfect correlation
  }

  /** Generate Valknut candidates from quantum gaps */
  generateValknutCandidates(seed: string, n: number = 30): ValknutCandidate[] {
    const candidates: ValknutCandidate[] = [];
    for (let i = 0; i < Math.min(n, this.quantumGaps.length); i++) {
      const gap = this.quantumGaps[i];
      const offset = Math.round(Math.abs(gap) * 1e6) % 1_000_000 - 500_000;
      const data = `${seed}:${i}:${offset}:${this.epoch}`;
      const xi = xiValknutV9(data);
      const df = dysonFactor(data);
      const berry = thueMorsePhase(data);
      candidates.push({
        index: i + 1,
        offset,
        xi,
        gap,
        passesFilter: Math.abs(xi - 1.0) <= this.xiTolerance,
        hashRateBoost: this.hashRateBoost,
        dysonEquilibrium: df,
        berryPhase: berry,
      });
    }
    return candidates.sort((a, b) => Math.abs(a.xi - 1) - Math.abs(b.xi - 1));
  }

  /** Mine with Valknut v9 filter — finds nonce where xi is near equilibrium */
  mine(blockData: string, maxAttempts: number = 50_000): DysonMineResult {
    let bestXi = 0;
    let bestNonce: number | null = null;
    let bestHash: string | null = null;

    for (let nonce = 0; nonce < maxAttempts; nonce++) {
      const data = `${blockData}:${nonce}:${this.epoch}`;
      const xi = xiValknutV9(data);
      const passes = Math.abs(xi - 1.0) <= this.xiTolerance;

      if (passes) {
        const df = dysonFactor(data);
        const berry = thueMorsePhase(data);
        const spec = zetaLike(data) ** 3;
        const blockHash = createHash("sha256").update(data).digest("hex");

        return {
          nonce,
          blockHash,
          xi,
          dysonFactor: df,
          berryPhase: berry,
          specCube: spec,
          quantumFib: xi - (spec + berry + df) / 4 + xi / 4,
          valknutPass: true,
          attempts: nonce + 1,
          hashRateBoost: this.hashRateBoost,
          chainCorrelation: this.chainCorrelation,
        };
      }

      if (Math.abs(xi - 1.0) < Math.abs(bestXi - 1.0) || bestNonce === null) {
        bestXi = xi;
        bestNonce = nonce;
        bestHash = createHash("sha256").update(data).digest("hex");
      }
    }

    const data = `${blockData}:${bestNonce}:${this.epoch}`;
    return {
      nonce: null,
      blockHash: null,
      xi: bestXi,
      dysonFactor: dysonFactor(data),
      berryPhase: thueMorsePhase(data),
      specCube: zetaLike(data) ** 3,
      quantumFib: 0,
      valknutPass: false,
      attempts: maxAttempts,
      hashRateBoost: this.hashRateBoost,
      chainCorrelation: this.chainCorrelation,
    };
  }

  getState(): DysonMinerState {
    const candidates = this.generateValknutCandidates("skynt-state", 30);
    const passCount = candidates.filter(c => c.passesFilter).length;
    const avgDyson = candidates.reduce((s, c) => s + c.dysonEquilibrium, 0) / candidates.length;

    return {
      primes: this.primes.slice(0, 10),
      specGaps: this.specGaps.slice(0, 10),
      latticeCorr: this.lattice.corr,
      latticeCorrRot: this.lattice.corrRot,
      quantumGaps: this.quantumGaps.slice(0, 10),
      chainCorrelation: this.chainCorrelation,
      finalCorrOrig: this.finalCorrOrig,
      finalCorrRot: this.finalCorrRot,
      eigenvalues: this.eigenvalues.slice(0, 10),
      valknutPassRate: passCount / candidates.length,
      hashRateBoost: this.hashRateBoost,
      dysonEquilibrium: avgDyson,
      xiTolerance: this.xiTolerance,
      epoch: this.epoch,
      lastUpdate: this.lastUpdate,
    };
  }
}

// ─── Singleton + Background Evolution ────────────────────────────────────────

export const dysonMiner = new QuantumGravityMinerV9(28);

// Evolve the lattice every 60 seconds to update correlations
let _evolutionHandle: ReturnType<typeof setInterval> | null = null;

export function startDysonEvolution(): void {
  if (_evolutionHandle) return;
  dysonMiner.evolve(0.01, 20);
  _evolutionHandle = setInterval(() => {
    try {
      dysonMiner.evolve(0.01, 20);
      const ds = dysonMiner.getState();
      console.log(`[DysonSphere] Epoch ${ds.epoch} — chainCorr=${ds.chainCorrelation.toFixed(4)} boost=${ds.hashRateBoost.toFixed(2)}x`);
      wsHub.broadcast("dyson:evolution", {
        epoch: ds.epoch,
        chainCorrelation: ds.chainCorrelation,
        hashRateBoost: ds.hashRateBoost,
        dysonEquilibrium: ds.dysonEquilibrium,
        valknutPassRate: ds.valknutPassRate,
        xiTolerance: ds.xiTolerance,
        lastUpdate: ds.lastUpdate,
      });
    } catch (e: any) {
      console.error("[DysonSphere] Evolution error:", e.message);
    }
  }, 60_000);
}

export function stopDysonEvolution(): void {
  if (_evolutionHandle) {
    clearInterval(_evolutionHandle);
    _evolutionHandle = null;
  }
}

export function isDysonEvolutionRunning(): boolean {
  return _evolutionHandle !== null;
}

export { xiValknutV9, dysonFactor, spectralGaps, generatePrimes, pearson };
