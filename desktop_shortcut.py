#!/usr/bin/env python3
"""
AetherionEXCAL — First-run desktop shortcut creator.

When AetherionEXCAL.exe runs for the first time, this module creates:
1. A desktop shortcut to the executable
2. A Start Menu shortcut
3. A registry entry for uninstall

This runs silently on first launch and creates a marker file so it
doesn't run again. For Inno Setup installations, this is a fallback —
the installer creates shortcuts during installation.

Usage:
    import desktop_shortcut
    desktop_shortcut.ensure_shortcuts()
"""

import os
import sys
import ctypes
import winreg
from pathlib import Path


def _get_exe_path() -> str:
    """Get the path to the running executable (works for frozen and dev)."""
    if getattr(sys, "frozen", False):
        return sys.executable
    return os.path.abspath(sys.argv[0])


def _get_shortcut_dir() -> str:
    """Get the desktop directory path."""
    try:
        # Use Windows shell to get the desktop path
        buf = ctypes.create_unicode_buffer(260)
        ctypes.windll.shell32.SHGetFolderPathW(0, 0x0000, None, 0, buf)
        return buf.value
    except Exception:
        return os.path.join(os.path.expanduser("~"), "Desktop")


def _get_start_menu_dir() -> str:
    """Get the Start Menu Programs directory path."""
    try:
        buf = ctypes.create_unicode_buffer(260)
        ctypes.windll.shell32.SHGetFolderPathW(0, 0x0006, None, 0, buf)
        return buf.value
    except Exception:
        return os.path.join(os.path.expanduser("~"), "AppData", "Roaming",
                           "Microsoft", "Windows", "Start Menu", "Programs")


def _create_shortcut(target: str, shortcut_path: str, description: str = "") -> bool:
    """
    Create a Windows .lnk shortcut using COM.
    
    Args:
        target: Path to the target executable
        shortcut_path: Full path for the .lnk file
        description: Description shown in tooltip
    
    Returns:
        True if shortcut was created successfully
    """
    try:
        import pythoncom
        from win32com.client import Dispatch
        
        pythoncom.CoInitialize()
        try:
            shell = Dispatch("WScript.Shell")
            shortcut = shell.CreateShortCut(shortcut_path)
            shortcut.TargetPath = target
            shortcut.WorkingDirectory = os.path.dirname(target)
            shortcut.Description = description or "AetherionEXCAL — Quantum Oracle P2P Wallet"
            shortcut.IconLocation = f"{target},0"
            shortcut.Save()
            return True
        finally:
            pythoncom.CoUninitialize()
    except ImportError:
        # pywin32 not available — try alternative method
        pass
    except Exception:
        pass
    return False


def _create_shortcut_vbs(target: str, shortcut_path: str, description: str = "") -> bool:
    """
    Create a Windows .lnk shortcut using a temporary VBScript.
    Fallback when pywin32 is not available.
    """
    import tempfile
    
    vbs_script = f'''
Set oWS = WScript.CreateObject("WScript.Shell")
sLinkFile = "{shortcut_path}"
Set oLink = oWS.CreateShortcut(sLinkFile)
oLink.TargetPath = "{target}"
oLink.WorkingDirectory = "{os.path.dirname(target)}"
oLink.Description = "{description}"
oLink.IconLocation = "{target},0"
oLink.Save
'''
    try:
        vbs_file = os.path.join(tempfile.gettempdir(), "_create_shortcut.vbs")
        with open(vbs_file, "w") as f:
            f.write(vbs_script)
        
        import subprocess
        result = subprocess.run(
            ["cscript.exe", "//nologo", vbs_file],
            capture_output=True, timeout=10
        )
        
        # Clean up
        try:
            os.unlink(vbs_file)
        except OSError:
            pass
        
        return result.returncode == 0 and os.path.exists(shortcut_path)
    except Exception:
        return False


def _get_first_run_marker() -> str:
    """Get the path to the first-run marker file."""
    data_dir = os.path.expanduser("~/.excal_wallet")
    os.makedirs(data_dir, exist_ok=True)
    return os.path.join(data_dir, ".desktop_shortcuts_created")


def has_created_shortcuts() -> bool:
    """Check if shortcuts have already been created."""
    return os.path.exists(_get_first_run_marker())


def ensure_shortcuts() -> bool:
    """
    Create desktop and Start Menu shortcuts on first run.
    
    Returns:
        True if shortcuts were created, False if already created or failed
    """
    # Only on Windows
    if sys.platform != "win32":
        return False
    
    # Skip if already created
    if has_created_shortcuts():
        return False
    
    exe_path = _get_exe_path()
    
    # For PyInstaller frozen apps, use the actual executable
    if getattr(sys, "frozen", False):
        target = exe_path
    else:
        # In dev mode, skip — user runs from source
        return False
    
    created = False
    
    # Create desktop shortcut
    desktop_dir = _get_shortcut_dir()
    desktop_shortcut = os.path.join(desktop_dir, "AetherionEXCAL.lnk")
    
    # Try pywin32 first, then VBScript fallback
    if _create_shortcut(target, desktop_shortcut, "AetherionEXCAL — Quantum Oracle P2P Wallet"):
        created = True
    elif _create_shortcut_vbs(target, desktop_shortcut, "AetherionEXCAL — Quantum Oracle P2P Wallet"):
        created = True
    
    # Create Start Menu shortcut
    start_menu_dir = _get_start_menu_dir()
    start_menu_shortcut = os.path.join(start_menu_dir, "AetherionEXCAL.lnk")
    
    if _create_shortcut(target, start_menu_shortcut, "AetherionEXCAL — Quantum Oracle P2P Wallet"):
        created = True
    elif _create_shortcut_vbs(target, start_menu_shortcut, "AetherionEXCAL — Quantum Oracle P2P Wallet"):
        created = True
    
    # Mark as done
    if created:
        marker = _get_first_run_marker()
        with open(marker, "w") as f:
            f.write("desktop_shortcuts_created")
    
    return created


def register_uninstall() -> bool:
    """
    Register the uninstaller in Windows Registry.
    Only works if we know the installer's uninstall path.
    """
    if sys.platform != "win32":
        return False
    
    try:
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\AetherionEXCAL"
        
        # Try to get install directory from registry (set by Inno Setup)
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, 
                               r"Software\AetherionEXCAL") as key:
                install_dir = winreg.QueryValueEx(key, "InstallDir")[0]
        except (FileNotFoundError, OSError):
            install_dir = os.path.dirname(_get_exe_path())
        
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, "AetherionEXCAL")
            winreg.SetValueEx(key, "DisplayVersion", 0, winreg.REG_SZ, "3.0.0")
            winreg.SetValueEx(key, "Publisher", 0, winreg.REG_SZ, "Aetherion Oracle")
            winreg.SetValueEx(key, "InstallLocation", 0, winreg.REG_SZ, install_dir)
            # Note: UninstallString requires the actual uninstaller from Inno Setup
            return True
    except Exception:
        return False


if __name__ == "__main__":
    if ensure_shortcuts():
        print("Desktop shortcuts created successfully.")
    else:
        print("Shortcuts already exist or creation skipped.")
