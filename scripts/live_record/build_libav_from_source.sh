#!/usr/bin/env bash
# build_libav_from_source.sh - Phase 20: build the three libav DLLs from source.
#
# User decision (2026-08-25): vendor by building FFmpeg ourselves for full
# control over provenance and contents, instead of shipping a third-party
# prebuilt distribution.
#
# What the recording-engine actually needs from libav (muxer/libav_loader.rs
# require_sym list): avformat MKV muxing core only. It strips ADTS itself,
# builds AAC ASC itself, never calls avcodec_find_decoder/open, and never
# touches swscale/swresample. So this build is deliberately minimal:
#   avutil + avcodec + avformat shared, matroska muxer, file protocol.
# Everything else is compiled out - auditable, small, no external deps.
#
# Run from MSYS2 bash:  /path/to/build_libav_from_source.sh <windagent_repo>
# Produces: avutil-60.dll avcodec-62.dll avformat-62.dll in both
#   <repo>/apps/desktop/src-tauri/resources/libav/
#   <repo>/apps/desktop/native/recording-engine/target/release/
# plus VENDORED.txt with tag/commit/configure flags/SHA-256 provenance.
set -euo pipefail

REPO="${1:?usage: build_libav_from_source.sh <windagent_repo> [work_dir]}"
TAG="n8.1"
WORK="${2:-${FFMPEG_BUILD_DIR:-$HOME/ffmpeg-n8.1-build}}"
SRC="$WORK/src"
JOBS="$(nproc)"

echo "== [0/6] toolchain =="
command -v gcc >/dev/null || { echo "error: gcc not on PATH - run inside MSYS2 with mingw-w64-x86_64-gcc installed"; exit 2; }
gcc --version | head -1

mkdir -p "$WORK"

echo "== [1/6] source: git clone --branch $TAG --depth 1 (official GitHub mirror) =="
if [ ! -d "$SRC/.git" ]; then
    git clone --branch "$TAG" --depth 1 https://github.com/FFmpeg/FFmpeg.git "$SRC"
fi
# Commit provenance without requiring a git binary inside MSYS2: the clone's
# reflog records the checked-out SHA ("<old> <new> …" on its first line).
if command -v git >/dev/null 2>&1; then
    COMMIT="$(git -C "$SRC" rev-parse HEAD)"
else
    COMMIT="$(awk 'NR==1 {print $2}' "$SRC/.git/logs/HEAD" 2>/dev/null \
        || echo "unknown-$TAG")"
fi
echo "   commit $COMMIT"

echo "== [2/6] configure (minimal shared: avutil+avcodec+avformat, matroska, file) =="
CONFIGURE_FLAGS=(
    --enable-shared --disable-static
    --disable-programs --disable-doc --disable-debug
    --disable-network --disable-autodetect
    --disable-everything
    --enable-muxer=matroska
    --enable-protocol=file
    --disable-swscale --disable-swresample
    --disable-avfilter --disable-avdevice
    --disable-iconv --disable-zlib --disable-bzlib --disable-lzma
)
cd "$SRC"
FLAGS_SHA="$(printf '%s\n' "${CONFIGURE_FLAGS[@]}" | sha256sum | cut -d' ' -f1)"
if [ ! -f config.mak ] || [ "$(cat config.flags.sha 2>/dev/null)" != "$FLAGS_SHA" ]; then
    ./configure "${CONFIGURE_FLAGS[@]}"
    printf '%s' "$FLAGS_SHA" > config.flags.sha
    printf '%s' "$(printf '%s\n' "${CONFIGURE_FLAGS[@]}" | sha256sum | cut -d' ' -f1)" > config.flags.sha
else
    echo "   cached (same flags)"
fi

echo "== [3/6] build (-j$JOBS) =="
make -j"$JOBS"

echo "== [4/6] collect DLLs =="
DLLS=(avutil-60.dll avcodec-62.dll avformat-62.dll)
# MinGW-built avutil links libwinpthread-1.dll; it must ride along or
# LoadLibraryW(avutil) fails and the loader reports LIBAV_UNAVAILABLE.
PTHREAD_DLL="$(command -v libwinpthread-1.dll || echo /mingw64/bin/libwinpthread-1.dll)"
[ -f "$PTHREAD_DLL" ] || { echo "error: libwinpthread-1.dll not found in PATH"; exit 4; }
cp -f "$PTHREAD_DLL" "$WORK/libwinpthread-1.dll"
for dll in "${DLLS[@]}"; do
    found="$(find "$SRC" -name "$dll" | head -1)"
    [ -n "$found" ] || { echo "error: $dll not produced"; exit 3; }
    cp -f "$found" "$WORK/$dll"
    echo "   $(basename "$found") -> $WORK"
done

echo "== [5/6] install into repo =="
DEST_A="$REPO/apps/desktop/src-tauri/resources/libav"
DEST_B="$REPO/apps/desktop/native/recording-engine/target/release"
mkdir -p "$DEST_A" "$DEST_B"
for dll in "${DLLS[@]}" libwinpthread-1.dll; do
    cp -f "$WORK/$dll" "$DEST_A/$dll"
    cp -f "$WORK/$dll" "$DEST_B/$dll"
done

echo "== [6/6] provenance =="
{
    echo "source: FFmpeg git clone --branch $TAG --depth 1 https://github.com/FFmpeg/FFmpeg.git"
    echo "commit: $COMMIT"
    echo "built_by: scripts/live_record/build_libav_from_source.sh (MSYS2 mingw-w64 gcc)"
    echo "configure_flags: ${CONFIGURE_FLAGS[*]}"
    echo ""
    for dll in "${DLLS[@]}" libwinpthread-1.dll; do
        hash="$(sha256sum "$WORK/$dll" | cut -d' ' -f1)"
        size="$(stat -c%s "$WORK/$dll")"
        echo "$dll  sha256=$hash  bytes=$size"
    done
    echo ""
    echo "libwinpthread-1.dll provenance: MSYS2 package mingw-w64-x86_64-winpthreads (MIT license), copied from /mingw64/bin at build time"
} > "$DEST_A/VENDORED.txt"
cp -f "$DEST_A/VENDORED.txt" "$DEST_B/VENDORED.txt"
cat "$DEST_A/VENDORED.txt"
echo "DONE"
