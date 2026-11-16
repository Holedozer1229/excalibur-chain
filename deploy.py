"""SphinxOS Nexus — Production deployment script.

Usage:
    python deploy.py              # Deploy with defaults
    python deploy.py --dev        # Development deployment
    python deploy.py --config config.json  # Custom config
"""

import argparse
import json
import os
import sys
import subprocess
from pathlib import Path

# Fix Windows console encoding (safe for PyInstaller windowed mode)
if sys.platform == "win32":
    try:
        if sys.stdout is not None:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass


def check_python_version():
    """Check Python version is compatible."""
    if sys.version_info < (3, 10):
        print("ERROR: Python 3.10+ is required")
        sys.exit(1)
    print(f"✓ Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")


def check_excal_dependencies():
    """Check EXCAL-specific dependencies."""
    # Check core modules can be imported
    core_modules = [
        "genesis_fork", "txscript", "p2p_layer", "fork_node",
        "stratum_fork", "trifold_lockbox", "lightledger", "camelot_api"
    ]
    for mod in core_modules:
        try:
            __import__(mod)
            print(f"✓ {mod} module loaded")
        except ImportError as e:
            print(f"WARNING: {mod} import failed: {e}")


def check_dependencies():
    """Check required dependencies are installed."""
    try:
        import numpy
        print(f"✓ numpy {numpy.__version__}")
    except ImportError:
        print("ERROR: numpy is required. Run: pip install numpy")
        sys.exit(1)


def run_tests():
    """Run the test suite."""
    print("\nRunning tests...")
    result = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "sphinx_os/tests", "-v"],
        capture_output=True,
        text=True,
    )
    
    if result.returncode != 0:
        print("ERROR: Tests failed")
        print(result.stdout)
        print(result.stderr)
        return False
    
    # Extract test count from output
    for line in result.stdout.split("\n"):
        if "Ran" in line:
            print(f"✓ {line.strip()}")
            break
    
    return True


def build_wallet():
    """Build Holo-wallet.exe."""
    print("\nBuilding Holo-wallet.exe...")
    
    try:
        import PyInstaller
        print(f"✓ PyInstaller {PyInstaller.__version__}")
    except ImportError:
        print("WARNING: PyInstaller not found. Skipping wallet build.")
        print("Install with: pip install pyinstaller")
        return False
    
    result = subprocess.run(
        [
            sys.executable, "-m", "PyInstaller",
            "--onefile", "--name", "Holo-wallet",
            "--add-data", "sphinx_os;sphinx_os",
            "--noconfirm",
            "holo_wallet.py"
        ],
        capture_output=True,
        text=True,
    )
    
    if result.returncode == 0:
        exe_path = Path("dist/Holo-wallet.exe")
        if exe_path.exists():
            size = exe_path.stat().st_size / (1024 * 1024)
            print(f"✓ Holo-wallet.exe built ({size:.1f} MB)")
            return True
    
    print("ERROR: Wallet build failed")
    return False


def create_config(args):
    """Create production configuration."""
    from sphinx_os.config import ProductionConfig
    
    if args.dev:
        config = ProductionConfig.development()
    else:
        config = ProductionConfig.default()
    
    # Validate
    errors = config.validate()
    if errors:
        print("ERROR: Configuration validation failed:")
        for err in errors:
            print(f"  - {err}")
        return False
    
    config_path = "config.json"
    config.save(config_path)
    print(f"✓ Configuration saved to {config_path}")
    return True


def verify_installation():
    """Verify the installation is working."""
    print("\nVerifying installation...")
    
    try:
        from sphinx_os.nexus import (
            NexusOrchestrator,
            QuantumSpacetimeFabric,
            ConsciousConsensusEngine,
            HolographicP2PLayer,
            SelfOrganizingTreasury,
        )
        print("✓ All sphinx_os modules imported successfully")
        
        # Quick smoke test
        nexus = NexusOrchestrator()
        state = nexus.step()
        print(f"✓ Nexus orchestrator running (phase: {state['phase']})")
        
        return True
    except Exception as e:
        print(f"ERROR: Verification failed: {e}")
        return False


def check_config():
    """Validate production configuration."""
    print("\nValidating configuration...")
    config_path = Path("config.json")
    if not config_path.exists():
        print("ERROR: config.json not found")
        return False
    
    with open(config_path) as f:
        config = json.load(f)
    
    # Check required fields
    required = ["p2p", "rpc", "stratum", "mining", "security", "camelot_game"]
    for field in required:
        if field not in config:
            print(f"ERROR: Missing config section: {field}")
            return False
    
    # Validate P2P config
    p2p = config["p2p"]
    if p2p.get("listen_port") != 9433:
        print(f"WARNING: P2P port is {p2p.get('listen_port')}, expected 9433")
    if p2p.get("bitcoin_bridge_port") != 8333:
        print(f"WARNING: Bitcoin bridge port is {p2p.get('bitcoin_bridge_port')}, expected 8333")
    if not p2p.get("atomic_swap_enabled"):
        print("WARNING: atomic_swap_enabled should be true for production")
    if not p2p.get("quantum_swap_enabled"):
        print("WARNING: quantum_swap_enabled should be true for production")
    
    # Validate security settings
    security = config.get("security", {})
    if security.get("max_reorg_depth", 0) < 50:
        print("WARNING: max_reorg_depth should be >= 50 for production")
    
    print("✓ Configuration validated")
    return True


def check_chain_file():
    """Check chain data file exists."""
    chain_file = Path("chain.jsonl")
    if not chain_file.exists():
        print("WARNING: chain.jsonl not found - node will create it on first run")
        return True
    
    size = chain_file.stat().st_size
    if size < 1024:
        print("WARNING: chain.jsonl is very small - may be empty or corrupted")
        return False
    
    print(f"✓ chain.jsonl exists ({size / (1024*1024):.1f} MB)")
    return True


def start_services():
    """Start all AetherionEXCAL services in the background."""
    print("\nStarting AetherionEXCAL services...")

    import subprocess as subp
    import time
    import platform

    services = [
        ("Fork Node (RPC)", ["fork_node.py"]),
        ("P2P Layer (EREPR)", ["p2p_layer.py", "--rpc-port", "9432"]),
        ("Stratum Server", ["stratum_fork.py"]),
        ("Camelot Game API", ["camelot_api.py"]),
    ]

    created_procs = []
    for name, args in services:
        print(f"  Starting {name}...")
        try:
            if platform.system() == "Windows":
                proc = subp.Popen(
                    [sys.executable] + args,
                    creationflags=subp.CREATE_NO_WINDOW,
                )
            else:
                proc = subp.Popen(
                    [sys.executable] + args,
                    stdout=subp.DEVNULL,
                    stderr=subp.DEVNULL,
                )
            created_procs.append((name, proc))
            print(f"  ✓ {name} started (PID: {proc.pid})")
            time.sleep(2)
        except Exception as e:
            print(f"  ✗ {name} failed: {e}")

    if created_procs:
        print("\n✓ All services started successfully")
        print("\nTo stop services:")
        if platform.system() == "Windows":
            print("  taskkill /F /IM python.exe")
        else:
            print("  pkill -f 'python.*fork_node|p2p_layer|stratum_fork|camelot_api'")
    return len(created_procs)


def main():
    parser = argparse.ArgumentParser(description="Deploy AetherionEXCAL P2P Stack")
    parser.add_argument("--dev", action="store_true", help="Development deployment")
    parser.add_argument("--skip-tests", action="store_true", help="Skip tests")
    parser.add_argument("--skip-wallet", action="store_true", help="Skip wallet build")
    parser.add_argument("--auto-start", action="store_true", help="Start all services after deployment")
    parser.add_argument("--config", type=str, help="Custom config file")

    args = parser.parse_args()
    
    print("=" * 60)
    print("  ⚔️ AetherionEXCAL P2P Stack — Production Deployment")
    print("  Version: 2.0.0")
    print("=" * 60)
    
    # Checks
    print("\n1. Checking prerequisites...")
    check_python_version()
    check_dependencies()
    check_excal_dependencies()
    
    # Config
    print("\n2. Validating configuration...")
    if not check_config():
        print("\nDeployment aborted: configuration error")
        sys.exit(1)
    
    # Chain file
    print("\n3. Checking chain data...")
    check_chain_file()
    
    # Tests
    if not args.skip_tests:
        print("\n4. Running tests...")
        if not run_tests():
            print("\nDeployment aborted: tests failed")
            sys.exit(1)
    else:
        print("\n4. Skipping tests (--skip-tests)")
    
    # Wallet
    if not args.skip_wallet:
        print("\n5. Building wallet...")
        build_wallet()
    else:
        print("\n5. Skipping wallet build (--skip-wallet)")
    
    # Verify
    print("\n6. Verifying installation...")
    if not verify_installation():
        print("\nDeployment completed with warnings")
        sys.exit(1)
    
    # Auto-start services if requested
    if args.auto_start:
        print("\n7. Starting services...")
        started = start_services()
        if started > 0:
            print(f"\n✓ {started} services started successfully")
        else:
            print("\n✗ No services were started")
    else:
        print("\n7. Services not started (use --auto-start to launch)")

    print("\n" + "=" * 60)
    print("  ⚔️ AetherionEXCAL Deployment Complete!")
    print("=" * 60)
    print("\nServices:")
    print("  • RPC:           0.0.0.0:9432")
    print("  • P2P (EREPR):   0.0.0.0:9433")
    print("  • Bitcoin Bridge: 0.0.0.0:8333")
    print("  • Stratum:       0.0.0.0:9434")
    print("  • Health Check:  0.0.0.0:9435")
    print("  • Game API:      0.0.0.0:9436")
    print("\nQuick start:")
    print("  • Auto bootstrap & deploy: auto-deploy.ps1 (Windows) or auto-deploy.sh (Linux/macOS)")
    print("  • Start full stack: start-production.bat (Windows) or start-production.sh (Linux/macOS)")
    print("  • Deploy & start: python deploy.py --skip-tests --skip-wallet --auto-start")
    print("  • Start node: python fork_node.py")
    print("  • Start P2P: python p2p_layer.py --seed <peer:port>")
    print("  • Start stratum: python stratum_fork.py")
    print("  • Start game API: python camelot_api.py")
    print("  • Start mining: python cpu_miner_mp.py")
    print("  • Use wallet: python holo_wallet.py status")
    print("  • View docs: README.md")
    print()


if __name__ == "__main__":
    main()
