// Bionic's ARM64 thread control block needs a 64-byte-aligned executable TLS
// segment. API-28 crtbegin does not provide the padding needed by the modern
// static libc shipped in NDK r27. Supply alignment at link time so TLS symbol
// offsets are computed correctly; do not rewrite an already-linked ELF header.
// Contract: platform/bionic/libc/bionic/bionic_elf_tls.cpp, reserve_exe_segment_and_tcb.
.section .tbss,"awT",@nobits
.p2align 6
.global __ocean_android_tls_alignment
.hidden __ocean_android_tls_alignment
.type __ocean_android_tls_alignment, @object
__ocean_android_tls_alignment:
.zero 1
.size __ocean_android_tls_alignment, 1
.section .note.GNU-stack,"",@progbits
