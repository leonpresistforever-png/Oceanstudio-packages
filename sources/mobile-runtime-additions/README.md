# Additive native runtime proposal

Baseline: canonical package main 7750ea037b9162c7da4f237e40416e3439f1181d. No APT pool/index/signatures or existing package payloads are changed.

The indexed ffmpeg_8.1.2_aarch64.deb contains a glibc executable with interpreter /lib/ld-linux-aarch64.so.1 and dependencies on libavdevice.so.62, libavfilter.so.11, libavformat.so.62, libavcodec.so.62, libswresample.so.6, libswscale.so.9, libavutil.so.60, libm.so.6, libz.so.1, libc.so.6 and ld-linux-aarch64.so.1. Merely installing an Android library cannot repair this ABI mismatch. The seven matching libav/libsw package names are absent from the inspected signed index. The observed Xzs_Construct failure also requires device library search-path diagnostics.

This proposal stages **11 library packages** from pinned official upstream sources:

- libavcodec, libavformat, libavutil, libavfilter, libavdevice, libswresample, libswscale
- libmbedcrypto, libmbedx509, libmbedtls
- libwebsockets

It additionally stages ocean-ffmpeg-native (ocean-ffmpeg and ocean-ffprobe commands) and ocean-llama-runtime (llama-server-ocean), preserving existing ffmpeg/ffprobe/llama-server paths. Mbed TLS enables HTTPS in the separate native FFmpeg build. FFmpeg uses its version-3 license option with Mbed TLS 3 and ships both applicable LGPL notices. The proposed libwebsockets build has TLS disabled; do not label it WSS-capable.

Upstream tags and peeled commit IDs were checked, and FFmpeg, Mbed TLS and libwebsockets sources were downloaded for recipe inspection. The llama.cpp b10818 commit was checked. Native compilation is **UNVERIFIED**: Android NDK, CMake and on-device runtime testing are unavailable in this environment.

Build with:

```sh
python scripts/build-mobile-runtime-additions.py --ndk /path/to/android-ndk --jobs 2
```

The builder fails before writing artifacts if the API 28 AArch64 compiler is absent. It validates ELF architecture and rejects glibc linkage/build search paths, adds source/license receipts and writes only staging/mobile-runtime-additions. This is not publication. Review file ownership/dependency closure, execute on Android, run the existing package-quality gates, then publish through the repository's signing workflow. No compiled packages were built or indexed by this repair.

Recipe checks: `python tests/test-mobile-runtime-additions.py` passes. Python compilation and whitespace checks pass. These checks do not prove native build success.

Existing ca-certificates, zlib, liblzma, libcurl, openssl, libnghttp2, libnghttp3, libngtcp2, libidn2, libunistring, libssh2, c-ares, libevent, libuv and libsodium are indexed; no duplicate packages are proposed for them. Absence was checked by indexed package name, not an exhaustive payload ownership audit across all packages.
