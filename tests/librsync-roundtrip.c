#include <librsync.h>
#include <stdio.h>
#include <string.h>
#define CHECK(x) do { if (!(x)) { fprintf(stderr, "failed at line %d\n", __LINE__); return 1; } } while (0)
int main(void) {
    const char *old = "Ocean library signature: this is the old payload.\n";
    const char *updated = "Ocean library signature: this is the NEW payload, with more content.\n";
    FILE *basis = fopen("basis", "w+b"), *next = fopen("next", "w+b");
    FILE *sig = fopen("signature", "w+b"), *delta = fopen("delta", "w+b"), *out = fopen("patched", "w+b");
    CHECK(basis && next && sig && delta && out);
    CHECK(fwrite(old, 1, strlen(old), basis) == strlen(old)); rewind(basis);
    CHECK(fwrite(updated, 1, strlen(updated), next) == strlen(updated)); rewind(next);
    CHECK(rs_sig_file(basis, sig, 16, 32, RS_RK_BLAKE2_SIG_MAGIC, NULL) == RS_DONE); rewind(sig);
    rs_signature_t *signature = NULL;
    CHECK(rs_loadsig_file(sig, &signature, NULL) == RS_DONE);
    CHECK(rs_build_hash_table(signature) == RS_DONE);
    CHECK(rs_delta_file(signature, next, delta, NULL) == RS_DONE);
    rewind(basis); rewind(delta);
    CHECK(rs_patch_file(basis, delta, out, NULL) == RS_DONE); rewind(out);
    char buffer[256]; size_t size = fread(buffer, 1, sizeof buffer, out);
    CHECK(size == strlen(updated) && memcmp(buffer, updated, size) == 0);
    rs_free_sumset(signature);
    fclose(basis); fclose(next); fclose(sig); fclose(delta); fclose(out);
    puts("signature, delta and patch round trip passed");
    return 0;
}
