// btc_core6f — PERIOD-9 + THE ADVANTAGE, SCALED (v6)
// Built 2026-10-21 at Lux's direction ("Scale the advantage"), on top
// of btc_core5 (Period-9 protocol; see btc_core5.c / period-9 doc).
//
// THE SCALING: core4/5 checked each hash against ONE side target.
// core6 checks every hash against a LADDER of up to 4 side targets in
// the same pass — still zero extra hashes. Each hit is filed once, at
// the HARDEST tier it satisfies, tagged tier=<k> in that tier's
// sidefile. Suggested ladder on a live-tip grind:
//   tier0  2^224 (32 zero bits)   tier1  2^228 (28)
//   tier2  2^232 (24 zero bits)   tier3  2^236 (20)
// One grind now mints a spectrum of work records: the common tiers
// land in minutes, the rare tiers are jackpots riding for free.
// CLI: --target2/--sidefile pairs are repeatable (up to 4 tiers);
// a lone --target2/--sidefile behaves exactly as in core4/5.
// Everything else (Period-9 folds, caduceus serpents, rotation, lean
// hot loop, checkpoint/resume, FOUND/NONE formats) is unchanged.
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <pthread.h>
#include <openssl/sha.h>

#define CHUNK_BITS 20
#define NCHUNKS (1u << (32 - CHUNK_BITS))
#define CHUNK_SIZE (1u << CHUNK_BITS)

static const uint32_t IV[8] = {
    0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a,
    0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19
};
static const uint32_t WARP[9]  = {0x80e39, 0xa0ca1, 0xc0b0b, 0xe0973, 0x007dd, 0x45bdf, 0x425fb, 0x22793, 0x02929};
static const uint32_t WINV[9]  = {0x38009, 0x6d761, 0x9e8a3, 0x243bb, 0xb8875, 0x3201f, 0xd1d33, 0x80e9b, 0xc8319};

static uint8_t prevhash[32], merkle[32], TARGET_BE[32], TARGET2_BE[4][32];
static uint32_t T2TOP[4];
static int n_target2 = 0;
static uint32_t g_time, g_bits, g_version = 1, g_rot = 228;  // P9 FNV fallback; --rot overrides
static int nthreads = 2;
static volatile int found = 0, stop_flag = 0;
static volatile uint32_t found_nonce;
static uint8_t found_hash[32];
static volatile unsigned long long total_hashes = 0, side_hits = 0;
static volatile uint32_t next_claim = 0;
static uint8_t done_bitmap[NCHUNKS / 8];
static pthread_mutex_t bm_lock = PTHREAD_MUTEX_INITIALIZER;
static pthread_mutex_t side_lock = PTHREAD_MUTEX_INITIALIZER;
static char ckpt_path[256] = "", side_paths[4][256];
static volatile unsigned long long tier_hits[4] = {0, 0, 0, 0};

typedef struct { int tid; int bench; } warg_t;

static void record_side(int tier, uint32_t nonce, const uint8_t d[32]) {
    __sync_fetch_and_add(&side_hits, 1);
    __sync_fetch_and_add(&tier_hits[tier], 1);
    if (!side_paths[tier][0]) return;
    pthread_mutex_lock(&side_lock);
    FILE *f = fopen(side_paths[tier], "a");
    if (f) {
        fprintf(f, "SIDE %u ", nonce);
        for (int i = 31; i >= 0; i--) fprintf(f, "%02x", d[i]);
        fprintf(f, " tier=%d\n", tier);
        fclose(f);
    }
    pthread_mutex_unlock(&side_lock);
}

static int chunk_done(uint32_t chunk) {
    pthread_mutex_lock(&bm_lock);
    int d = (done_bitmap[chunk >> 3] >> (chunk & 7)) & 1;
    pthread_mutex_unlock(&bm_lock);
    return d;
}

static void *worker(void *p) {
    warg_t *a = (warg_t *)p;
    uint8_t hdr[80];
    memset(hdr, 0, sizeof hdr);
    hdr[0] = (uint8_t)g_version; hdr[1] = (uint8_t)(g_version >> 8);
    hdr[2] = (uint8_t)(g_version >> 16); hdr[3] = (uint8_t)(g_version >> 24);
    memcpy(hdr + 4, prevhash, 32);
    memcpy(hdr + 36, merkle, 32);
    hdr[68] = (uint8_t)g_time; hdr[69] = (uint8_t)(g_time >> 8);
    hdr[70] = (uint8_t)(g_time >> 16); hdr[71] = (uint8_t)(g_time >> 24);
    hdr[72] = (uint8_t)g_bits; hdr[73] = (uint8_t)(g_bits >> 8);
    hdr[74] = (uint8_t)(g_bits >> 16); hdr[75] = (uint8_t)(g_bits >> 24);
    SHA256_CTX mc; memcpy(mc.h, IV, sizeof mc.h);
    SHA256_Transform(&mc, hdr);
    uint32_t mid_h[8]; memcpy(mid_h, mc.h, sizeof mid_h);
    // LEAN: prebuild both block templates once; per hash patch only
    // the nonce word (blk1[12..15]) and the digest (blk2[0..31]).
    uint8_t blk1[64], blk2[64];
    memcpy(blk1, hdr + 64, 16);
    blk1[16] = 0x80; memset(blk1 + 17, 0, 39); blk1[62] = 0x02; blk1[63] = 0x80;
    memset(blk2, 0, 64);
    blk2[32] = 0x80; blk2[62] = 0x01; blk2[63] = 0x00;
    uint32_t ttop = ((uint32_t)TARGET_BE[0] << 24) | ((uint32_t)TARGET_BE[1] << 16)
                  | ((uint32_t)TARGET_BE[2] << 8) | TARGET_BE[3];
    uint32_t t2top[4];
    for (int t = 0; t < n_target2; t++) t2top[t] = T2TOP[t];
    unsigned long long local = 0;
    SHA256_CTX c;
    while (!found && !stop_flag) {
        uint32_t m = __sync_fetch_and_add(&next_claim, 1);
        if (m >= 2 * NCHUNKS) break;
        uint32_t c0; int serpentB;
        if ((m & 1) == 0) { c0 = m >> 1; serpentB = 0; }
        else { c0 = NCHUNKS - 1 - (m >> 1); serpentB = 1; }
        uint32_t chunk = (c0 + g_rot) % NCHUNKS;                    // pattern rotation
        if (chunk_done(chunk)) continue;
        uint32_t base = chunk << CHUNK_BITS;
        uint32_t fold = chunk % 9;
        uint32_t w = serpentB ? WINV[fold] : WARP[fold];
        for (uint32_t i = 0; i < CHUNK_SIZE && !found && !stop_flag; i++) {
            uint32_t nonce = base + ((i * w) & (CHUNK_SIZE - 1));
            blk1[12] = (uint8_t)nonce; blk1[13] = (uint8_t)(nonce >> 8);
            blk1[14] = (uint8_t)(nonce >> 16); blk1[15] = (uint8_t)(nonce >> 24);
            memcpy(c.h, mid_h, sizeof c.h);
            SHA256_Transform(&c, blk1);
            for (int j = 0; j < 8; j++) {
                blk2[4*j] = (uint8_t)(c.h[j] >> 24); blk2[4*j+1] = (uint8_t)(c.h[j] >> 16);
                blk2[4*j+2] = (uint8_t)(c.h[j] >> 8); blk2[4*j+3] = (uint8_t)c.h[j];
            }
            memcpy(c.h, IV, sizeof c.h);
            SHA256_Transform(&c, blk2);
            uint8_t d[32];
            for (int j = 0; j < 8; j++) {
                d[4*j] = (uint8_t)(c.h[j] >> 24); d[4*j+1] = (uint8_t)(c.h[j] >> 16);
                d[4*j+2] = (uint8_t)(c.h[j] >> 8); d[4*j+3] = (uint8_t)c.h[j];
            }
            local++;
            if (!a->bench) {
                uint32_t top = ((uint32_t)d[0] << 24) | ((uint32_t)d[1] << 16)
                             | ((uint32_t)d[2] << 8) | d[3];
                if (top <= ttop) {
                    int cmp = 0;
                    for (int j = 0; j < 32; j++) {
                        if (d[j] < TARGET_BE[j]) { cmp = -1; break; }
                        if (d[j] > TARGET_BE[j]) { cmp = 1; break; }
                    }
                    if (cmp <= 0) {
                        if (!found) { found_nonce = nonce; memcpy(found_hash, d, 32); found = 1; }
                        continue;
                    }
                }
                if (n_target2) {                                     // bycatch ladder
                    int best = -1;
                    for (int t = 0; t < n_target2; t++) {
                        if (top > t2top[t]) continue;
                        int cmp = 0;
                        for (int j = 0; j < 32; j++) {
                            if (d[31 - j] < TARGET2_BE[t][j]) { cmp = -1; break; }
                            if (d[31 - j] > TARGET2_BE[t][j]) { cmp = 1; break; }
                        }
                        if (cmp <= 0 && (best < 0 || memcmp(TARGET2_BE[t], TARGET2_BE[best], 32) < 0))
                            best = t;                                // hardest tier satisfied
                    }
                    if (best >= 0) record_side(best, nonce, d);
                }
            }
        }
        __sync_fetch_and_add(&total_hashes, local); local = 0;
        pthread_mutex_lock(&bm_lock);
        done_bitmap[chunk >> 3] |= (uint8_t)(1u << (chunk & 7));
        pthread_mutex_unlock(&bm_lock);
    }
    __sync_fetch_and_add(&total_hashes, local);
    return NULL;
}

static uint32_t done_count(void) {
    uint32_t n = 0;
    pthread_mutex_lock(&bm_lock);
    for (uint32_t c = 0; c < NCHUNKS; c++) n += (done_bitmap[c >> 3] >> (c & 7)) & 1;
    pthread_mutex_unlock(&bm_lock);
    return n;
}

static void write_ckpt(void) {
    if (!ckpt_path[0]) return;
    FILE *f = fopen(ckpt_path, "w");
    if (!f) return;
    fprintf(f, "%u\n", next_claim);
    pthread_mutex_lock(&bm_lock);
    for (uint32_t i = 0; i < NCHUNKS / 8; i++) fprintf(f, "%02x", done_bitmap[i]);
    pthread_mutex_unlock(&bm_lock);
    fprintf(f, "\n%u\n", g_rot);
    fclose(f);
}

static void *monitor(void *u) {
    (void)u;
    unsigned long long prev = 0;
    while (!found && !stop_flag) {
        struct timespec ts = {5, 0};
        nanosleep(&ts, NULL);
        unsigned long long cur = total_hashes;
        fprintf(stderr, "[period9+] %llu M hashes, %.2f MH/s, chunks %u/%u, side hits %llu (tiers %llu/%llu/%llu/%llu)\n",
                cur / 1000000ULL, (double)(cur - prev) / 5.0 / 1e6, done_count(), NCHUNKS, side_hits,
                tier_hits[0], tier_hits[1], tier_hits[2], tier_hits[3]);
        prev = cur;
        write_ckpt();
        fflush(stderr);
    }
    return NULL;
}

int main(int argc, char **argv) {
    if (argc < 6) { fprintf(stderr, "usage: %s prevhash merkle time bits target [version] [nthreads] [--checkpoint f] [--resume] [--bench s] [--rot N] [--target2 hex] [--sidefile f]\n", argv[0]); return 2; }
    if (strlen(argv[1]) != 64 || strlen(argv[2]) != 64 || strlen(argv[5]) != 64) return 2;
    for (int i = 0; i < 32; i++) {
        unsigned v; sscanf(argv[1] + 2*i, "%2x", &v); prevhash[i] = (uint8_t)v;
        sscanf(argv[2] + 2*i, "%2x", &v); merkle[i] = (uint8_t)v;
        sscanf(argv[5] + 2*i, "%2x", &v); TARGET_BE[i] = (uint8_t)v;
    }
    g_time = (uint32_t)strtoul(argv[3], NULL, 10);
    g_bits = (uint32_t)strtoul(argv[4], NULL, 16);
    int bench_secs = 0, resume = 0;
    for (int i = 6; i < argc; i++) {
        if (!strcmp(argv[i], "--checkpoint") && i + 1 < argc) strncpy(ckpt_path, argv[++i], 255);
        else if (!strcmp(argv[i], "--resume")) resume = 1;
        else if (!strcmp(argv[i], "--bench") && i + 1 < argc) bench_secs = atoi(argv[++i]);
        else if (!strcmp(argv[i], "--rot") && i + 1 < argc) g_rot = (uint32_t)strtoul(argv[++i], NULL, 10) % NCHUNKS;
        else if (!strcmp(argv[i], "--target2") && i + 1 < argc) {
            const char *t2 = argv[++i];
            if (strlen(t2) == 64 && n_target2 < 4) {
                for (int j = 0; j < 32; j++) { unsigned v; sscanf(t2 + 2*j, "%2x", &v); TARGET2_BE[n_target2][j] = (uint8_t)v; }
                T2TOP[n_target2] = ((uint32_t)TARGET2_BE[n_target2][0] << 24) | ((uint32_t)TARGET2_BE[n_target2][1] << 16)
                                 | ((uint32_t)TARGET2_BE[n_target2][2] << 8) | TARGET2_BE[n_target2][3];
                n_target2++;
            }
        }
        else if (!strcmp(argv[i], "--sidefile") && i + 1 < argc) {
            if (n_target2 > 0) strncpy(side_paths[n_target2 - 1], argv[++i], 255);
            else i++;
        }
        else if (i == 6) g_version = (uint32_t)strtoul(argv[i], NULL, 0);
        else if (i == 7) nthreads = atoi(argv[i]);
    }
    if (resume && ckpt_path[0]) {
        FILE *f = fopen(ckpt_path, "r");
        if (f) {
            uint32_t saved = 0;
            if (fscanf(f, "%u", &saved) == 1) {
                char hexbuf[NCHUNKS / 4 + 2];
                if (fscanf(f, "%1025s", hexbuf) == 1 && strlen(hexbuf) == NCHUNKS / 4) {
                    for (uint32_t i = 0; i < NCHUNKS / 8; i++) {
                        unsigned v; sscanf(hexbuf + 2*i, "%2x", &v);
                        done_bitmap[i] = (uint8_t)v;
                    }
                }
                next_claim = saved > 64 ? saved - 64 : 0;
            }
            fclose(f);
        }
    }
    pthread_t th[16], mon; warg_t args[16];
    if (!bench_secs) pthread_create(&mon, NULL, monitor, NULL);
    for (int i = 0; i < nthreads; i++) {
        args[i].tid = i; args[i].bench = bench_secs > 0;
        pthread_create(&th[i], NULL, worker, &args[i]);
    }
    if (bench_secs) {
        struct timespec ts = {bench_secs, 0};
        nanosleep(&ts, NULL);
        stop_flag = 1;
    }
    for (int i = 0; i < nthreads; i++) pthread_join(th[i], NULL);
    if (bench_secs) {
        printf("BENCH %llu hashes in %ds = %.2f MH/s total (%d threads)\n",
               total_hashes, bench_secs, (double)total_hashes / bench_secs / 1e6, nthreads);
        return 0;
    }
    write_ckpt();
    if (!found) { printf("NONE side=%llu\n", side_hits); return 1; }
    printf("FOUND %u %u ", g_time, found_nonce);
    for (int i = 31; i >= 0; i--) printf("%02x", found_hash[i]);
    printf(" side=%llu\n", side_hits);
    return 0;
}
