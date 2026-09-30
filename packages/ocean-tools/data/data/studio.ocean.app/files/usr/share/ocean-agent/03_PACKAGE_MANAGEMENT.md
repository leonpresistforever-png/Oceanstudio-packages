# Package Management & Toolchain Operations

## 1. Primary Package Commands
Ocean Studio provides a native package manager frontend `pkg` wrapping signed Debian `apt` archives:

| Operation | Command | Notes |
| :--- | :--- | :--- |
| **Update Index** | `pkg update` or `apt-get update` | Synchronizes the latest signed repository snapshot. |
| **Install Package** | `pkg install -y <package>` | Installs packages without interactive confirmation prompts. |
| **Search Packages** | `pkg search <query>` | Queries the 6,500+ verified packages in the catalog. |
| **Package Details** | `pkg show <package>` | Displays package version, size, dependencies, and origin. |
| **Remove Package** | `pkg uninstall <package>` | Removes a package cleanly from the `$PREFIX` filesystem. |

---

## 2. Cryptographic Security & Provenance
- **Keyring**: `$PREFIX/etc/apt/keyrings/ocean.gpg` containing official Ocean Package Archive key `DE6CC7B9B2CF51DA5434663F5FBBA12482C45CC3`.
- **Repository URL**: `https://raw.githubusercontent.com/leonpresistforever-png/Oceanstudio-packages/main/apt`.
- **Integrity**: `InRelease` is signed via EdDSA/SHA256. Every `.deb` is validated against SHA256 checksums before installation.
- **Rule**: Never install `.deb` archives from untrusted or third-party web mirrors outside the verified Ocean repository.

---

## 3. Core Development Toolchains
The following verified upstream compilers and runtimes are available:
- **C/C++**: `clang`, `lld`, `make`, `pkg-config` (targeting Android Bionic API 28+).
- **Python**: `python` (Python 3.12/3.14), `pip` (use `python -m pip install <package>`).
- **Node.js**: `node`, `npm` (fast V8 JavaScript runtime for backend tools and web servers).
- **Git**: `git` (official distributed version control).
- **Rust / Go**: `rustc`, `cargo`, `golang` (AArch64 cross-capable compiler suites).
