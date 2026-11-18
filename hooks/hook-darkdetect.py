# PyInstaller hook for darkdetect
# darkdetect uses ctypes.util.find_library which is not supported by PyInstaller.
# On Windows, darkdetect directly loads shcore.dll, so no extra binaries are needed.

from PyInstaller.utils.hooks import collect_submodules

# Ensure all darkdetect submodules are collected
hiddenimports = collect_submodules('darkdetect')

