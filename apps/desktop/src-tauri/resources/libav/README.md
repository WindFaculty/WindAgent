# libav runtime DLLs (bundled next to the installed executables)

The recording-engine sidecar resolves avformat/avcodec/avutil with
`LoadLibraryW + GetProcAddress` at runtime (`muxer/libav_loader.rs`); nothing
is statically linked. This directory is declared in `tauri.conf.json`
(`bundle.resources`) so the installer places the DLLs beside `WindAgent.exe`,
which is inside the standard loader search path for the sidecar too.

Files here are BUILT FROM SOURCE, not taken from a third-party prebuilt
distribution (user decision 2026-08-25). Rebuild them with:

    C:\msys64\usr\bin\bash.exe -lc \
      '<repo>/scripts/live_record/build_libav_from_source.sh <repo> <work_dir>'

- `avutil-60.dll`
- `avcodec-62.dll`
- `avformat-62.dll`   (matroska muxer only — the engine's one MKV need)
- `libwinpthread-1.dll` (MinGW runtime dependency of avutil; MIT)

The build configures FFmpeg n8.1 with
`--enable-shared --disable-everything --enable-muxer=matroska
--enable-protocol=file` and everything else compiled out — no network,
no zlib/bz2/iconv, no swscale/swresample/avfilter/avdevice. The engine
strips ADTS and builds AAC ASC itself (`audio/aac.rs`), so no bitstream
filters or codec libraries are needed at mux time. Exact provenance
(tag, commit, flags, SHA-256 per file) lives in `VENDORED.txt`.

The 7.x (`-61/-61/-59`) and 6.x (`-60/-60/-58`) families remain accepted
fallbacks in the loader for older deployments.

Loader fallback order (first hit wins):
1. `WINDAGENT_LIBAV_DIR` environment variable (explicit deployments)
2. executable directory / standard loader search (this bundle)
3. bare names through PATH

Dev machines: run the build script above once — it installs into
`native/recording-engine/target/{release}/` as well as here.
