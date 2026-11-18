// Excalibur JSON-RPC Client
// Communicates with AetherionEXCAL.exe via JSON-RPC on localhost:9332

export interface JsonRpcRequest {
  jsonrpc: string;
  id: number | string;
  method: string;
  params?: any[] | Record<string, any>;
}

export interface JsonRpcResponse {
  jsonrpc: string;
  id: number | string;
  result?: any;
  error?: {
    code: number;
    message: string;
    data?: any;
  };
}

export interface BlockInfo {
  hash: string;
  height: number;
  timestamp: number;
  previousblockhash: string;
  merkleroot: string;
  tx: string[];
  confirmations: number;
  size: number;
  weight: number;
}

export interface MempoolInfo {
  loaded: number;
  size: number;
  maxmempool: number;
  mempoolminfee: number;
  minrelaytxfee: number;
}

export interface PeerInfo {
  id: number;
  addr: string;
  addrbind: string;
  version: number;
  subver: string;
  pingtime: number;
  lastsend: number;
  lastrecv: number;
  bytessent: number;
  bytesrecv: number;
  connection_time: number;
}

export interface BalanceInfo {
  address: string;
  balance: number;
  confirmed: number;
  unconfirmed: number;
}

export interface ExcaliburRpcConfig {
  url: string;
  timeout?: number;
  retries?: number;
}

export class ExcaliburRpcClient {
  private config: ExcaliburRpcConfig;
  private requestId: number;

  constructor(config?: Partial<ExcaliburRpcConfig>) {
    this.config = {
      url: config?.url || process.env.EXCALIBUR_RPC_URL || 'http://127.0.0.1:9332',
      timeout: config?.timeout || 30000,
      retries: config?.retries || 3,
    };
    this.requestId = 0;
  }

  private async sendRequest(method: string, params?: any[] | Record<string, any>): Promise<any> {
    const request: JsonRpcRequest = {
      jsonrpc: '2.0',
      id: ++this.requestId,
      method,
      params,
    };

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), this.config.timeout);

    try {
      const response = await fetch(this.config.url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(request),
        signal: controller.signal,
      });

      clearTimeout(timeoutId);

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = (await response.json()) as JsonRpcResponse;

      if (data.error) {
        throw new Error(`RPC error: ${data.error.message} (code: ${data.error.code})`);
      }

      return data.result;
    } catch (error) {
      if (error instanceof Error) {
        if (error.name === 'AbortError') {
          throw new Error(`Request timeout after ${this.config.timeout}ms`);
        }
        throw error;
      }
      throw new Error('Failed to connect to Excalibur node');
    }
  }

  // Chain methods
  async getBlockCount(): Promise<number> {
    return this.sendRequest('getblockcount');
  }

  async getBlockHash(height: number): Promise<string> {
    return this.sendRequest('getblockhash', [height]);
  }

  async getBlock(blockHash: string, verbosity: number = 1): Promise<BlockInfo | string> {
    return this.sendRequest('getblock', [blockHash, verbosity]);
  }

  // Wallet methods
  async getBalance(address?: string, minconf: number = 0): Promise<number> {
    const params = address ? [address, minconf] : [minconf];
    return this.sendRequest('getbalance', params);
  }

  // Mempool methods
  async getMempoolInfo(): Promise<MempoolInfo> {
    return this.sendRequest('getmempoolinfo');
  }

  async getMempoolTxids(): Promise<string[]> {
    return this.sendRequest('getrawmempool');
  }

  // Network methods
  async getPeerInfo(): Promise<PeerInfo[]> {
    return this.sendRequest('getpeerinfo');
  }

  async getNetworkInfo(): Promise<any> {
    return this.sendRequest('getnetworkinfo');
  }

  // Mining methods
  async generate(blocks: number): Promise<string[]> {
    return this.sendRequest('generate', [blocks]);
  }

  async getMiningInfo(): Promise<any> {
    return this.sendRequest('getmininginfo');
  }

  // Transaction methods
  async sendRawTransaction(hex: string): Promise<string> {
    return this.sendRequest('sendrawtransaction', [hex]);
  }

  async getRawTransaction(txid: string, verbosity: number = 0): Promise<string | any> {
    return this.sendRequest('getrawtransaction', [txid, verbosity]);
  }

  // Raw RPC method for custom requests
  async raw(method: string, params?: any[] | Record<string, any>): Promise<any> {
    return this.sendRequest(method, params);
  }

  // Health check
  async ping(): Promise<boolean> {
    try {
      await this.getBlockCount();
      return true;
    } catch {
      return false;
    }
  }

  // Get node status summary
  async getStatus(): Promise<{
    connected: boolean;
    blockCount?: number;
    peers?: number;
    mempoolSize?: number;
  }> {
    const status: { connected: boolean; blockCount?: number; peers?: number; mempoolSize?: number } = { connected: false };

    try {
      const [blockCount, peerInfo, mempoolInfo]: [
        PromiseSettledResult<number>,
        PromiseSettledResult<PeerInfo[]>,
        PromiseSettledResult<MempoolInfo>
      ] = await Promise.allSettled([
        this.getBlockCount(),
        this.getPeerInfo(),
        this.getMempoolInfo(),
      ]);

      status.connected = true;
      status.blockCount = blockCount.status === 'fulfilled' ? blockCount.value : undefined;
      status.peers = peerInfo.status === 'fulfilled' ? peerInfo.value.length : undefined;
      status.mempoolSize = mempoolInfo.status === 'fulfilled' ? mempoolInfo.value.size : undefined;
    } catch {
      status.connected = false;
    }

    return status;
  }
}

// Browser-side proxy client that uses /api/excalibur-rpc endpoint
export class ExcaliburRpcBrowserClient extends ExcaliburRpcClient {
  constructor() {
    // Browser client uses the proxy endpoint
    super({ url: '/api/excalibur-rpc' });
  }
}

// Default export for convenience
export default ExcaliburRpcClient;
