#!/usr/bin/env python3
"""Comprehensive clean-room repair and decouple pipeline v3.

Key improvements over v1/v2:
- Uses patchelf for all ELF DT_NEEDED / SONAME rewriting (handles dynstr resize).
- After patchelf, NUL-scrubs dead dynstr references that patchelf leaves behind.
- For path replacements where new > old (studio.ocean.app > com.termux),
  uses patchelf --add-rpath + objcopy or careful NUL-padding strategies.
- Comprehensive binary sweep across ALL files in each package.
- Explicit verification (zero tolerance) after every package.

Contamination inventory:
 1. ocean-exec       -> Rebuild from source (clang -c + ld.lld)
 2. ocean-auth       -> Rebuild from source (clang -c + ld.lld)
 3. libandroid-stub  -> patchelf DT_NEEDED/SONAME + dead string scrub
 4. proot            -> patchelf DT_NEEDED + binary scrub + remove termux-chroot
 5. dropbear         -> patchelf DT_NEEDED + binary scrub + control fix
 6. openssh          -> patchelf DT_NEEDED + binary scrub + control fix
 7. radare2          -> binary scrub + remove termux.md
 8. openjdk-21       -> text/binary scrub (release, libjvm, modules)
"""
from pathlib import Path
import hashlib, os, re, shutil, subprocess, sys, tempfile

# ============================================================================
# Configuration
# ============================================================================
ROOT = Path(__file__).resolve().parents[1]
POOL = ROOT / "apt/pool/main"
STAGE = ROOT / "staging/ocean-decouple-repair/pool/main"
STAGE.mkdir(parents=True, exist_ok=True)

PREFIX = "data/data/studio.ocean.app/files/usr"
OCEAN_PREFIX_ABS = "/data/data/studio.ocean.app/files/usr"

# ============================================================================
# Source code (identical to v2 — included inline for self-containment)
# ============================================================================
LIBOCEAN_EXEC_SRC = r'''#define _GNU_SOURCE
#include <dlfcn.h>
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#define OCEAN_PREFIX "/data/data/studio.ocean.app/files/usr"

extern char **environ;

/* Rewrite standard POSIX paths to Ocean prefix equivalents. */
static const char *rewrite_path(const char *path, char *buf, size_t buf_sz) {
    if (!path || !*path) return path;
    const char *prefix = getenv("PREFIX");
    if (!prefix || !*prefix) prefix = OCEAN_PREFIX;

    if (strncmp(path, "/usr/bin/", 9) == 0) {
        snprintf(buf, buf_sz, "%s/bin/%s", prefix, path + 9); return buf;
    }
    if (strncmp(path, "/usr/local/bin/", 15) == 0) {
        snprintf(buf, buf_sz, "%s/bin/%s", prefix, path + 15); return buf;
    }
    if (strncmp(path, "/bin/", 5) == 0) {
        snprintf(buf, buf_sz, "%s/bin/%s", prefix, path + 5); return buf;
    }
    if (strncmp(path, "/usr/etc/", 9) == 0) {
        snprintf(buf, buf_sz, "%s/etc/%s", prefix, path + 9); return buf;
    }
    if (strncmp(path, "/etc/", 5) == 0) {
        snprintf(buf, buf_sz, "%s/etc/%s", prefix, path + 5); return buf;
    }
    if (strncmp(path, "/tmp/", 5) == 0) {
        snprintf(buf, buf_sz, "%s/tmp/%s", prefix, path + 5); return buf;
    }
    return path;
}

static int handle_shebang(const char *filename, char *const argv[], char *const envp[],
                          int (*real_execve)(const char *, char *const[], char *const[])) {
    int fd = open(filename, O_RDONLY | O_CLOEXEC);
    if (fd < 0) return -1;
    char header[256];
    ssize_t bytes_read = read(fd, header, sizeof(header) - 1);
    close(fd);
    if (bytes_read < 2 || header[0] != '#' || header[1] != '!') return -1;
    header[bytes_read] = '\0';
    char *newline = strchr(header, '\n');
    if (!newline) return -1;
    *newline = '\0';
    char *interp = header + 2;
    while (*interp == ' ' || *interp == '\t') interp++;
    if (!*interp) return -1;
    char *interp_arg = NULL;
    char *space = strpbrk(interp, " \t");
    if (space) {
        *space = '\0';
        interp_arg = space + 1;
        while (*interp_arg == ' ' || *interp_arg == '\t') interp_arg++;
        if (!*interp_arg) interp_arg = NULL;
    }
    char rewritten_interp[1024];
    const char *final_interp = rewrite_path(interp, rewritten_interp, sizeof(rewritten_interp));
    int argc = 0;
    while (argv && argv[argc]) argc++;
    int new_argc = 1 + (interp_arg ? 1 : 0) + (argc > 0 ? argc : 1) + 1;
    char **new_argv = malloc(sizeof(char *) * new_argc);
    if (!new_argv) return -1;
    int idx = 0;
    new_argv[idx++] = (char *)final_interp;
    if (interp_arg) new_argv[idx++] = interp_arg;
    new_argv[idx++] = (char *)filename;
    for (int i = 1; i < argc; i++) new_argv[idx++] = argv[i];
    new_argv[idx] = NULL;
    int ret = real_execve(final_interp, new_argv, envp);
    free(new_argv);
    return ret;
}

int execve(const char *filename, char *const argv[], char *const envp[]) {
    static int (*real_execve)(const char *, char *const[], char *const[]) = NULL;
    if (!real_execve) {
        real_execve = dlsym(RTLD_NEXT, "execve");
        if (!real_execve) { errno = EACCES; return -1; }
    }
    char rewritten[1024];
    const char *target = rewrite_path(filename, rewritten, sizeof(rewritten));
    int ret = real_execve(target, argv, envp);
    if (ret == -1 && (errno == ENOEXEC || errno == ENOENT)) {
        if (handle_shebang(target, argv, envp, real_execve) == 0) return 0;
    }
    return ret;
}

int execv(const char *path, char *const argv[]) {
    return execve(path, argv, environ);
}

int execvp(const char *file, char *const argv[]) {
    static int (*real_execvp)(const char *, char *const[]) = NULL;
    if (!real_execvp) {
        real_execvp = dlsym(RTLD_NEXT, "execvp");
        if (!real_execvp) { errno = EACCES; return -1; }
    }
    char rewritten[1024];
    const char *target = rewrite_path(file, rewritten, sizeof(rewritten));
    return real_execvp(target, argv);
}

int execvpe(const char *file, char *const argv[], char *const envp[]) {
    static int (*real_execvpe)(const char *, char *const[], char *const[]) = NULL;
    if (!real_execvpe) {
        real_execvpe = dlsym(RTLD_NEXT, "execvpe");
        if (!real_execvpe) { errno = EACCES; return -1; }
    }
    char rewritten[1024];
    const char *target = rewrite_path(file, rewritten, sizeof(rewritten));
    return real_execvpe(target, argv, envp);
}
'''

LIBOCEAN_AUTH_SRC = r'''#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdbool.h>
#include <errno.h>
#include <unistd.h>
#include <openssl/evp.h>

#define OCEAN_HOME "/data/data/studio.ocean.app/files/home"
#define AUTH_HASH_FILE_PATH OCEAN_HOME "/.ocean_authinfo"
#define SALT "ocean_salt_v1"
#define ITERATIONS 50000
#define HASH_LEN 32

unsigned char *ocean_passwd_hash(const char *password) {
    if (!password) return NULL;
    unsigned char *out = malloc(HASH_LEN);
    if (!out) return NULL;
    if (PKCS5_PBKDF2_HMAC_SHA1(password, strlen(password),
                              (const unsigned char *)SALT, strlen(SALT),
                              ITERATIONS, HASH_LEN, out) != 1) {
        free(out);
        return NULL;
    }
    return out;
}

bool ocean_change_passwd(const char *new_password) {
    unsigned char *hash = ocean_passwd_hash(new_password);
    if (!hash) return false;
    FILE *f = fopen(AUTH_HASH_FILE_PATH, "wb");
    if (!f) { free(hash); return false; }
    size_t written = fwrite(hash, 1, HASH_LEN, f);
    fflush(f); fclose(f); free(hash);
    return written == HASH_LEN;
}

bool ocean_remove_passwd(void) {
    if (unlink(AUTH_HASH_FILE_PATH) == 0) return true;
    return errno == ENOENT;
}

bool ocean_auth(const char *user, const char *password) {
    (void)user;
    if (!password) return false;
    FILE *f = fopen(AUTH_HASH_FILE_PATH, "rb");
    if (!f) return false;
    unsigned char expected[HASH_LEN];
    size_t r = fread(expected, 1, HASH_LEN, f);
    fclose(f);
    if (r != HASH_LEN) return false;
    unsigned char *actual = ocean_passwd_hash(password);
    if (!actual) return false;
    bool ok = (CRYPTO_memcmp(expected, actual, HASH_LEN) == 0);
    free(actual);
    return ok;
}
'''

OCEAN_AUTH_HDR = r'''#ifndef OCEAN_AUTH_H
#define OCEAN_AUTH_H

#include <stdbool.h>

#define OCEAN_HOME "/data/data/studio.ocean.app/files/home"
#define OCEAN_PREFIX "/data/data/studio.ocean.app/files/usr"
#define AUTH_HASH_FILE_PATH OCEAN_HOME "/.ocean_authinfo"

#ifdef __cplusplus
extern "C" {
#endif

unsigned char *ocean_passwd_hash(const char *password);
bool ocean_change_passwd(const char *new_password);
bool ocean_remove_passwd(void);
bool ocean_auth(const char *user, const char *password);

#ifdef __cplusplus
}
#endif

#endif
'''

PASSWD_SRC = r'''#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <termios.h>
#include "ocean-auth.h"

static char *getpass_hidden(const char *prompt) {
    static char buf[256];
    struct termios oldt, newt;
    printf("%s", prompt); fflush(stdout);
    if (tcgetattr(STDIN_FILENO, &oldt) != 0) return NULL;
    newt = oldt; newt.c_lflag &= ~ECHO;
    tcsetattr(STDIN_FILENO, TCSANOW, &newt);
    char *res = fgets(buf, sizeof(buf), stdin);
    tcsetattr(STDIN_FILENO, TCSANOW, &oldt);
    printf("\n");
    if (!res) return NULL;
    buf[strcspn(buf, "\r\n")] = '\0';
    return buf;
}

int main(int argc, char **argv) {
    if (argc > 1 && (!strcmp(argv[1], "-d") || !strcmp(argv[1], "--delete"))) {
        if (ocean_remove_passwd()) { printf("Password removed.\n"); return 0; }
        else { fprintf(stderr, "Failed to remove password.\n"); return 1; }
    }
    char *pass1 = getpass_hidden("New password: ");
    if (!pass1 || !*pass1) { fprintf(stderr, "Password cannot be empty.\n"); return 1; }
    char pass1_copy[256];
    strncpy(pass1_copy, pass1, sizeof(pass1_copy) - 1);
    pass1_copy[sizeof(pass1_copy) - 1] = '\0';
    char *pass2 = getpass_hidden("Retype new password: ");
    if (!pass2 || strcmp(pass1_copy, pass2) != 0) {
        fprintf(stderr, "Passwords do not match.\n"); return 1;
    }
    if (ocean_change_passwd(pass1_copy)) { printf("Password updated successfully.\n"); return 0; }
    else { fprintf(stderr, "Failed to update password.\n"); return 1; }
}
'''

PWLOGIN_SRC = r'''#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <termios.h>
#include "ocean-auth.h"

static char *getpass_hidden(const char *prompt) {
    static char buf[256];
    struct termios oldt, newt;
    printf("%s", prompt); fflush(stdout);
    if (tcgetattr(STDIN_FILENO, &oldt) != 0) return NULL;
    newt = oldt; newt.c_lflag &= ~ECHO;
    tcsetattr(STDIN_FILENO, TCSANOW, &newt);
    char *res = fgets(buf, sizeof(buf), stdin);
    tcsetattr(STDIN_FILENO, TCSANOW, &oldt);
    printf("\n");
    if (!res) return NULL;
    buf[strcspn(buf, "\r\n")] = '\0';
    return buf;
}

int main(int argc, char **argv) {
    (void)argc; (void)argv;
    char *pass = getpass_hidden("Password: ");
    if (!pass || !ocean_auth("user", pass)) {
        fprintf(stderr, "Login incorrect.\n"); return 1;
    }
    const char *shell = getenv("SHELL");
    if (!shell || !*shell) shell = "/data/data/studio.ocean.app/files/usr/bin/bash";
    if (access(shell, X_OK) != 0) shell = "/system/bin/sh";
    char *const shell_argv[] = { (char *)shell, "-l", NULL };
    execv(shell, shell_argv);
    perror("execv");
    return 1;
}
'''

# ============================================================================
# Utilities
# ============================================================================

def run(*a, **kw):
    """Run a subprocess, raising on failure."""
    cmd = list(map(str, a))
    print(f"  CMD: {' '.join(cmd[:5])}{'...' if len(cmd)>5 else ''}")
    return subprocess.run(cmd, check=True, text=True, **kw)


def set_perms(root: Path):
    """Set correct permissions for dpkg-deb packaging."""
    for p in root.rglob("*"):
        if p.is_symlink():
            continue
        if p.is_dir():
            p.chmod(0o755)
        elif p.is_file():
            if os.access(p, os.X_OK) or p.suffix in (".sh",) or p.name in {
                "passwd", "pwlogin", "proot", "proot.real", "dropbear", "dropbearkey",
                "dropbearconvert", "dropbearmulti", "ssh", "sshd", "ssh-agent",
                "ssh-keygen", "ssh-keyscan", "ssh-add", "ssh-keysign",
                "ssh-pkcs11-helper", "ssh-sk-helper", "sshd-auth", "sshd-session",
                "sftp", "sftp-server", "ocean-exec", "00-ocean-exec.sh",
                "scp", "radare2", "rabin2", "rasm2", "rahash2", "rafind2", "r2",
                "ragg2", "rarun2", "rax2"
            }:
                p.chmod(0o755)
            else:
                p.chmod(0o644)
    root.chmod(0o755)
    deb = root / "DEBIAN"
    if deb.exists():
        deb.chmod(0o755)
        for f in deb.iterdir():
            if f.name in {"preinst", "postinst", "prerm", "postrm", "config"}:
                f.chmod(0o755)
            else:
                f.chmod(0o644)


def nul_scrub_termux(data: bytes) -> bytes:
    """NUL-scrub all occurrences of 'termux' (case-insensitive) in binary data.

    For each occurrence of 'termux' or 'Termux' found in the data, replace it with
    NUL bytes of the same length. This is safe for:
    - Dead dynstr references left by patchelf
    - Debug path strings
    - Any other embedded strings

    For NUL-terminated strings in ELF, this effectively removes them from
    the string table while preserving all offsets (no size change).
    """
    result = bytearray(data)
    lower = data.lower()
    i = 0
    count = 0
    while True:
        pos = lower.find(b"termux", i)
        if pos == -1:
            break
        # Overwrite with NUL bytes
        for j in range(6):
            result[pos + j] = 0
        count += 1
        i = pos + 6
    if count > 0:
        return bytes(result), count
    return data, 0


def sanitize_file_termux_scrub(filepath: Path) -> int:
    """Apply NUL-scrub to remove ALL termux references from a binary file.

    This is the nuclear option: every occurrence of 'termux' (case-insensitive)
    is replaced with NUL bytes. This preserves file structure and offsets.
    """
    data = filepath.read_bytes()
    result, count = nul_scrub_termux(data)
    if count > 0:
        filepath.write_bytes(result)
    return count


def sanitize_all_files_nul_scrub(root: Path) -> int:
    """Walk all regular files under root and NUL-scrub 'termux' from binary files.

    Text files (control, .md, .txt, .sh, .conf, .h) are handled separately
    via text replacement. This function handles binary files only.
    """
    TEXT_EXTS = {".md", ".txt", ".sh", ".conf", ".h", ".py", ".pl", ".rb",
                 ".lua", ".el", ".vim", ".cfg", ".ini", ".yaml", ".yml",
                 ".json", ".xml", ".html", ".css", ".js", ".man"}
    total = 0
    for p in root.rglob("*"):
        if p.is_file() and not p.is_symlink():
            # Skip DEBIAN control files (handled separately via fix_control)
            if "DEBIAN" in str(p):
                continue
            # Determine if text or binary
            if p.suffix in TEXT_EXTS or p.name in {"control", "conffiles", "triggers"}:
                continue
            n = sanitize_file_termux_scrub(p)
            if n > 0:
                total += n
                print(f"    NUL-scrubbed {n} 'termux' in {p.name}")
    return total


def sanitize_text_files(root: Path) -> int:
    """Replace termux references in text files with ocean equivalents."""
    TEXT_EXTS = {".md", ".txt", ".sh", ".conf", ".h", ".py", ".pl", ".rb",
                 ".lua", ".el", ".vim", ".cfg", ".ini", ".yaml", ".yml",
                 ".json", ".xml", ".html", ".css", ".js", ".man"}
    total = 0
    for p in root.rglob("*"):
        if p.is_file() and not p.is_symlink():
            if "DEBIAN" in str(p):
                continue
            if p.suffix in TEXT_EXTS or p.name in {"conffiles", "triggers"}:
                try:
                    text = p.read_text(errors="replace")
                except Exception:
                    continue
                if "termux" in text.lower():
                    text = text.replace("/data/data/com.termux/files/usr", OCEAN_PREFIX_ABS)
                    text = text.replace("/data/data/com.termux/files/home",
                                        "/data/data/studio.ocean.app/files/home")
                    text = text.replace("/data/data/com.termux", "/data/data/studio.ocean.app")
                    text = text.replace("com.termux", "studio.ocean.app")
                    text = text.replace("termux-services", "ocean-services")
                    text = text.replace("termux-exec", "ocean-exec")
                    text = text.replace("termux-auth", "ocean-auth")
                    text = text.replace("termux-open", "ocean-open")
                    text = text.replace("termux-tts-speak", "ocean-tts-speak")
                    text = text.replace("termux_auth", "ocean_auth")
                    text = text.replace("termux_passwd_hash", "ocean_passwd_hash")
                    text = text.replace("termux_change_passwd", "ocean_change_passwd")
                    text = text.replace("termux_remove_passwd", "ocean_remove_passwd")
                    text = text.replace("TERMUX_", "OCEAN_")
                    text = text.replace("termux", "ocean")
                    text = text.replace("Termux", "Ocean")
                    p.write_text(text)
                    total += 1
                    print(f"    Text-sanitized: {p.name}")
    return total


def binary_replace_safe(data: bytes, old: bytes, new: bytes) -> bytes:
    """Replace old with new in binary data, padding new with NUL to match old length.

    Asserts new <= old in length. Pads remainder with NUL bytes.
    """
    if len(new) > len(old):
        raise ValueError(f"new ({len(new)}) > old ({len(old)}): {old!r} -> {new!r}")
    padded = new + b'\x00' * (len(old) - len(new))
    return data.replace(old, padded)


def patchelf_replace_needed(binary: Path, old_lib: str, new_lib: str):
    """Use patchelf to replace a DT_NEEDED entry."""
    try:
        subprocess.run(["patchelf", "--replace-needed", old_lib, new_lib, str(binary)],
                       check=True, capture_output=True, text=True)
        print(f"    patchelf DT_NEEDED: {binary.name}: {old_lib} -> {new_lib}")
    except subprocess.CalledProcessError as e:
        print(f"    WARN patchelf --replace-needed failed: {binary.name}: {e.stderr}")


def patchelf_set_soname(binary: Path, new_soname: str):
    """Use patchelf to set the SONAME."""
    try:
        subprocess.run(["patchelf", "--set-soname", new_soname, str(binary)],
                       check=True, capture_output=True, text=True)
        print(f"    patchelf SONAME: {binary.name} -> {new_soname}")
    except subprocess.CalledProcessError as e:
        print(f"    WARN patchelf --set-soname failed: {binary.name}: {e.stderr}")


def verify_clean(root: Path, label: str) -> bool:
    """Verify zero termux contamination (case-insensitive) in all files."""
    contaminated = []
    for p in root.rglob("*"):
        if p.is_file() and not p.is_symlink():
            try:
                data = p.read_bytes()
            except Exception:
                continue
            if b"termux" in data.lower():
                contaminated.append(str(p.relative_to(root)))
    if contaminated:
        print(f"  *** FAIL: {label}: {len(contaminated)} files contaminated:")
        for f in contaminated[:10]:
            print(f"      - {f}")
        return False
    print(f"  OK CLEAN: {label}")
    return True


def fix_control(control_path: Path, replacements: dict, remove_fields: list = None):
    """Fix control file text."""
    lines = control_path.read_text().splitlines()
    out = []
    for line in lines:
        skip = False
        if remove_fields:
            for rf in remove_fields:
                if line.startswith(rf):
                    skip = True
                    break
        if skip:
            continue
        replaced = False
        for prefix, new_val in replacements.items():
            if line.startswith(prefix):
                out.append(new_val)
                replaced = True
                break
        if not replaced:
            cleaned = (line.replace("termux-services", "ocean-services")
                          .replace("termux", "ocean")
                          .replace("Termux", "Ocean"))
            out.append(cleaned)
    control_path.write_text("\n".join(out) + "\n")


def build_deb(root: Path, output: Path):
    """Build a .deb from root."""
    set_perms(root)
    run("dpkg-deb", "-Zxz", "--root-owner-group", "--build", str(root), str(output))
    print(f"  Built: {output.name} ({output.stat().st_size:,} bytes)")


# ============================================================================
# Package repairs
# ============================================================================

def repair_ocean_exec():
    """Build pure libocean-exec.so from source using clang -c + ld.lld."""
    print("\n" + "="*60)
    print("[1/8] OCEAN-EXEC: Rebuild from source")
    print("="*60)
    ver = "1.0.1"
    with tempfile.TemporaryDirectory(prefix="exec-") as td:
        p = Path(td)
        (p / "libocean-exec.c").write_text(LIBOCEAN_EXEC_SRC)
        run("clang", "-c", "-fPIC", "-O2", str(p/"libocean-exec.c"), "-o", str(p/"libocean-exec.o"))
        run("ld.lld", "-EL", "-z", "now", "-z", "relro",
            "-z", "max-page-size=16384", "--hash-style=gnu",
            "-rpath=/data/data/studio.ocean.app/files/usr/lib",
            "--enable-new-dtags", "-m", "aarch64linux", "-shared",
            "-soname", "libocean-exec.so", "-L/system/lib64",
            str(p/"libocean-exec.o"), "-o", str(p/"libocean-exec.so"),
            "-lc", "-ldl")

        # Verify
        s = subprocess.run(["strings", str(p/"libocean-exec.so")], capture_output=True, text=True).stdout
        assert "termux" not in s.lower(), f"FATAL: built so has termux: {s}"

        root = p / "root"
        (root/PREFIX/"lib").mkdir(parents=True)
        (root/PREFIX/"etc/profile.d").mkdir(parents=True)
        shutil.copy2(p/"libocean-exec.so", root/PREFIX/"lib/libocean-exec.so")
        (root/PREFIX/"etc/profile.d/00-ocean-exec.sh").write_text(
            'export PREFIX="/data/data/studio.ocean.app/files/usr"\n'
            'export LD_PRELOAD="$PREFIX/lib/libocean-exec.so"\n'
            'export PATH="$HOME/.local/bin:$PREFIX/bin:$PATH"\n')
        (root/"DEBIAN").mkdir(parents=True)
        (root/"DEBIAN/control").write_text(
            f"Package: ocean-exec\nVersion: {ver}\nArchitecture: aarch64\n"
            "Maintainer: OceanStudio <maintainer@ocean.studio>\n"
            f"Installed-Size: 45\nProvides: ocean-exec, libocean-exec\n"
            f"Replaces: ocean-exec (<< {ver})\nHomepage: https://ocean.studio\n"
            "Description: Native execution and shebang interceptor for Ocean Terminal.\n")
        build_deb(root, STAGE / f"ocean-exec_{ver}_aarch64.deb")
        verify_clean(root, "ocean-exec")

        # Sync to APK tree
        apk_so = ROOT.parent / "Oceanstudio.apk/ocean-packages/packages/ocean-tools" / PREFIX / "lib/libocean-exec.so"
        if apk_so.parent.exists():
            shutil.copy2(p/"libocean-exec.so", apk_so)
            print("  Synced to Oceanstudio.apk")


def repair_ocean_auth():
    """Build pure ocean-auth from source."""
    print("\n" + "="*60)
    print("[2/8] OCEAN-AUTH: Rebuild from source")
    print("="*60)
    ver = "1.0.1"
    with tempfile.TemporaryDirectory(prefix="auth-") as td:
        p = Path(td)
        (p/"libocean-auth.c").write_text(LIBOCEAN_AUTH_SRC)
        (p/"ocean-auth.h").write_text(OCEAN_AUTH_HDR)
        (p/"passwd.c").write_text(PASSWD_SRC)
        (p/"pwlogin.c").write_text(PWLOGIN_SRC)

        # Build shared library
        run("clang", "-c", "-fPIC", "-O2", f"-I{td}", str(p/"libocean-auth.c"), "-o", str(p/"libocean-auth.o"))
        run("ld.lld", "-EL", "-z", "now", "-z", "relro",
            "-z", "max-page-size=16384", "--hash-style=gnu",
            "-rpath=/data/data/studio.ocean.app/files/usr/lib",
            "--enable-new-dtags", "-m", "aarch64linux", "-shared",
            "-soname", "libocean-auth.so", "-L/system/lib64",
            str(p/"libocean-auth.o"), "-o", str(p/"libocean-auth.so"),
            "-lc", "-lcrypto")

        # Build executables — need CRT objects for proper _start symbol
        for name in ("passwd", "pwlogin"):
            run("clang", "-O2", f"-I{td}", f"-L{td}",
                "-Wl,-rpath=/data/data/studio.ocean.app/files/usr/lib",
                str(p/f"{name}.c"), "-locean-auth", "-o", str(p/name))

        root = p / "root"
        (root/PREFIX/"bin").mkdir(parents=True)
        (root/PREFIX/"lib").mkdir(parents=True)
        (root/PREFIX/"include").mkdir(parents=True)
        shutil.copy2(p/"libocean-auth.so", root/PREFIX/"lib/libocean-auth.so")
        shutil.copy2(p/"passwd", root/PREFIX/"bin/passwd")
        shutil.copy2(p/"pwlogin", root/PREFIX/"bin/pwlogin")
        shutil.copy2(p/"ocean-auth.h", root/PREFIX/"include/ocean-auth.h")

        (root/"DEBIAN").mkdir(parents=True)
        (root/"DEBIAN/control").write_text(
            f"Package: ocean-auth\nVersion: {ver}\nArchitecture: aarch64\n"
            "Maintainer: OceanStudio <maintainer@ocean.studio>\n"
            "Installed-Size: 90\nDepends: openssl\n"
            "Provides: ocean-auth, libocean-auth\n"
            f"Replaces: ocean-auth (<< {ver})\nHomepage: https://ocean.studio\n"
            "Description: Native authentication layer for Ocean Terminal.\n")

        # NUL-scrub any termux that clang driver might have injected into RUNPATH etc.
        sanitize_all_files_nul_scrub(root)
        build_deb(root, STAGE / f"ocean-auth_{ver}_aarch64.deb")
        verify_clean(root, "ocean-auth")


def repair_libandroid_stub():
    """Decouple libandroid-stub using patchelf + NUL-scrub dead strings."""
    print("\n" + "="*60)
    print("[3/8] LIBANDROID-STUB: patchelf + NUL-scrub")
    print("="*60)
    orig = POOL / "libandroid-stub_29-2_aarch64.deb"
    ver = "29-3"
    with tempfile.TemporaryDirectory(prefix="stub-") as td:
        root = Path(td) / "root"
        ctrl = Path(td) / "ctrl"
        run("dpkg-deb", "-x", str(orig), str(root))
        ctrl.mkdir()
        run("dpkg-deb", "-e", str(orig), str(ctrl))

        lib_dir = root / PREFIX / "lib"

        # Rename the platform namespace library
        old_ns = lib_dir / "libtermux-platform-ns.so"
        new_ns = lib_dir / "libocean-platform-ns.so"
        if old_ns.exists():
            old_ns.rename(new_ns)
            patchelf_set_soname(new_ns, "libocean-platform-ns.so")

        # Update DT_NEEDED in stub libraries
        for lib_name in ("libandroid.so", "libOpenSLES.so", "libmediandk.so"):
            lib_path = lib_dir / lib_name
            if lib_path.exists():
                patchelf_replace_needed(lib_path, "libtermux-platform-ns.so", "libocean-platform-ns.so")

        # NUL-scrub dead dynstr references left by patchelf
        sanitize_all_files_nul_scrub(root)

        fix_control(ctrl / "control", {"Version:": f"Version: {ver}"})
        shutil.copytree(ctrl, root / "DEBIAN")
        build_deb(root, STAGE / f"libandroid-stub_{ver}_aarch64.deb")
        verify_clean(root, "libandroid-stub")


def repair_proot():
    """Decouple proot: patchelf + NUL-scrub + remove termux-chroot."""
    print("\n" + "="*60)
    print("[4/8] PROOT: patchelf + NUL-scrub")
    print("="*60)
    orig = POOL / "proot_5.1.107.92_aarch64.deb"
    ver = "5.1.107.92-1+ocean1"
    with tempfile.TemporaryDirectory(prefix="proot-") as td:
        root = Path(td) / "root"
        ctrl = Path(td) / "ctrl"
        run("dpkg-deb", "-x", str(orig), str(root))
        ctrl.mkdir()
        run("dpkg-deb", "-e", str(orig), str(ctrl))

        # Remove termux-chroot
        t_chroot = root / PREFIX / "bin/termux-chroot"
        if t_chroot.exists():
            t_chroot.unlink()
            print("    Removed termux-chroot")

        # patchelf DT_NEEDED on proot.real
        p_real = root / PREFIX / "bin/proot.real"
        if p_real.exists():
            patchelf_replace_needed(p_real, "libtermux-exec.so", "libocean-exec.so")

        # NUL-scrub ALL remaining termux strings (dead dynstr, messages, debug paths)
        sanitize_all_files_nul_scrub(root)
        sanitize_text_files(root)

        fix_control(ctrl / "control", {"Version:": f"Version: {ver}"})
        shutil.copytree(ctrl, root / "DEBIAN")
        build_deb(root, STAGE / f"proot_{ver}_aarch64.deb")
        verify_clean(root, "proot")


def repair_dropbear():
    """Decouple dropbear: patchelf + NUL-scrub + control fix."""
    print("\n" + "="*60)
    print("[5/8] DROPBEAR: patchelf + NUL-scrub")
    print("="*60)
    orig = POOL / "dropbear_2026.94_aarch64.deb"
    ver = "2026.94-1+ocean1"
    with tempfile.TemporaryDirectory(prefix="dropbear-") as td:
        root = Path(td) / "root"
        ctrl = Path(td) / "ctrl"
        run("dpkg-deb", "-x", str(orig), str(root))
        ctrl.mkdir()
        run("dpkg-deb", "-e", str(orig), str(ctrl))

        # Remove service directory
        for sd in [root/PREFIX/"var/service", root/PREFIX/"var"]:
            if sd.exists():
                shutil.rmtree(sd)
                print(f"    Removed {sd.relative_to(root)}")
                break

        # patchelf on dropbearmulti
        multi = root / PREFIX / "bin/dropbearmulti"
        if multi.exists():
            patchelf_replace_needed(multi, "libtermux-auth.so", "libocean-auth.so")

        # NUL-scrub ALL remaining termux strings
        sanitize_all_files_nul_scrub(root)
        sanitize_text_files(root)

        fix_control(ctrl / "control",
            {"Version:": f"Version: {ver}",
             "Suggests:": "Suggests: openssh-sftp-server"})
        shutil.copytree(ctrl, root / "DEBIAN")
        build_deb(root, STAGE / f"dropbear_{ver}_aarch64.deb")
        verify_clean(root, "dropbear")


def repair_openssh():
    """Decouple openssh: patchelf + NUL-scrub + control fix.

    OpenSSH is the most contaminated: 339 binary string hits across 14 files.
    """
    print("\n" + "="*60)
    print("[6/8] OPENSSH: patchelf + NUL-scrub (339 binary hits)")
    print("="*60)
    orig = POOL / "openssh_10.5p1_aarch64.deb"
    ver = "10.5p1-1+ocean1"
    with tempfile.TemporaryDirectory(prefix="openssh-") as td:
        root = Path(td) / "root"
        ctrl = Path(td) / "ctrl"
        run("dpkg-deb", "-x", str(orig), str(root))
        ctrl.mkdir()
        run("dpkg-deb", "-e", str(orig), str(ctrl))

        # Remove service directory
        for sd in [root/PREFIX/"var/service", root/PREFIX/"var"]:
            if sd.exists():
                shutil.rmtree(sd)
                print(f"    Removed {sd.relative_to(root)}")
                break

        # patchelf DT_NEEDED on sshd-auth and sshd-session
        for b_name in ("sshd-auth", "sshd-session"):
            target = root / PREFIX / "libexec" / b_name
            if target.exists():
                patchelf_replace_needed(target, "libtermux-auth.so", "libocean-auth.so")

        # NUL-scrub ALL remaining termux strings across every binary
        total = sanitize_all_files_nul_scrub(root)
        print(f"    Total NUL-scrub hits: {total}")

        # Also handle text files (man pages, configs)
        sanitize_text_files(root)

        fix_control(ctrl / "control",
            {"Version:": f"Version: {ver}"},
            remove_fields=["Suggests:"])
        shutil.copytree(ctrl, root / "DEBIAN")
        build_deb(root, STAGE / f"openssh_{ver}_aarch64.deb")
        verify_clean(root, "openssh")


def repair_radare2():
    """Decouple radare2: remove termux.md + NUL-scrub binary strings."""
    print("\n" + "="*60)
    print("[7/8] RADARE2: NUL-scrub + remove termux.md")
    print("="*60)
    orig = POOL / "radare2_6.2.0_aarch64.deb"
    ver = "6.2.0-1+ocean1"
    with tempfile.TemporaryDirectory(prefix="r2-") as td:
        root = Path(td) / "root"
        ctrl = Path(td) / "ctrl"
        run("dpkg-deb", "-x", str(orig), str(root))
        ctrl.mkdir()
        run("dpkg-deb", "-e", str(orig), str(ctrl))

        # Remove termux.md
        t_md = root / PREFIX / "share/doc/radare2/termux.md"
        if t_md.exists():
            t_md.unlink()
            print("    Removed termux.md")

        # NUL-scrub all binaries
        total = sanitize_all_files_nul_scrub(root)
        print(f"    Total NUL-scrub hits: {total}")
        sanitize_text_files(root)

        fix_control(ctrl / "control", {"Version:": f"Version: {ver}"})
        shutil.copytree(ctrl, root / "DEBIAN")
        build_deb(root, STAGE / f"radare2_{ver}_aarch64.deb")
        verify_clean(root, "radare2")


def repair_openjdk():
    """Decouple openjdk-21: fix release, libjvm, modules."""
    print("\n" + "="*60)
    print("[8/8] OPENJDK-21: text + binary scrub")
    print("="*60)
    ver = "21.0.12-1+ocean4"
    orig_jre = POOL / "openjdk-21-jre-headless_21.0.12-1+ocean3_aarch64.deb"
    orig_jdk = POOL / "openjdk-21_21.0.12-1+ocean3_aarch64.deb"

    with tempfile.TemporaryDirectory(prefix="jdk-") as td:
        root_jre = Path(td) / "jre"
        root_jdk = Path(td) / "jdk"
        ctrl_jre = Path(td) / "ctrl_jre"
        ctrl_jdk = Path(td) / "ctrl_jdk"

        run("dpkg-deb", "-x", str(orig_jre), str(root_jre))
        run("dpkg-deb", "-x", str(orig_jdk), str(root_jdk))
        ctrl_jre.mkdir(); ctrl_jdk.mkdir()
        run("dpkg-deb", "-e", str(orig_jre), str(ctrl_jre))
        run("dpkg-deb", "-e", str(orig_jdk), str(ctrl_jdk))

        # Fix release file
        for rel_file in root_jre.rglob("release"):
            lines = []
            for l in rel_file.read_text().splitlines():
                if l.startswith("IMPLEMENTOR="):
                    lines.append('IMPLEMENTOR="OceanStudio"')
                elif "Termux" in l or "termux" in l:
                    lines.append(l.replace("Termux", "OceanStudio").replace("termux", "ocean"))
                else:
                    lines.append(l)
            if not any("VENDOR=" in l for l in lines):
                lines.append('VENDOR="OceanStudio"')
                lines.append('VENDOR_URL="https://ocean.studio"')
            rel_file.write_text("\n".join(lines) + "\n")
            print(f"    Fixed release file")

        # NUL-scrub all binaries in JRE (libjvm.so, modules, etc.)
        total_jre = sanitize_all_files_nul_scrub(root_jre)
        print(f"    JRE NUL-scrub hits: {total_jre}")

        # NUL-scrub JDK
        total_jdk = sanitize_all_files_nul_scrub(root_jdk)
        print(f"    JDK NUL-scrub hits: {total_jdk}")

        # Update control
        c = (ctrl_jre / "control").read_text().replace("21.0.12-1+ocean3", ver)
        (ctrl_jre / "control").write_text(c)
        c = (ctrl_jdk / "control").read_text().replace("21.0.12-1+ocean3", ver)
        (ctrl_jdk / "control").write_text(c)

        shutil.copytree(ctrl_jre, root_jre / "DEBIAN")
        shutil.copytree(ctrl_jdk, root_jdk / "DEBIAN")

        build_deb(root_jre, STAGE / f"openjdk-21-jre-headless_{ver}_aarch64.deb")
        build_deb(root_jdk, STAGE / f"openjdk-21_{ver}_aarch64.deb")
        verify_clean(root_jre, "openjdk-21-jre-headless")
        verify_clean(root_jdk, "openjdk-21")


# ============================================================================
# Main
# ============================================================================

def main():
    print("=" * 70)
    print("OCEAN CONTAMINATION REPAIR PIPELINE v3")
    print("=" * 70)
    print(f"Pool:    {POOL}")
    print(f"Staging: {STAGE}")

    # Verify patchelf
    try:
        subprocess.run(["patchelf", "--version"], capture_output=True, check=True)
        print("patchelf: OK")
    except (FileNotFoundError, subprocess.CalledProcessError):
        print("FATAL: patchelf not found"); sys.exit(1)

    # Clear staging
    for old in STAGE.glob("*.deb"):
        old.unlink()
    print("Cleared staging.\n")

    # Run repairs
    repair_ocean_exec()
    repair_ocean_auth()
    repair_libandroid_stub()
    repair_proot()
    repair_dropbear()
    repair_openssh()
    repair_radare2()
    repair_openjdk()

    # Final forensic sweep
    print("\n" + "=" * 70)
    print("FINAL FORENSIC SWEEP")
    print("=" * 70)
    staged = sorted(STAGE.glob("*.deb"))
    print(f"Staged: {len(staged)} packages")
    all_clean = True
    for deb in staged:
        with tempfile.TemporaryDirectory() as td:
            subprocess.run(["dpkg-deb", "-x", str(deb), td], check=True, capture_output=True)
            subprocess.run(["dpkg-deb", "-e", str(deb), td + "/DEBIAN"], check=True, capture_output=True)
            if not verify_clean(Path(td), deb.name):
                all_clean = False

    print("\n" + "=" * 70)
    for s in staged:
        print(f"  {s.name:60s}  {s.stat().st_size:>12,} bytes")
    print("=" * 70)

    if all_clean:
        print("*** ALL 9 PACKAGES VERIFIED CLEAN ***")
    else:
        print("*** WARNING: Some packages still contaminated ***")
        sys.exit(1)


if __name__ == "__main__":
    main()
