#!/bin/zsh
# Build a self-contained LocalFlow.app and install it to /Applications
# (or ~/Applications). The bundle embeds the localflow code, the .venv,
# and config.json, so the app never reads from ~/Documents (avoiding the
# macOS Documents-access permission) and keeps working if this project
# moves. Re-run this script after changing the code.
set -e
cd "$(dirname "$0")/.."
ROOT="$PWD"

BUILD="$(mktemp -d)"
APP="$BUILD/LocalFlow.app"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"

cat > "$APP/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key><string>LocalFlow</string>
    <key>CFBundleDisplayName</key><string>LocalFlow</string>
    <key>CFBundleIdentifier</key><string>com.danny.localflow</string>
    <key>CFBundleExecutable</key><string>LocalFlow</string>
    <key>CFBundlePackageType</key><string>APPL</string>
    <key>CFBundleShortVersionString</key><string>0.1.0</string>
    <key>CFBundleVersion</key><string>1</string>
    <key>CFBundleIconFile</key><string>LocalFlow</string>
    <key>LSMinimumSystemVersion</key><string>12.0</string>
    <key>LSUIElement</key><true/>
    <key>NSMicrophoneUsageDescription</key>
    <string>LocalFlow records your voice while you hold the dictation key and transcribes it entirely on-device. Audio never leaves your Mac.</string>
    <key>NSHumanReadableCopyright</key><string>Local + private. Powered by Parakeet V3 on MLX.</string>
    <key>LSEnvironment</key>
    <dict>
        <key>PYTHONDONTWRITEBYTECODE</key><string>1</string>
    </dict>
</dict>
</plist>
PLIST

# Embedded runtime: code + venv + default config
ditto "$ROOT/localflow" "$APP/Contents/Resources/localflow"
find "$APP/Contents/Resources/localflow" -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true
cp "$ROOT/config.json" "$APP/Contents/Resources/config.json"
echo "Copying venv into bundle (~600 MB)..."
ditto "$ROOT/.venv" "$APP/Contents/Resources/venv"

# Launcher: a small Mach-O binary (LaunchServices rejects script
# executables). It FORKS Python as a child rather than exec'ing it:
# if the LS-registered app process execs a foreign binary, the macOS
# menu bar server rejects its status items (identity mismatch), so the
# child must register the menu bar icon under Python's own identity.
# Permission prompts still attribute to LocalFlow.app via macOS's
# responsible-process mechanism, like scripts run from Terminal.
cat > "$BUILD/launcher.c" <<'LAUNCHER'
#include <errno.h>
#include <fcntl.h>
#include <mach-o/dyld.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/wait.h>
#include <unistd.h>

static pid_t child = 0;

static void forward(int sig) {
    if (child > 0) kill(child, sig);
}

int main(void) {
    char exe[4096];
    uint32_t size = sizeof exe;
    if (_NSGetExecutablePath(exe, &size) != 0) return 1;
    char contents[4096];
    if (!realpath(exe, contents)) return 1;
    char *slash = strrchr(contents, '/');  /* strip /LocalFlow */
    if (slash) *slash = 0;
    slash = strrchr(contents, '/');        /* strip /MacOS */
    if (slash) *slash = 0;

    char res[4200], py[4300];
    snprintf(res, sizeof res, "%s/Resources", contents);
    snprintf(py, sizeof py, "%s/venv/bin/python", res);

    child = fork();
    if (child < 0) return 1;
    if (child == 0) {
        const char *home = getenv("HOME");
        char log[1024];
        snprintf(log, sizeof log, "%s/Library/Logs/LocalFlow.log",
                 home ? home : "/tmp");
        int fd = open(log, O_WRONLY | O_CREAT | O_APPEND, 0644);
        if (fd >= 0) { dup2(fd, 1); dup2(fd, 2); close(fd); }
        setenv("PYTHONPATH", res, 1);
        chdir(res);
        execl(py, py, "-u", "-m", "localflow", (char *)NULL);
        _exit(1);
    }

    signal(SIGTERM, forward);
    signal(SIGINT, forward);
    signal(SIGHUP, forward);
    int status = 0;
    while (waitpid(child, &status, 0) < 0 && errno == EINTR) {}
    return WIFEXITED(status) ? WEXITSTATUS(status) : 1;
}
LAUNCHER
# The launcher binary is cached and reused: macOS ties Accessibility /
# Input Monitoring grants to its code hash, and clang builds are NOT
# reproducible — recompiling would invalidate the user's grants on every
# rebuild. Only recompile when the C source actually changes.
CACHE="$ROOT/build"
mkdir -p "$CACHE"
SRC_HASH=$(shasum -a 256 "$BUILD/launcher.c" | cut -d' ' -f1)
if [[ ! -f "$CACHE/launcher" || "$(cat "$CACHE/launcher.src.sha256" 2>/dev/null)" != "$SRC_HASH" ]]; then
    echo "NOTE: recompiling launcher — existing Accessibility/Input Monitoring"
    echo "      grants will go stale; re-grant them in System Settings after this."
    clang -O2 -o "$CACHE/launcher" "$BUILD/launcher.c"
    codesign --force -s - --identifier com.danny.localflow "$CACHE/launcher"
    echo "$SRC_HASH" > "$CACHE/launcher.src.sha256"
fi
cp "$CACHE/launcher" "$APP/Contents/MacOS/LocalFlow"

# Icon
PNG="$BUILD/icon_1024.png"
"$ROOT/.venv/bin/python" "$ROOT/scripts/make_icon.py" "$PNG" > /dev/null
ICONSET="$BUILD/LocalFlow.iconset"
mkdir -p "$ICONSET"
typeset -A sizes
sizes=(icon_16x16 16 icon_16x16@2x 32 icon_32x32 32 icon_32x32@2x 64
       icon_128x128 128 icon_128x128@2x 256 icon_256x256 256
       icon_256x256@2x 512 icon_512x512 512 icon_512x512@2x 1024)
for name size in "${(@kv)sizes}"; do
    sips -z "$size" "$size" "$PNG" --out "$ICONSET/$name.png" > /dev/null
done
iconutil -c icns -o "$APP/Contents/Resources/LocalFlow.icns" "$ICONSET"

# Install
DEST="/Applications/LocalFlow.app"
if [[ ! -w /Applications ]]; then
    DEST="$HOME/Applications/LocalFlow.app"
    mkdir -p "$HOME/Applications"
fi
rm -rf "$DEST"
ditto "$APP" "$DEST"
rm -rf "$BUILD"
echo "Installed $DEST"
