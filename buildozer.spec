[app]

# Title and identifier
title = AetherionEXCAL
package.name = aetherionexcal
package.domain = org.aetherion
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,txt,json,jsonl,md

# Versioning
version = 3.0.0
url = https://www.aetherion-oracle.com
author = Aetherion Oracle

# Android configuration
android.minapi = 24
android.maxapi = 34
android.sdk = 34
android.ndk = 25b
android.ndk_path =
android.archs = arm64-v8a,armeabi-v7a
android.orientation = portrait
android.fullscreen = 0
android.immersive_mode = 1
android.wakelock = 1
android.allow_backup = True
android.private_storage = True
android.windowSoftInputMode = adjustResize
android.activity_launch_mode = standard
android.sdk_check = True
android.copy_libs = 1
android.export = False
android.debuglog = False
android.next_storage = True
android.hardware_back = True
android.hardware_orient = 1
android.implicit_intents = True
android.filesystem_access_mode = implicitIntent
android.preferred_dependency_format = apk
android.chunk_install = False

# Icon and presplash
android.icon = kivy_wallet/android_icon.png
android.presplash_name =

# Permissions
android.permissions = internet,access_network_state,access_wifi_state

# Bootstrap
p4a.bootstrap = sdl2
android.build_mode = debug

# Service (disabled for wallet app)
android.service = False
android.service_core = False
android.service_enabled = False
android.service_foreground = False

# Theme
android.theme = default
android.compileplatform = 34
android.entrypoint = org.kivy.android.PythonActivity

# Empty optional fields
android.logcat_filters =
android.intent_filters =
android.add_activities =
android.meta_data =
android.select =
android.service_entrypoint =
android.service_args =
android.service_permissions =
android.service_install_mode =
android.service_priority =

[buildozer]

# Path to build output
logdir = .buildozer/android/log

# Logger verbosity
log_level = 2

# Application requirements
requirements = python3,kivy

# Source traceback
source.showtraceback = 2
