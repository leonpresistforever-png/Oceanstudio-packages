# Ocean Android native runtime additions

The initial 13 Android API 28 AArch64 packages were compiled successfully in workflow run 37179897379 from pinned official upstream sources. They include seven matching FFmpeg libraries, three Mbed TLS libraries, libwebsockets, ocean-ffmpeg-native, and ocean-llama-runtime. Build receipts contain source revisions and binary hashes. Physical-device execution is still required; a cross-build is not that test.

The indexed older ffmpeg executable uses the glibc loader. This build preserves that command and adds `ocean-ffmpeg` and `ocean-ffprobe` using Bionic and the matching libav/libsw packages. Mbed TLS 3 enables HTTPS, with FFmpeg version-3 license configuration and applicable LGPL notices. libwebsockets in this build provides HTTP/WebSocket transport with TLS disabled.

Two further genuine repairs are built by the same workflow: `ollama-cli` replaces the old success-printing stub with official Ollama and its matching llama.cpp CPU backend; `mandoc` supplies upstream mandoc, demandoc and makewhatis. Ollama keeps the official ../lib/ollama helper layout. All inputs come from upstream; no Termux source, packages or prefix are used.

```sh
python scripts/build-mobile-runtime-additions.py --ndk /path/to/android-ndk --jobs 4
```

The builder validates Android ELF architecture, glibc exclusion, loader paths and actual 16 KiB PT_LOAD alignment. It stages archives with licenses and source/hash receipts. The complete repository publisher separately checks dependency closure and file ownership before signing with the existing trusted archive key. Publication failure never replaces the live signed index.
