import { WebSocketServer, WebSocket } from "ws";
import { IncomingMessage } from "http";

/**
 * WebSocket Hub for Dyson Sphere Miner broadcast.
 *
 * Provides a simple pub/sub broadcast mechanism for real-time
 * Dyson evolution updates to connected clients.
 */

export interface WsClient {
  ws: WebSocket;
  lastPing: number;
}

export class WsHub {
  private wss: WebSocketServer | null = null;
  private clients: Set<WsClient> = new Set();
  private port: number;

  constructor(port: number = 8080) {
    this.port = port;
  }

  /** Start the WebSocket server */
  start(): Promise<number> {
    return new Promise((resolve, reject) => {
      this.wss = new WebSocketServer({ port: this.port });

      this.wss.on("connection", (ws: WebSocket, req: IncomingMessage) => {
        const client: WsClient = { ws, lastPing: Date.now() };
        this.clients.add(client);

        const remoteAddr = req.socket.remoteAddress;
        console.log(`[WsHub] Client connected: ${remoteAddr} (${this.clients.size} total)`);

        ws.on("message", (data: Buffer) => {
          client.lastPing = Date.now();
          try {
            const msg = JSON.parse(data.toString());
            this.handleMessage(client, msg);
          } catch (e) {
            console.error("[WsHub] Invalid JSON message:", data.toString());
          }
        });

        ws.on("close", () => {
          this.clients.delete(client);
          console.log(`[WsHub] Client disconnected (${this.clients.size} remaining)`);
        });

        ws.on("error", (err) => {
          console.error("[WsHub] Client error:", err.message);
          this.clients.delete(client);
        });

        // Send welcome message
        this.sendTo(client, "system:welcome", {
          message: "Connected to Dyson Sphere Miner Hub",
          clients: this.clients.size,
        });
      });

      this.wss.on("listening", () => {
        console.log(`[WsHub] Listening on port ${this.port}`);
        resolve(this.port);
      });

      this.wss.on("error", (err) => {
        console.error("[WsHub] Server error:", err.message);
        reject(err);
      });
    });
  }

  /** Handle incoming messages from clients */
  private handleMessage(client: WsClient, msg: any) {
    const { type, payload } = msg;

    switch (type) {
      case "ping":
        this.sendTo(client, "pong", { time: Date.now() });
        break;
      case "subscribe":
        console.log(`[WsHub] Client subscribed to: ${payload?.channel || "all"}`);
        break;
      default:
        console.log(`[WsHub] Unknown message type: ${type}`);
    }
  }

  /** Send a message to a specific client */
  private sendTo(client: WsClient, type: string, data: any) {
    try {
      if (client.ws.readyState === WebSocket.OPEN) {
        client.ws.send(JSON.stringify({ type, data }));
      }
    } catch (e) {
      console.error("[WsHub] Send error:", (e as Error).message);
    }
  }

  /** Broadcast a message to all connected clients */
  broadcast(type: string, data: any) {
    const message = JSON.stringify({ type, data });
    let count = 0;
    for (const client of this.clients) {
      try {
        if (client.ws.readyState === WebSocket.OPEN) {
          client.ws.send(message);
          count++;
        }
      } catch (e) {
        console.error("[WsHub] Broadcast error:", (e as Error).message);
      }
    }
    if (count > 0) {
      console.log(`[WsHub] Broadcast "${type}" to ${count} clients`);
    }
  }

  /** Get current client count */
  getClientCount(): number {
    return this.clients.size;
  }

  /** Stop the WebSocket server */
  stop(): Promise<void> {
    return new Promise((resolve) => {
      if (this.wss) {
        for (const client of this.clients) {
          try {
            client.ws.close(1000, "Server shutting down");
          } catch (e) {
            // ignore
          }
        }
        this.clients.clear();
        this.wss.close(() => {
          console.log("[WsHub] Server stopped");
          resolve();
        });
      } else {
        resolve();
      }
    });
  }
}

// Singleton instance
let _wsHub: WsHub | null = null;

export function getWsHub(port: number = 8080): WsHub {
  if (!_wsHub) {
    _wsHub = new WsHub(port);
  }
  return _wsHub;
}

export const wsHub = getWsHub();
