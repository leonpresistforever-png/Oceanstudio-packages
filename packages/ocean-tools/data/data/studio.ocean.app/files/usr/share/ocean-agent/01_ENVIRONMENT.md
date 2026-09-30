# Ocean Runtime Environment Specification

## 1. Architectural Scope & Target Environment
- **Platform**: Native Android OS targeting **minSdk 28 (Android 9.0 Pie)** on 64-bit ARM (`aarch64` / `arm64-v8a`).
- **Core C Library**: Android Bionic libc (`/system/bin/linker64`).
- **Process Privilege**: Unprivileged, sandboxed native Android application user ID (non-root).
- **Execution Model**: Real local Linux PTY and subshell child processes managed directly by Ocean Studio.

---

## 2. Autonomous Filesystem Hierarchy
Ocean Studio enforces a strict, independent filesystem prefix completely isolated from external distributions:

| Path | Environment Variable | Purpose |
| :--- | :--- | :--- |
| `/data/data/studio.ocean.app/files/usr/` | `$PREFIX` | Application binaries (`bin/`), libraries (`lib/`), headers (`include/`), shared data (`share/`), configuration (`etc/`). |
| `/data/data/studio.ocean.app/files/home/` | `$HOME` | User home directory, project code, dotfiles (`.bashrc`, `.agent/`). |
| `/data/data/studio.ocean.app/files/usr/tmp/` | `$TMPDIR` | Ephemeral temporary scratch files, unix sockets, and build directories. |
| `/data/data/studio.ocean.app/files/usr/etc/apt/` | N/A | APT sources list, keyrings (`ocean.gpg`), and package repositories. |

---

## 3. Dynamic Linking & Dynamic Loader Constraints
- **Dynamic Linker**: `/system/bin/linker64` (provided by Android OS).
- **RPATH / RUNPATH**: All compiled ELF binaries and shared libraries use explicit RPATH pointing to `/data/data/studio.ocean.app/files/usr/lib`.
- **System Separation**: System libraries in `/system/lib64` and `/vendor/lib64` provide hardware, graphics (OpenGL/Vulkan), and Bionic primitives.
- **Zero External Contamination**: No paths containing `/data/data/com.termux`, `com.termux.*`, or foreign distribution wrappers are permitted.

---

## 4. Hardware & Resource Context
- Multiple CPU cores (AArch64 multi-core).
- Memory-constrained mobile environment: always use reasonable compiler threads (e.g. `make -j2` or `-j4`) to prevent Out-Of-Memory (OOM) killer invocations.
- Storage resides in internal flash memory with POSIX permissions enforced by the Android Linux kernel.
