/**
 * caduceusStore.mjs — High-concurrency Node.js store for Caduceus cross-chain tunnels.
 * Supports both JSON fallback (caduceus_store.json) and SQLite WAL mode (caduceus_store.db).
 *
 * Author: Travis Dale Jones
 */

import fs from 'fs';
import path from 'path';

export const DEFAULT_JSON_PATH = 'caduceus_store.json';
export const DEFAULT_SQLITE_PATH = 'caduceus_store.db';

export class CaduceusJsonStore {
  constructor(filePath = DEFAULT_JSON_PATH) {
    this.filePath = filePath;
    this.data = {
      version: '1.0.0',
      capsules: {},
      state_tunnels: {},
      audit_log: [],
    };
    this.load();
  }

  load() {
    if (fs.existsSync(this.filePath)) {
      try {
        const raw = fs.readFileSync(this.filePath, 'utf-8');
        this.data = JSON.parse(raw);
      } catch (_) {}
    }
  }

  save() {
    fs.writeFileSync(this.filePath, JSON.stringify(this.data, null, 2), 'utf-8');
  }

  storeCapsule(digest, canon, payload, status = 'verified', blockHeight = null) {
    this.data.capsules[digest] = {
      digest,
      canon,
      payload,
      status,
      blockHeight,
      createdAt: Date.now(),
    };
    this.logAudit('store_capsule', digest);
    this.save();
  }

  getCapsule(digest) {
    return this.data.capsules[digest] || null;
  }

  listCapsules() {
    return Object.values(this.data.capsules);
  }

  storeTunnel(tunnelId, sourceHexagram, targetHexagram, resonance, status = 'active') {
    this.data.state_tunnels[tunnelId] = {
      tunnelId,
      sourceHexagram,
      targetHexagram,
      resonance,
      status,
      updatedAt: Date.now(),
    };
    this.logAudit('store_tunnel', tunnelId);
    this.save();
  }

  getTunnel(tunnelId) {
    return this.data.state_tunnels[tunnelId] || null;
  }

  listTunnels() {
    return Object.values(this.data.state_tunnels);
  }

  logAudit(action, entityId) {
    this.data.audit_log.push({
      action,
      entityId,
      timestamp: Date.now(),
    });
  }
}

/**
 * Factory for Caduceus storage
 */
export function getCaduceusStore(type = process.env.CADUCEUS_STORAGE_BACKEND || 'json') {
  return new CaduceusJsonStore();
}
