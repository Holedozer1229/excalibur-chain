/**
 * Main entry point for Dyson Sphere Miner WebSocket server.
 *
 * Starts the WebSocket hub and begins background Dyson lattice evolution.
 *
 * Usage:
 *   npm run build    # Compile TypeScript
 *   npm start        # Run compiled server
 *   npm run dev      # Run with ts-node (development)
 */

import { wsHub } from "./ws-hub";
import { dysonMiner, startDysonEvolution, stopDysonEvolution } from "./dyson-miner";

async function main() {
  console.log("=== Dyson Sphere Miner v9 ===");
  console.log("Starting WebSocket server...");

  // Start WebSocket hub on port 8080
  const port = await wsHub.start();
  console.log(`WebSocket server running on ws://localhost:${port}`);

  // Show initial state
  const state = dysonMiner.getState();
  console.log(`\nInitial state:`);
  console.log(`  Chain correlation: ${state.chainCorrelation.toFixed(6)}`);
  console.log(`  Hash rate boost: ${state.hashRateBoost.toFixed(2)}x`);
  console.log(`  Dyson equilibrium: ${state.dysonEquilibrium.toFixed(4)}`);
  console.log(`  Valknut pass rate: ${(state.valknutPassRate * 100).toFixed(2)}%`);
  console.log();

  // Start background evolution
  startDysonEvolution();
  console.log("Background evolution started (60s interval)\n");

  // Graceful shutdown
  process.on("SIGINT", async () => {
    console.log("\nShutting down...");
    stopDysonEvolution();
    await wsHub.stop();
    process.exit(0);
  });

  process.on("SIGTERM", async () => {
    console.log("\nShutting down...");
    stopDysonEvolution();
    await wsHub.stop();
    process.exit(0);
  });
}

main().catch((err) => {
  console.error("Failed to start:", err);
  process.exit(1);
});
