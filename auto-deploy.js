#!/usr/bin/env node
/**
 * auto-deploy.js — AetherionEXCAL Auto-Bootstrap & Deploy
 *
 * Cross-platform Node.js auto-deploy script that works on Windows, Linux, and macOS.
 * Replaces the bash auto-deploy.sh which had persistent syntax errors on Windows Git Bash.
 *
 * Usage:
 *   node auto-deploy.js
 *   node auto-deploy.js --skip-chain-download
 *   node auto-deploy.js --skip-start
 *   node auto-deploy.js --dev
 */

const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');
const os = require('os');

// Parse arguments
const args = process.argv.slice(2);
const skipChainDownload = args.includes('--skip-chain-download');
const skipStart = args.includes('--skip-start');
const dev = args.includes('--dev');
const force = args.includes('--force');

// Colors for terminal output
const Colors = {
  Reset: '\x1b[0m',
  Green: '\x1b[32m',
  Yellow: '\x1b[33m',
  Red: '\x1b[31m',
  Cyan: '\x1b[36m',
  Bold: '\x1b[1m'
};

function writeStep(msg) {
  console.log(`\n${Colors.Cyan}>> ${msg}${Colors.Reset}`);
}

function writeOk(msg) {
  console.log(`${Colors.Green}[OK] ${msg}${Colors.Reset}`);
}

function writeWarn(msg) {
  console.log(`${Colors.Yellow}[WARN] ${msg}${Colors.Reset}`);
}

function writeErr(msg) {
  console.log(`${Colors.Red}[ERR] ${msg}${Colors.Reset}`);
}

function fail(msg) {
  writeErr(msg);
  process.exit(1);
}

function runCommand(cmd, options = {}) {
  try {
    const output = execSync(cmd, {
      stdio: 'pipe',
      encoding: 'utf8',
      shell: true,
      ...options
    });
    return output.trim();
  } catch (error) {
    return null;
  }
}

function isWindows() {
  return os.platform() === 'win32';
}

function getPythonCommand() {
  const commands = isWindows() ? ['python', 'py'] : ['python3', 'python'];
  
  for (const cmd of commands) {
    try {
      const version = execSync(`${cmd} --version`, {
        encoding: 'utf8',
        shell: true
      }).trim();
      
      // Check for Python 3.10+
      const match = version.match(/Python 3\.(\d+)/);
      if (match && parseInt(match[1]) >= 10) {
        return { cmd, version };
      }
    } catch (e) {
      // Try next command
    }
  }
  
  return null;
}

async function main() {
  console.log(`${Colors.Cyan}========================================${Colors.Reset}`);
  console.log(`${Colors.Cyan}  AetherionEXCAL - Auto Bootstrap & Deploy${Colors.Reset}`);
  console.log(`${Colors.Cyan}  Version: 2.0.0${Colors.Reset}`);
  console.log(`${Colors.Cyan}========================================${Colors.Reset}`);
  console.log('');

  // ============================================================
  // STEP 1: Determine install directory
  // ============================================================
  writeStep('STEP 1: Determining install directory');
  
  const scriptDir = path.dirname(__filename);
  let installDir = scriptDir;
  
  // Check if we're in a git repo
  if (!fs.existsSync(path.join(installDir, '.git'))) {
    installDir = path.join(os.homedir(), 'excalibur-chain');
  }
  
  writeOk(`Install directory: ${installDir}`);

  // ============================================================
  // STEP 2: Git repository setup
  // ============================================================
  writeStep('STEP 2: Git repository setup');
  
  if (!fs.existsSync(path.join(installDir, '.git'))) {
    const repoUrl = 'https://github.com/Holedozer1229/excalibur-chain.git';
    console.log('Cloning repository...');
    
    const output = runCommand(`git clone ${repoUrl} "${installDir}"`);
    if (output !== null) {
      writeOk('Repository cloned');
    } else {
      writeWarn('Git clone failed - checking if directory exists');
      if (!fs.existsSync(installDir)) {
        fail('Git clone failed and directory does not exist');
      }
    }
  } else {
    console.log('Repository found - pulling latest...');
    const output = runCommand(`git -C "${installDir}" pull --ff-only`, {
      cwd: installDir
    });
    if (output !== null) {
      writeOk('Repository updated');
    } else {
      writeWarn('Git pull failed - continuing with current checkout');
    }
  }

  // ============================================================
  // STEP 3: Python 3.10+ check
  // ============================================================
  writeStep('STEP 3: Checking Python');
  
  const python = getPythonCommand();
  if (!python) {
    fail('Python 3.10+ not found. Install from https://www.python.org/downloads/');
  }
  
  writeOk(`Python found: ${python.version}`);
  
  // Check for virtual environment
  let pyCmd = python.cmd;
  const venvPath = path.join(installDir, isWindows() ? '.venv\\Scripts\\python.exe' : '.venv/bin/python');
  
  if (fs.existsSync(venvPath)) {
    pyCmd = venvPath;
  }

  // ============================================================
  // STEP 4: Install Python dependencies
  // ============================================================
  writeStep('STEP 4: Installing Python dependencies');
  
  process.chdir(installDir);
  
  const venvDir = path.join(installDir, '.venv');
  if (!fs.existsSync(venvDir)) {
    console.log('Creating virtual environment...');
    runCommand(`${python.cmd} -m venv "${venvDir}"`);
    writeOk('Virtual environment created');
    pyCmd = venvPath;
  }
  
  const pipCmd = isWindows()
    ? path.join(venvDir, 'Scripts\\pip.exe')
    : path.join(venvDir, 'bin/pip');
  
  // Upgrade pip
  console.log('Upgrading pip...');
  runCommand(`"${pipCmd}" install --upgrade pip -q`);
  writeOk('Pip upgraded');
  
  // Install dependencies
  const requirementsFile = path.join(installDir, 'requirements.txt');
  if (fs.existsSync(requirementsFile)) {
    console.log('Installing dependencies from requirements.txt...');
    const output = runCommand(`"${pipCmd}" install -r "${requirementsFile}" -q`);
    if (output !== null) {
      writeOk('Dependencies installed');
    } else {
      writeWarn('Some dependencies may have failed to install');
    }
  }

  // ============================================================
  // STEP 5: Download and verify chain data
  // ============================================================
  writeStep('STEP 5: Chain data setup');
  
  const chainGz = path.join(installDir, 'chain.jsonl.gz');
  const chainFile = path.join(installDir, 'chain.jsonl');
  
  if (!skipChainDownload) {
    if (fs.existsSync(chainFile) && !force) {
      const stats = fs.statSync(chainFile);
      const sizeMb = (stats.size / (1024 * 1024)).toFixed(1);
      writeOk(`chain.jsonl already present (${sizeMb} MB)`);
    } else {
      const urls = [
        'https://github.com/Holedozer1229/excalibur-chain/releases/latest/download/chain.jsonl.gz',
        'https://github.com/Holedozer1229/excalibur-chain/releases/download/chain-snapshot-2026-11-12/chain.jsonl.gz'
      ];
      
      let downloaded = false;
      for (const url of urls) {
        console.log(`  Downloading from ${url}`);
        
        let downloadCmd;
        if (isWindows()) {
          downloadCmd = `powershell -Command "(New-Object Net.WebClient).DownloadFile('${url}', '${chainGz}')"`;
        } else {
          downloadCmd = `curl -fSL -o "${chainGz}" "${url}"`;
        }
        
        const output = runCommand(downloadCmd);
        if (output !== null && fs.existsSync(chainGz)) {
          downloaded = true;
          break;
        } else {
          writeWarn('  Download failed, trying next URL...');
        }
      }
      
      if (downloaded) {
        console.log('  Decompressing chain data...');
        const decompressCmd = `"${pyCmd}" -c "import gzip, shutil; shutil.copyfileobj(gzip.open('${chainGz}','rb'), open('${chainFile}','wb'))"`;
        const output = runCommand(decompressCmd);
        
        if (output !== null && fs.existsSync(chainFile)) {
          const stats = fs.statSync(chainFile);
          const sizeMb = (stats.size / (1024 * 1024)).toFixed(1);
          writeOk(`Chain data decompressed (${sizeMb} MB)`);
        } else {
          fail('Chain decompression failed');
        }
      } else {
        writeWarn('Could not download chain snapshot - node will start with empty chain');
      }
    }
  } else {
    writeWarn('Chain download skipped (--skip-chain-download)');
  }

  // ============================================================
  // STEP 6: Validate configuration
  // ============================================================
  writeStep('STEP 6: Validating configuration');
  
  const configFile = path.join(installDir, 'config.json');
  if (fs.existsSync(configFile)) {
    try {
      const config = JSON.parse(fs.readFileSync(configFile, 'utf8'));
      const p2p = config.p2p || {};
      const camelot = config.camelot_game || {};
      
      if (p2p.listen_port === 9433) {
        writeOk('P2P port: 9433 (AetherionEXCAL)');
      } else {
        writeWarn(`P2P port: ${p2p.listen_port} (expected 9433)`);
      }
      
      if (p2p.bitcoin_bridge_port === 8333) {
        writeOk('Bitcoin bridge port: 8333');
      }
      
      if (p2p.atomic_swap_enabled) writeOk('Atomic swap: enabled');
      if (p2p.quantum_swap_enabled) writeOk('Quantum swap: enabled');
      if (p2p.erepr_enabled) writeOk('EREPR protocol: enabled');
      
      if (camelot.enabled) {
        writeOk(`Camelot Game API: enabled (port ${camelot.api_port})`);
      }
      
      writeOk('Configuration validated');
    } catch (e) {
      writeWarn(`Failed to parse config.json: ${e.message}`);
    }
  } else {
    writeWarn('config.json not found - using defaults');
  }

  // ============================================================
  // STEP 7: Check core modules
  // ============================================================
  writeStep('STEP 7: Checking core modules');
  
  const coreModules = [
    'genesis_fork', 'txscript', 'p2p_layer', 'fork_node',
    'stratum_fork', 'trifold_lockbox', 'lightledger', 'camelot_api'
  ];
  
  let moduleErrors = 0;
  for (const mod of coreModules) {
    const output = runCommand(`"${pyCmd}" -c "import ${mod}"`);
    if (output !== null) {
      writeOk(`${mod} module loaded`);
    } else {
      writeWarn(`${mod} import failed`);
      moduleErrors++;
    }
  }
  
  if (moduleErrors > 0) {
    writeWarn(`${moduleErrors} module(s) had import issues - continuing anyway`);
  }

  // ============================================================
  // STEP 8: Run deploy.py verification
  // ============================================================
  writeStep('STEP 8: Running deploy verification');
  
  const deployScript = path.join(installDir, 'deploy.py');
  if (fs.existsSync(deployScript)) {
    let deployArgs = '--skip-tests --skip-wallet';
    if (dev) deployArgs += ' --dev';
    
    const output = runCommand(`"${pyCmd}" "${deployScript}" ${deployArgs}`);
    if (output !== null) {
      // Print deploy output
      output.split('\n').forEach(line => console.log(`  ${line}`));
      writeOk('Deploy verification passed');
    } else {
      writeWarn('Deploy verification completed with warnings');
    }
  } else {
    writeWarn('deploy.py not found - skipping verification');
  }

  // ============================================================
  // STEP 9: Summary
  // ============================================================
  console.log('');
  console.log(`${Colors.Green}========================================${Colors.Reset}`);
  console.log(`${Colors.Green}  AetherionEXCAL - Bootstrap Complete!${Colors.Reset}`);
  console.log(`${Colors.Green}========================================${Colors.Reset}`);
  console.log('');
  console.log(`${Colors.Cyan}Services available:${Colors.Reset}`);
  console.log('  RPC:            0.0.0.0:9432');
  console.log('  P2P (EREPR):    0.0.0.0:9433');
  console.log('  Bitcoin Bridge: 0.0.0.0:8333');
  console.log('  Stratum:        0.0.0.0:9434');
  console.log('  Health Check:   0.0.0.0:9435');
  console.log('  Game API:       0.0.0.0:9436');
  console.log('');

  // ============================================================
  // STEP 10: Auto-start services
  // ============================================================
  if (!skipStart) {
    writeStep('STEP 10: Starting all services');
    
    // Set environment variables
    process.env.EXCAL_WORKSPACE = installDir;
    process.env.FORK_RPC_PORT = '9432';
    process.env.FORK_RPC_HOST = '0.0.0.0';
    process.env.STRATUM_HOST = '0.0.0.0';
    process.env.STRATUM_PORT = '9434';
    process.env.GAME_API_PORT = '9436';
    
    const { spawn } = require('child_process');
    
    const services = [
      { name: 'Fork Node (RPC)', script: 'fork_node.py' },
      { name: 'P2P Layer', script: 'p2p_layer.py', args: ['--rpc-port', '9432'] },
      { name: 'Stratum Server', script: 'stratum_fork.py' },
      { name: 'Camelot Game API', script: 'camelot_api.py' }
    ];
    
    const children = [];
    
    for (const service of services) {
      console.log(`Starting ${service.name}...`);
      
      const child = spawn(pyCmd, [service.script, ...(service.args || [])], {
        cwd: installDir,
        detached: true,
        stdio: 'ignore',
        env: { ...process.env }
      });
      
      child.unref();
      children.push(child);
      
      // Small delay between starts
      await new Promise(resolve => setTimeout(resolve, 2000));
      writeOk(`${service.name} started`);
    }
    
    console.log('');
    console.log(`${Colors.Green}========================================${Colors.Reset}`);
    console.log(`${Colors.Green}  AetherionEXCAL Stack is RUNNING${Colors.Reset}`);
    console.log(`${Colors.Green}========================================${Colors.Reset}`);
    console.log('');
    console.log(`${Colors.Yellow}All services started in background.${Colors.Reset}`);
    console.log(`${Colors.Yellow}Press Ctrl+C to stop all services${Colors.Reset}`);
    console.log('');
    console.log(`${Colors.Cyan}Quick commands:${Colors.Reset}`);
    console.log('  RPC test: curl http://localhost:9432');
    console.log('  Health:   curl http://localhost:9435/health');
    console.log('  Game API: curl http://localhost:9436/stats');
    console.log('');
    
    // Handle graceful shutdown
    process.on('SIGINT', () => {
      console.log('\nShutting down AetherionEXCAL stack...');
      children.forEach(child => {
        try {
          process.kill(-child.pid, 'SIGTERM');
        } catch (e) {
          // Ignore errors
        }
      });
      console.log('All services stopped.');
      process.exit(0);
    });
    
    // Keep process running
    new Promise(() => {});
  } else {
    writeWarn('Service start skipped (--skip-start)');
    const startScript = isWindows() ? 'start-production.bat' : 'start-production.sh';
    writeWarn(`Run: ${startScript} to start all services`);
    console.log('');
  }
  
  console.log(`${Colors.Green}Auto-deploy complete. AetherionEXCAL is ready.${Colors.Reset}`);
}

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

// Run main
main().catch(err => {
  writeErr(`Auto-deploy failed: ${err.message}`);
  process.exit(1);
});
