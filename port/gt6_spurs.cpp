// SPDX-License-Identifier: GPL-2.0-or-later
/*
 * GT6's SPURS set-up (D33).
 *
 * GT6 runs SPU job binaries and a policy module (Wws_Job) that the translate step does not
 * find ahead of time. They must run, so they run in ps3recomp's SPU interpreter, the D9
 * fallback (SPU_JOB_INTERP=1, patch 0008), and every run is counted in the milestone log as
 * spu:interp:<fingerprint>, which scripts/boot_game.py reports. Each image is dumped once to
 * <tree>/spu-missed/ (SPU_DUMP_MISS), and scripts/translate_game.py lifts what it finds
 * there on its next run, so the next build runs it as native code.
 *
 * The runtime's job-chain walker makes up a completion event per job by default. GT6 reads
 * those events as its own (its event-queue worker indexes a callback table with data2), and
 * on hardware the job manager sends none: a job reports its own end. So they are off
 * (SPURS_JOB_SYNTH_EVENTS=0). Faking a completion corrupts game state (O10).
 *
 * Each variable keeps a value the caller already set, for experiments.
 */

#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <sys/stat.h>

#include "gt6_paths.h"   /* GT6_DEFAULT_SPU_MISSED (generated) */

extern "C" {
extern void (*g_spu_job_interp_hook)(uint64_t fp, uint32_t size);   /* spu_workload.c */
void ps3_msf(const char* fmt, ...);                                  /* milestone log */
}

static void count_interpreted_run(uint64_t fp, uint32_t size)
{
    (void)size;
    ps3_msf("spu:interp:%016llX", (unsigned long long)fp);
}

extern "C" void gt6_configure_spurs(void)
{
    setenv("SPU_JOB_INTERP", "1", 0);
    setenv("SPURS_JOB_SYNTH_EVENTS", "0", 0);
    const char* dump = getenv("SPU_DUMP_MISS");
    if (!dump || !*dump) {
        mkdir(GT6_DEFAULT_SPU_MISSED, 0755);   /* exists already after the first run */
        setenv("SPU_DUMP_MISS", GT6_DEFAULT_SPU_MISSED, 1);
    }
    g_spu_job_interp_hook = count_interpreted_run;
    printf("[boot] SPURS: unlifted SPU images run interpreted (D9), dumped to %s; "
           "no synthetic job events\n", getenv("SPU_DUMP_MISS"));
}
