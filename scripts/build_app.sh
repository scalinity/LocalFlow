#!/bin/zsh
# Build a LocalFlow.app and install it to /Applications
# (or ~/Applications). The bundle embeds the localflow code, the .venv,
# and config.json, so the app never reads from ~/Documents (avoiding the
# macOS Documents-access permission) and keeps working if this project
# moves. Re-run this script after changing the code.
set -e
cd "$(dirname "$0")/.."
ROOT="$PWD"

# Qualification builds use the same bundle recipe without replacing the
# installed app. Refuse an existing output rather than deleting it.
OUTPUT=""
if (( $# )); then
    if [[ $# != 2 || "$1" != "--output" || "$2" != /*.app ]]; then
        echo "Usage: $0 [--output /absolute/path/LocalFlow.app]" >&2
        exit 2
    fi
    OUTPUT="$2"
    if [[ -e "$OUTPUT" || -L "$OUTPUT" ]]; then
        echo "Output already exists: $OUTPUT" >&2
        exit 2
    fi
fi

# A worktree shares the configured development environment with its repository.
VENV="${LOCALFLOW_BUILD_VENV:-$ROOT/.venv}"
if [[ ! -x "$VENV/bin/python" ]]; then
    COMMON=$(git rev-parse --path-format=absolute --git-common-dir)
    VENV="$(dirname "$COMMON")/.venv"
fi
if [[ ! -x "$VENV/bin/python" ]]; then
    echo "Missing Python environment; set LOCALFLOW_BUILD_VENV" >&2
    exit 2
fi
PY_BASE=$("$VENV/bin/python" -c 'import sys; print(sys.base_prefix)')
PY_INCLUDE=$("$VENV/bin/python" -c 'import sysconfig; print(sysconfig.get_path("include"))')
PY_VERSION=$("$VENV/bin/python" -c 'import sys; print("%s.%s" % sys.version_info[:2])')
if [[ ! -f "$PY_BASE/Python" || ! -f "$PY_INCLUDE/Python.h" ]]; then
    echo "Build requires a macOS framework Python with embedding headers" >&2
    exit 2
fi
BUILD="$(mktemp -d)"
trap 'rm -rf "$BUILD"' EXIT
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

# Embedded coordinator runtime, venv dependencies, and default config. Worker
# interpreter links and native dependency libraries retain the existing local
# Python/Homebrew requirements; this is not a portable distribution recipe.
ditto "$ROOT/localflow" "$APP/Contents/Resources/localflow"
find "$APP/Contents/Resources/localflow" -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true
cp "$ROOT/config.json" "$APP/Contents/Resources/config.json"
REVISION=$(git rev-parse HEAD)
DIRTY=false
if [[ -n "$(git status --porcelain)" ]]; then DIRTY=true; fi
"$VENV/bin/python" - "$APP/Contents/Resources" "$REVISION" "$DIRTY" <<'PROVENANCE'
from pathlib import Path
import hashlib
import json
import sys

resources = Path(sys.argv[1])

def manifest(folder):
    files = []
    for path in folder.rglob('*'):
        relative = path.relative_to(resources)
        if (not path.is_file() or '__pycache__' in relative.parts
                or path.name == 'BUILD.json'):
            continue
        files.append({'path': relative.as_posix(),
                      'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
    files.sort(key=lambda file: file['path'])
    # NUL separators make both path and digest boundaries unambiguous.
    digest = hashlib.sha256()
    for file in files:
        digest.update(file['path'].encode('utf-8') + b'\0')
        digest.update(file['sha256'].encode('ascii') + b'\0')
    return {'files': files, 'sha256': digest.hexdigest()}

web = resources / 'localflow/v2/ui/companion/web'
frontend_build = (web / 'BUILD.json').read_bytes()
source_hash = json.loads(frontend_build)['source_sha256']
if (not isinstance(source_hash, str) or len(source_hash) != 64
        or any(char not in '0123456789abcdef' for char in source_hash)):
    raise ValueError('Invalid frontend BUILD source hash')
record = {
    'source_revision': sys.argv[2],
    'dirty': sys.argv[3] == 'true',
    'production': manifest(resources / 'localflow'),
    'frontend': {
        'source_sha256': source_hash,
        'build_sha256': hashlib.sha256(frontend_build).hexdigest(),
        **manifest(web),
    },
}
(resources / 'BUILD.json').write_text(json.dumps(record, indent=2) + '\n')
PROVENANCE
echo "Copying venv into bundle (~600 MB)..."
ditto "$VENV" "$APP/Contents/Resources/venv"
# Embed the matching base interpreter too. A venv alone contains symlinks to
# Homebrew's Python and cannot establish the native app's runtime identity.
ditto "$PY_BASE/Python" "$APP/Contents/Resources/runtime/Python"
ditto "$PY_BASE/lib/python$PY_VERSION" "$APP/Contents/Resources/runtime/lib/python$PY_VERSION"
# Subprocesses (ASR workers) remain ordinary Python processes through the copied
# venv's existing interpreter links; only the UI coordinator embeds Python.

# The LaunchServices executable owns AppKit and embeds CPython in-process.
# No foreign exec or Python child owns NSApplication, so NSBundle.mainBundle,
# process name, app menu, and Dock registration all refer to LocalFlow.app.
# Worker subprocesses still use the venv interpreter via sys.executable.
cat > "$BUILD/launcher.m" <<'LAUNCHER'
#import <Foundation/Foundation.h>
#include <Python.h>
#include <dlfcn.h>
#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>

#define LOAD(name) __typeof__(&name) lf_##name = dlsym(runtime, #name); \
    if (!lf_##name) { fprintf(stderr, "Missing Python entry point: %s\n", #name); return 2; }
#define CHECK(call) do { PyStatus status = (call); \
    if (status._type != _PyStatus_TYPE_OK) { \
        fprintf(stderr, "Python initialization failed: %s\n", status.err_msg ?: "unknown"); \
        lf_PyConfig_Clear(&config); return 2; } } while (0)

int main(int argc, char **argv) {
  @autoreleasepool {
    NSBundle *bundle = NSBundle.mainBundle;
    NSString *resources = bundle.resourcePath;
    if (![bundle.bundleIdentifier isEqualToString:@"com.danny.localflow"]) return 2;
    BOOL probe = argc == 2 && strcmp(argv[1], "--localflow-runtime-check") == 0;
    if (!probe && argc != 1) return 2;
    if (!probe) {
        const char *data = getenv("LOCALFLOW_DATA_HOME");
        if (data && data[0] != '/') return 2;
        NSString *base = data ? [NSString stringWithUTF8String:data] : NSHomeDirectory();
        NSString *logs = [base stringByAppendingPathComponent:@"Library/Logs"];
        [NSFileManager.defaultManager createDirectoryAtPath:logs
            withIntermediateDirectories:YES attributes:nil error:nil];
        NSString *log = [logs stringByAppendingPathComponent:@"LocalFlow.log"];
        int fd = open(log.fileSystemRepresentation, O_WRONLY | O_CREAT | O_APPEND, 0600);
        if (fd >= 0) { dup2(fd, 1); dup2(fd, 2); close(fd); }
    }
    NSString *base = [resources stringByAppendingPathComponent:@"runtime"];
    void *runtime = dlopen([[base stringByAppendingPathComponent:@"Python"] fileSystemRepresentation],
                           RTLD_NOW | RTLD_GLOBAL);
    if (!runtime) { fprintf(stderr, "Python runtime unavailable: %s\n", dlerror()); return 2; }
    LOAD(PyConfig_InitPythonConfig); LOAD(PyConfig_SetBytesString);
    LOAD(PyConfig_SetBytesArgv); LOAD(PyConfig_SetString);
    LOAD(PyWideStringList_Append); LOAD(Py_InitializeFromConfig);
    LOAD(PyConfig_Clear); LOAD(Py_RunMain);
    PyConfig config;
    lf_PyConfig_InitPythonConfig(&config);
    config.parse_argv = 0;
    config.use_environment = 0;
    config.user_site_directory = 0;
    config.write_bytecode = 0;
    config.buffered_stdio = 0;
    config.module_search_paths_set = 1;
    CHECK(lf_PyConfig_SetBytesString(&config, &config.program_name,
                                   bundle.executablePath.fileSystemRepresentation));
    CHECK(lf_PyConfig_SetBytesString(&config, &config.home, base.fileSystemRepresentation));
    NSString *venv = [resources stringByAppendingPathComponent:@"venv"];
    NSString *python = [venv stringByAppendingPathComponent:@"bin/python"];
    CHECK(lf_PyConfig_SetBytesString(&config, &config.executable, python.fileSystemRepresentation));
    CHECK(lf_PyConfig_SetBytesString(&config, &config.prefix, venv.fileSystemRepresentation));
    CHECK(lf_PyConfig_SetBytesString(&config, &config.exec_prefix, venv.fileSystemRepresentation));
    CHECK(lf_PyConfig_SetBytesString(&config, &config.base_prefix, base.fileSystemRepresentation));
    CHECK(lf_PyConfig_SetBytesString(&config, &config.base_exec_prefix, base.fileSystemRepresentation));
    NSArray *paths = @[resources,
        [base stringByAppendingPathComponent:@"lib/pythonPY_VERSION"],
        [base stringByAppendingPathComponent:@"lib/pythonPY_VERSION/lib-dynload"],
        [venv stringByAppendingPathComponent:@"lib/pythonPY_VERSION/site-packages"]];
    for (NSString *path in paths) {
        wchar_t wide[4096];
        size_t length = mbstowcs(wide, path.fileSystemRepresentation, 4096);
        if (length == (size_t)-1 || length >= 4096) return 2;
        CHECK(lf_PyWideStringList_Append(&config.module_search_paths, wide));
    }
    char *args[] = {(char *)python.fileSystemRepresentation};
    CHECK(lf_PyConfig_SetBytesArgv(&config, 1, args));
    if (probe) {
        CHECK(lf_PyConfig_SetString(&config, &config.run_command,
          L"import json,sys,os,AppKit; from Foundation import NSBundle,NSProcessInfo; "
          L"b=NSBundle.mainBundle(); "
          L"print(json.dumps({'bundle_id':str(b.bundleIdentifier()),"
          L"'bundle_path':str(b.bundlePath()),'executable':str(b.executablePath()),"
          L"'name':str(b.objectForInfoDictionaryKey_('CFBundleDisplayName')),"
          L"'process_name':str(NSProcessInfo.processInfo().processName()),"
          L"'pid':os.getpid(),'python':sys.executable,'prefix':sys.prefix,"
          L"'base_prefix':sys.base_prefix,'icon':bool(b.pathForResource_ofType_('LocalFlow','icns')),"
          L"'icon_loadable':bool(AppKit.NSImage.alloc().initWithContentsOfFile_("
          L"b.pathForResource_ofType_('LocalFlow','icns')))}))"));
    } else {
        CHECK(lf_PyConfig_SetString(&config, &config.run_module, L"localflow"));
        if (chdir(resources.fileSystemRepresentation)) return 2;
    }
    CHECK(lf_Py_InitializeFromConfig(&config));
    lf_PyConfig_Clear(&config);
    return lf_Py_RunMain();
  }
}
LAUNCHER
# Replace only this compile-time version marker; no source paths enter the binary.
sed -i '' "s/PY_VERSION/$PY_VERSION/g" "$BUILD/launcher.m"
CACHE="$ROOT/build"
mkdir -p "$CACHE"
SRC_HASH=$(cat "$BUILD/launcher.m" "$PY_INCLUDE/patchlevel.h" | shasum -a 256 | cut -d' ' -f1)
if [[ ! -f "$CACHE/launcher" || "$(cat "$CACHE/launcher.src.sha256" 2>/dev/null)" != "$SRC_HASH" ]]; then
    echo "NOTE: launcher identity changed; macOS may require renewed Accessibility/Input Monitoring grants."
    clang -O2 -I"$PY_INCLUDE" -framework Foundation -o "$CACHE/launcher" "$BUILD/launcher.m"
    codesign --force -s - --identifier com.danny.localflow "$CACHE/launcher"
    echo "$SRC_HASH" > "$CACHE/launcher.src.sha256"
fi
cp "$CACHE/launcher" "$APP/Contents/MacOS/LocalFlow"

# Icon
PNG="$BUILD/icon_1024.png"
"$VENV/bin/python" "$ROOT/scripts/make_icon.py" "$PNG" > /dev/null
ICONSET="$BUILD/LocalFlow.iconset"
mkdir -p "$ICONSET"
typeset -A sizes
sizes=(icon_16x16 16 icon_16x16@2x 32 icon_32x32 32 icon_32x32@2x 64
       icon_128x128 128 icon_128x128@2x 256 icon_256x256 256
       icon_256x256@2x 512 icon_512x512 512 icon_512x512@2x 1024)
for name size in "${(@kv)sizes}"; do
    sips -z "$size" "$size" "$PNG" --out "$ICONSET/$name.png" > /dev/null
done
# ICNS accepts PNG representations directly. Assemble that documented container
# without iconutil's image-service dependency (unavailable in restricted builds).
"$VENV/bin/python" - "$ICONSET" "$APP/Contents/Resources/LocalFlow.icns" <<'ICNS'
from pathlib import Path
import struct
import sys
source = Path(sys.argv[1])
representations = (
    (b'icp4', 'icon_16x16'), (b'ic11', 'icon_16x16@2x'),
    (b'icp5', 'icon_32x32'), (b'ic12', 'icon_32x32@2x'),
    (b'ic07', 'icon_128x128'), (b'ic13', 'icon_128x128@2x'),
    (b'ic08', 'icon_256x256'), (b'ic14', 'icon_256x256@2x'),
    (b'ic09', 'icon_512x512'), (b'ic10', 'icon_512x512@2x'),
)
chunks = []
for kind, name in representations:
    data = (source / (name + '.png')).read_bytes()
    chunks.append(kind + struct.pack('>I', len(data) + 8) + data)
body = b''.join(chunks)
Path(sys.argv[2]).write_bytes(b'icns' + struct.pack('>I', len(body) + 8) + body)
ICNS

# Install
if [[ -n "$OUTPUT" ]]; then
    mkdir -p "$(dirname "$OUTPUT")"
    ditto "$APP" "$OUTPUT"
    rm -rf "$BUILD"
    echo "Built $OUTPUT (not installed)"
    exit 0
fi
DEST="/Applications/LocalFlow.app"
if [[ ! -w /Applications ]]; then
    DEST="$HOME/Applications/LocalFlow.app"
    mkdir -p "$HOME/Applications"
fi
rm -rf "$DEST"
ditto "$APP" "$DEST"
rm -rf "$BUILD"
echo "Installed $DEST"
