#!/usr/bin/env bash
# One-shot wrapper (MSYS2 bash): provision the toolchain, then build+install
# the three libav DLLs into the WindAgent repo. Kept as a single invocation so
# one approval covers the whole pipeline.
#   C:\\msys64\\usr\\bin\\bash.exe -lc '<repo>/scripts/live_record/msys2_setup_and_build.sh <repo>'
set -e

REPO="${1:?usage: msys2_setup_and_build.sh <windagent_repo>}"

echo "== [t] MSYS2 core sync =="
# First run may replace the msys runtime and ask to restart; tolerate both.
pacman -Syu --noconfirm || true
pacman -Su --noconfirm || true

echo "== [t] install toolchain =="
pacman -S --needed --noconfirm mingw-w64-x86_64-gcc make diffutils nasm

export PATH="/mingw64/bin:$PATH"
gcc --version | head -1

echo "== [b] FFmpeg DLL build =="
exec "$REPO/scripts/live_record/build_libav_from_source.sh" "$REPO"
