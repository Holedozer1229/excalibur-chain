// AetherionEXCAL SkyNet P2P — .NET Implementation
// 
// Cross-platform P2P node using .NET 8 that works alongside the Python beacon.
// Compatible with Python beacon, Node.js P2P, and the wallet.
//
// Build:
//   dotnet build -c Release
//   dotnet publish -c Release -r win-x64 --self-contained
//   dotnet publish -c Release -r osx-x64 --self-contained
//
// Run:
//   dotnet run -- --port 9433 --beacon http://localhost:9435

using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Net;
using System.Net.Http;
using System.Net.Sockets;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Threading;
using System.Threading.Tasks;

namespace SkyNetP2P
{
    public class Peer
    {
        [JsonPropertyName("node_id")]
        public string NodeId { get; set; } = string.Empty;
        
        [JsonPropertyName("host")]
        public string Host { get; set; } = string.Empty;
        
        [JsonPropertyName("port")]
        public int Port { get; set; } = 9433;
        
        [JsonPropertyName("services")]
        public int Services { get; set; } = 0;
        
        [JsonPropertyName("last_seen")]
        public double LastSeen { get; set; } = 0;
    }

    public class SkyNetNode
    {
        private readonly int _port;
        private readonly string _beaconUrl;
        private readonly string _nodeId;
        private readonly string _host;
        private readonly ConcurrentDictionary<string, Peer> _peers = new();
        private HttpListener? _httpListener;
        private UdpClient? _multicastSocket;
        private UdpClient? _broadcastSocket;
        private CancellationTokenSource? _cts;
        private bool _running;

        private const string MulticastGroup = "239.1.1.1";
        private const int MulticastPort = 9436;
        private const int BroadcastPort = 9437;
        private const string BroadcastAddress = "255.255.255.255";
        private const int PeerTtl = 600;
        private const int HeartbeatIntervalMs = 60000;

        public SkyNetNode(int port = 9433, string? beaconUrl = null)
        {
            _port = port;
            _beaconUrl = beaconUrl ?? $"http://localhost:9435";
            _nodeId = Guid.NewGuid().ToString();
            _host = GetLocalIP();
        }

        public async Task StartAsync()
        {
            _running = true;
            _cts = new CancellationTokenSource();

            Console.WriteLine(new string('=', 50));
            Console.WriteLine("  AetherionEXCAL SkyNet P2P (.NET)");
            Console.WriteLine(new string('=', 50));
            Console.WriteLine($"  Node ID:  {_nodeId}");
            Console.WriteLine($"  Host:     {_host}");
            Console.WriteLine($"  Port:     {_port}");
            Console.WriteLine($"  Beacon:   {_beaconUrl}");
            Console.WriteLine(new string('=', 50));

            // Start HTTP server
            _ = Task.Run(() => RunHttpServerAsync(_cts.Token));

            // Start multicast listener
            _ = Task.Run(() => RunMulticastAsync(_cts.Token));

            // Start broadcast listener
            _ = Task.Run(() => RunBroadcastAsync(_cts.Token));

            // Register with beacon
            await RegisterWithBeaconAsync(_cts.Token);

            // Start heartbeat
            _ = Task.Run(() => HeartbeatLoopAsync(_cts.Token));

            Console.WriteLine($"\nSkyNet P2P node started on port {_port}");
            Console.WriteLine($"Discover peers: {_beaconUrl}/peers\n");
        }

        public async Task StopAsync()
        {
            _running = false;
            _cts?.Cancel();
            _httpListener?.Stop();
            _multicastSocket?.Close();
            _broadcastSocket?.Close();
            Console.WriteLine("SkyNet P2P node stopped");
        }

        private async Task RunHttpServerAsync(CancellationToken ct)
        {
            _httpListener = new HttpListener();
            _httpListener.Prefixes.Add($"http://*:{_port}/");
            _httpListener.Start();

            while (!ct.IsCancellationRequested)
            {
                try
                {
                    var context = await _httpListener.GetContextAsync();
                    _ = Task.Run(() => HandleRequestAsync(context, ct));
                }
                catch (ObjectDisposedException)
                {
                    break;
                }
                catch when (ct.IsCancellationRequested)
                {
                    break;
                }
            }
        }

        private async Task HandleRequestAsync(HttpListenerContext context, CancellationToken ct)
        {
            var url = context.Request.Url;
            context.Response.ContentType = "application/json";

            if (context.Request.HttpMethod == "GET" && url != null)
            {
                if (url.AbsolutePath == "/peers")
                {
                    var limit = 8;
                    if (int.TryParse(url.Query.Substring(1).Split('=')[1], out var l))
                        limit = l;
                    var peers = GetPeers(limit);
                    var json = JsonSerializer.Serialize(new { peers, count = peers.Length });
                    context.Response.StatusCode = 200;
                    await WriteResponseAsync(context.Response, json);
                }
                else if (url.AbsolutePath == "/health")
                {
                    var json = JsonSerializer.Serialize(new
                    {
                        status = "ok",
                        node_id = _nodeId,
                        host = _host,
                        port = _port,
                    });
                    context.Response.StatusCode = 200;
                    await WriteResponseAsync(context.Response, json);
                }
                else if (url.AbsolutePath == "/stats")
                {
                    var stats = GetStats();
                    context.Response.StatusCode = 200;
                    await WriteResponseAsync(context.Response, stats);
                }
                else
                {
                    context.Response.StatusCode = 404;
                    await WriteResponseAsync(context.Response, "{\"error\":\"not found\"}");
                }
            }
            else if (context.Request.HttpMethod == "POST" && url != null)
            {
                using var reader = new StreamReader(context.Request.InputStream);
                var body = await reader.ReadToEndAsync();

                if (url.AbsolutePath == "/register")
                {
                    try
                    {
                        var data = JsonSerializer.Deserialize<Dictionary<string, object>>(body);
                        if (data != null)
                        {
                            var nodeId = data.GetValueOrDefault("node_id")?.ToString() ?? "";
                            var host = data.GetValueOrDefault("host")?.ToString() ?? "";
                            var port = 9433;
                            if (data.TryGetValue("port", out var p) && double.TryParse(p.ToString(), out var pi))
                                port = (int)pi;

                            AddPeer(nodeId, host, port);
                        }
                        context.Response.StatusCode = 200;
                        await WriteResponseAsync(context.Response, "{\"status\":\"ok\"}");
                    }
                    catch
                    {
                        context.Response.StatusCode = 400;
                        await WriteResponseAsync(context.Response, "{\"error\":\"invalid json\"}");
                    }
                }
                else
                {
                    context.Response.StatusCode = 404;
                    await WriteResponseAsync(context.Response, "{\"error\":\"not found\"}");
                }
            }

            context.Response.Close();
        }

        private async Task WriteResponseAsync(HttpListenerResponse response, string json)
        {
            var bytes = Encoding.UTF8.GetBytes(json);
            response.ContentLength64 = bytes.Length;
            await response.OutputStream.WriteAsync(bytes, 0, bytes.Length);
        }

        private async Task RunMulticastAsync(CancellationToken ct)
        {
            try
            {
                _multicastSocket = new UdpClient();
                _multicastSocket.JoinMulticastGroup(IPAddress.Parse(MulticastGroup), 32);
                _multicastSocket.Client.SetSocketOption(SocketOptionLevel.Socket, SocketOptionName.ReuseAddress, true);
                _multicastSocket.Client.Bind(new IPEndPoint(IPAddress.Any, MulticastPort));

                while (!ct.IsCancellationRequested)
                {
                    var result = await _multicastSocket.ReceiveAsync();
                    HandleUdpMessage(result.Buffer, result.RemoteEndPoint);
                }
            }
            catch (ObjectDisposedException) { }
            catch (SocketException) when (ct.IsCancellationRequested) { }
            catch (Exception ex)
            {
                Console.WriteLine($"Multicast error: {ex.Message}");
            }
        }

        private async Task RunBroadcastAsync(CancellationToken ct)
        {
            try
            {
                _broadcastSocket = new UdpClient();
                _broadcastSocket.Client.SetSocketOption(SocketOptionLevel.Socket, SocketOptionName.ReuseAddress, true);
                _broadcastSocket.Client.Bind(new IPEndPoint(IPAddress.Any, BroadcastPort));

                while (!ct.IsCancellationRequested)
                {
                    var result = await _broadcastSocket.ReceiveAsync();
                    HandleUdpMessage(result.Buffer, result.RemoteEndPoint);
                }
            }
            catch (ObjectDisposedException) { }
            catch (SocketException) when (ct.IsCancellationRequested) { }
            catch (Exception ex)
            {
                Console.WriteLine($"Broadcast error: {ex.Message}");
            }
        }

        private void HandleUdpMessage(byte[] data, IPEndPoint remoteEndPoint)
        {
            try
            {
                var json = Encoding.UTF8.GetString(data);
                var msg = JsonSerializer.Deserialize<Dictionary<string, object>>(json);
                if (msg == null) return;

                var type = msg.GetValueOrDefault("type")?.ToString() ?? "";

                if (type == "register")
                {
                    var nodeId = msg.GetValueOrDefault("node_id")?.ToString() ?? "";
                    var host = msg.GetValueOrDefault("host")?.ToString() ?? remoteEndPoint.Address.ToString();
                    var port = 9433;
                    if (msg.TryGetValue("port", out var p) && double.TryParse(p.ToString(), out var pi))
                        port = (int)pi;

                    AddPeer(nodeId, host, port);

                    // Respond with known peers
                    var peers = GetPeers(8);
                    var response = JsonSerializer.Serialize(new { type = "peers", peers });
                    SendUdp(response, remoteEndPoint.Address, port);
                }
                else if (type == "heartbeat")
                {
                    var nodeId = msg.GetValueOrDefault("node_id")?.ToString() ?? "";
                    if (_peers.TryGetValue(nodeId, out var peer))
                        peer.LastSeen = DateTimeOffset.UtcNow.ToUnixTimeSeconds();
                }
            }
            catch { /* Ignore invalid messages */ }
        }

        private void SendUdp(string message, IPAddress address, int port)
        {
            try
            {
                using var sock = new UdpClient();
                var data = Encoding.UTF8.GetBytes(message);
                sock.Send(data, data.Length, address, port);
            }
            catch { }
        }

        private void AddPeer(string nodeId, string host, int port)
        {
            if (string.IsNullOrEmpty(nodeId) || nodeId == _nodeId) return;

            _peers[nodeId] = new Peer
            {
                NodeId = nodeId,
                Host = host,
                Port = port,
                LastSeen = DateTimeOffset.UtcNow.ToUnixTimeSeconds(),
            };
        }

        private Peer[] GetPeers(int limit = 8)
        {
            var now = DateTimeOffset.UtcNow.ToUnixTimeSeconds();
            var list = new List<Peer>();

            foreach (var peer in _peers.Values)
            {
                if (now - peer.LastSeen < PeerTtl)
                    list.Add(new Peer
                    {
                        NodeId = peer.NodeId,
                        Host = peer.Host,
                        Port = peer.Port,
                        Services = peer.Services,
                    });
            }

            list.Sort((a, b) => b.LastSeen.CompareTo(a.LastSeen));
            return list.Take(limit).ToArray();
        }

        private string GetStats()
        {
            var now = DateTimeOffset.UtcNow.ToUnixTimeSeconds();
            var active = _peers.Values.Count(p => now - p.LastSeen < PeerTtl);

            return JsonSerializer.Serialize(new
            {
                node_id = _nodeId,
                host = _host,
                port = _port,
                peers_registered = _peers.Count,
                peers_active = active,
                running = _running,
            });
        }

        private async Task RegisterWithBeaconAsync(CancellationToken ct)
        {
            try
            {
                using var client = new HttpClient();
                var data = JsonSerializer.Serialize(new
                {
                    node_id = _nodeId,
                    host = _host,
                    port = _port,
                    services = 1,
                    user_agent = "/SkyNet-DotNet:1.0/",
                });

                var content = new StringContent(data, Encoding.UTF8, "application/json");
                var response = await client.PostAsync($"{_beaconUrl}/register", content, ct);
                if (response.IsSuccessStatusCode)
                {
                    Console.WriteLine($"Registered with beacon: {_beaconUrl}");
                }
            }
            catch (Exception ex)
            {
                Console.WriteLine($"Beacon registration failed: {ex.Message}");
            }
        }

        private async Task HeartbeatLoopAsync(CancellationToken ct)
        {
            while (!ct.IsCancellationRequested)
            {
                await Task.Delay(HeartbeatIntervalMs, ct);

                var msg = JsonSerializer.Serialize(new
                {
                    type = "heartbeat",
                    node_id = _nodeId,
                    host = _host,
                    port = _port,
                });

                // Multicast
                SendUdp(msg, IPAddress.Parse(MulticastGroup), MulticastPort);

                // Broadcast
                SendUdp(msg, IPAddress.Parse(BroadcastAddress), BroadcastPort);

                // Re-register with beacon
                await RegisterWithBeaconAsync(ct);
            }
        }

        private string GetLocalIP()
        {
            using var socket = new Socket(AddressFamily.InterNetwork, SocketType.Dgram, ProtocolType.Udp);
            socket.Connect("8.8.8.8", 80);
            var ep = socket.LocalEndPoint as IPEndPoint;
            socket.Close();
            return ep?.Address.ToString() ?? "127.0.0.1";
        }
    }

    class Program
    {
        static async Task Main(string[] args)
        {
            var port = 9433;
            string? beaconUrl = null;

            for (int i = 0; i < args.Length; i++)
            {
                if (args[i] == "--port" && i + 1 < args.Length)
                    int.TryParse(args[++i], out port);
                else if (args[i] == "--beacon" && i + 1 < args.Length)
                    beaconUrl = args[++i];
            }

            var node = new SkyNetNode(port, beaconUrl);
            await node.StartAsync();

            Console.CancelKeyPress += (s, e) =>
            {
                Console.WriteLine("\nShutting down...");
                node.StopAsync().Wait();
                e.Cancel = true;
            };

            // Keep running
            await Task.Delay(Timeout.Infinite);
        }
    }
}
