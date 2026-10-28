// SPDX-License-Identifier: GPL-2.0-or-later
/*
 * Adapted from ps3recomp templates/project/main.cpp at commit
 * 4e8f3ca87a3e1d87bb83b8b7e9348fe2685cd514. That file:
 * Copyright (c) 2026 Ned Heller / sp00nznet, MIT licence
 * (full text in THIRD-PARTY-NOTICES.md and third_party/ps3recomp/LICENSE).
 *
 * The GT6 runner: gt6 <path to EMAIN.SELF.elf>. Changes from the template, and nothing
 * else: the usage line and banner, the window title, and the VFS roots (the disc tree and
 * /dev_hdd0 default to the gt6unpack tree this build was configured for, gt6_paths.h, with
 * /dev_hdd0 on its play folder, /dev_hdd1 beside it; PS3_VFS_ROOT, PS3_HDD0_ROOT and PS3_HDD1_ROOT
 * override; a /dev_hdd0 folder
 * without prepare.json beside it stops the start), and the guest command line (the launch
 * contract, configure_guest_argv), and the SPURS set-up call (gt6_configure_spurs). The
 * template's Windows and Linux paths are kept so the file stays diffable against the
 * template; the port builds on macOS arm64 only.
 *
 * Template header follows.
 *
 * This is the runner. It boots a lifted title through the toolkit's PPU
 * scaffold: allocate the flat guest VM, load the PPU ELF named on the command
 * line, register the lifted function table and the HLE NID handlers, start a
 * frame clock, and dispatch the entry OPD.
 *
 * The scaffold does the work; nothing below reimplements it. ppu_load_elf,
 * ppu_recomp_register, ppu_hle_init, ppu_sysprx_register, ppu_fs_register,
 * lv2_init_syscalls and ppu_run all come from the toolkit, compiled into this
 * project from PS3RECOMP_DIR (see CMakeLists.txt). What is left here is the
 * part a port owns: which backend to present through, how the frame clock is
 * paced, and whatever diagnostics the title turns out to need.
 *
 * runtime/ppu/tests/boot_main.cpp in the toolkit is the same boot in its
 * fully-instrumented form -- crash filter, hang watchdog, guest-PC sampling
 * profiler. Read it when a boot goes wrong; copy from it what the title
 * needs. It is deliberately not what a fresh project starts with.
 *
 * The one part that IS duplicated from it is the frame clock below, because a
 * port is expected to change its pacing and a shared one would be the wrong
 * shape for that. It was copied faithfully, comments and all. If a pacing bug
 * is fixed in one of the two, look at the other.
 *
 * This builds on Windows, macOS and Linux. CI builds and runs it against the
 * boot smoke title on the last two, and compile-checks it against clang-cl on
 * the first (tools/check_ppu_scaffold.py).
 */

/* The lifter's generated header, which declares ppu_context and the function
 * table. It comes first: everything below is written against that struct. */
#include "ppu_recomp.h"

/* The Win32 names -- Sleep, GetTickCount64, CreateThread, InterlockedIncrement,
 * VirtualAlloc, the scalar typedefs -- from one place. On Windows this is a
 * passthrough to <windows.h>; off Windows the toolkit's shim supplies the same
 * names over pthreads and mmap, so the call sites below are written once. */
#include "win32_compat.h"

#include "gt6_paths.h"   /* GT6_DEFAULT_VFS_ROOT, GT6_DEFAULT_HDD0_ROOT (generated) */

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>   /* stat, mkdir: the /dev_hdd0 and /dev_hdd1 folders, see configure_vfs_roots */
#include <unistd.h>     /* execv: exit-spawn, see gt6_exitspawn */
#include <fcntl.h>      /* FD_CLOEXEC on guest files before the exec */
#include <string>
#if defined(__APPLE__)
#include <mach-o/dyld.h>   /* _NSGetExecutablePath */
#include <CommonCrypto/CommonDigest.h>   /* CC_SHA256: which EMAIN.SELF is on disk (D44) */
#endif
#include <errno.h>

#ifndef _WIN32
#include <sys/mman.h>   /* mmap: the guest arena, see alloc_guest_vm */
#endif

#if defined(__APPLE__)
#include <CoreFoundation/CoreFoundation.h>   /* the main thread's run loop, see run_guest */
#include <pthread.h>
#endif

#ifdef _WIN32
/* timeBeginPeriod: <windows.h> arrives with WIN32_LEAN_AND_MEAN set, which
 * excludes the multimedia timer API, so it is asked for by name -- and after
 * windows.h, since timeapi.h uses UINT. No shim exists off Windows because
 * there is nothing to shim: the 15.6 ms default timer granularity this works
 * around is a Windows problem. */
#include <timeapi.h>
#endif

/* ---------------------------------------------------------------------------
 * What the scaffold gives this file
 * -----------------------------------------------------------------------*/
extern "C" {
uint32_t ppu_load_elf(const char* path);      /* ELF -> guest RAM, returns entry OPD */
void     ppu_recomp_register(void);           /* generated: lifted table -> address map */
void     ppu_hle_init(void);                  /* firmware import NID -> HLE handler */
void     ppu_sysprx_register(void);           /* boot-critical CRT (sys_initialize_tls, ...) */
void     ppu_fs_register(void);               /* cellFs over the real game directory */
void     lv2_init_syscalls(void);             /* the lv2 syscall table */
int      ppu_run(uint32_t entry_opd, uint32_t stack_top);

/* This project's own: load whatever real system PRX modules the title needs
 * into guest RAM and register their exports. stubs.cpp has the empty version
 * a game with no lifted PRX wants. */
void     ps3_load_prx_modules(void);
void     gt6_configure_spurs(void);           /* gt6_spurs.cpp: the SPU fallback set-up (D33) */

extern const char* ppu_vfs_root;              /* host dir the PS3 mount points map into */
void     cellfs_add_path_mapping(const char* ps3_prefix, const char* host_path); /* cellFs.c */
void     ps3_host_quit(const char* why);      /* cellSysutil.c: REQUEST_EXITGAME, then exit 0 */
void     cellGame_init_from_paramsfo(const char* sfo_path); /* cellGame.c: the booted PARAM.SFO */

/* sys_ppu_thread.c: the main thread's stack, as sys_ppu_thread_get_stack_information
 * reports it. Left at 0 it names VM_STACK_BASE, the first created thread's stack. */
extern uint32_t g_ppu_main_stack_addr;
extern uint32_t g_ppu_main_stack_size;

/* The status the guest handed to sys_process_exit. A title that exits that way
 * never returns through ppu_run, so this is only read on the path where the
 * entry function unwound instead. */
extern int     g_sys_process_exit_called;
extern int32_t g_sys_process_exit_code;

/* Host-provided symbols the runtime and the HLE libraries link against. */
uint8_t* vm_base = nullptr;
extern uint32_t ppu_vm_size;                  /* ppu_loader.cpp: the OOB guard */

/* Guest-callback dispatch. g_ps3_guest_caller is the hook the HLE runtime
 * calls back into recompiled code through -- cellSysutil events and the GCM
 * vblank/flip handlers. ppu_guest_call does the OPD -> dispatch. */
typedef void (*ps3_guest_caller_fn)(uint32_t, uint64_t, uint64_t, uint64_t, uint64_t,
                                    uint64_t, uint64_t, uint64_t, uint64_t);
extern ps3_guest_caller_fn g_ps3_guest_caller;
uint64_t ppu_guest_call(uint32_t, uint64_t, uint64_t, uint64_t, uint64_t,
                        uint64_t, uint64_t, uint64_t, uint64_t);

/* The GCM half of the frame clock. */
void     cellGcmTickVBlank(void);
void     cellGcmTickFlip(void);
int      cellGcm_take_flip_pending(void);
void     cellGcm_rsx_process_fifo(void);      /* drain get -> put */
unsigned cellGcm_flip_request_count(void);
}

/* ---------------------------------------------------------------------------
 * RSX present backend
 * -----------------------------------------------------------------------*/
/* D3D12 on Windows, Metal on Apple, and the null backend's headless software
 * path anywhere else -- the same selection runtime/host/host_posix.c and the
 * toolkit's boot harness make. All three expose the same three entry points,
 * so the frame clock below is backend-agnostic. */
#if defined(_WIN32)
extern "C" int  rsx_d3d12_backend_init(uint32_t w, uint32_t h, const char* title);
extern "C" void rsx_d3d12_backend_present(void);
extern "C" int  rsx_d3d12_backend_pump_messages(void);
#  define rsx_backend_init    rsx_d3d12_backend_init
#  define rsx_backend_present rsx_d3d12_backend_present
#  define rsx_backend_pump    rsx_d3d12_backend_pump_messages
#  define RSX_BACKEND_NAME    "D3D12"
#elif defined(__APPLE__)
extern "C" int  rsx_metal_backend_init(uint32_t w, uint32_t h, const char* title);
extern "C" void rsx_metal_backend_present(void);
extern "C" int  rsx_metal_backend_pump_messages(void);
#  define rsx_backend_init    rsx_metal_backend_init
#  define rsx_backend_present rsx_metal_backend_present
#  define rsx_backend_pump    rsx_metal_backend_pump_messages
#  define RSX_BACKEND_NAME    "Metal"
#else
extern "C" int  rsx_null_backend_init(uint32_t w, uint32_t h, const char* title);
extern "C" void rsx_null_backend_present(void);
extern "C" int  rsx_null_backend_pump_messages(void);
#  define rsx_backend_init    rsx_null_backend_init
#  define rsx_backend_present rsx_null_backend_present
#  define rsx_backend_pump    rsx_null_backend_pump_messages
#  define RSX_BACKEND_NAME    "null (headless software)"
#endif

/* ---------------------------------------------------------------------------
 * Configuration
 * -----------------------------------------------------------------------*/
/* The flat VM must span every region the PS3 memory map uses, not just the
 * game image: sys_ppu_thread_create puts thread stacks at 0xD0000000, so a
 * smaller arena makes every spawned thread's stack access out of bounds. */
#define VM_SIZE       0x100010000ull   /* the full 32-bit guest space + a 64K guard */
#define STACK_TOP     0x0FF00000u      /* main-thread stack, below the 0x10000000 segment */
#define STACK_SIZE    0x00100000u      /* what the main thread is told it has */
#define WINDOW_WIDTH  1280
#define WINDOW_HEIGHT 720

/* ---------------------------------------------------------------------------
 * Frame clock
 * -----------------------------------------------------------------------*/
/* On real hardware the RSX raises a vblank interrupt about 60 times a second
 * and that is what drives the game's frame loop. With no RSX it is synthesized
 * here: a host thread calls cellGcmTickVBlank/TickFlip, which invoke the
 * handlers the guest registered, and drains the GCM FIFO. Without this the
 * title initialises, registers its handlers and then waits forever.
 *
 * The ticks are driven off real elapsed time rather than off how long present()
 * took. A hidden or occluded window makes present block hard, and pacing the
 * ticks behind it paces the whole game behind it. */
static volatile LONG g_frames_presented = 0;

/* Frames handed to the backend at a guest FLIP boundary -- one per frame the
 * guest actually finished. The presents made before the guest's first flip, so
 * a fresh window is not left blank through a long boot, carry no guest frame
 * and are deliberately not counted. */
extern "C" unsigned ppu_boot_frames_presented(void)
{
    return (unsigned)g_frames_presented;
}

static void present_guest_frame(void)
{
    rsx_backend_present();
    /* This thread increments and guest threads read, so interlocked rather
     * than a volatile ++, which on arm64 is neither atomic nor a fence. */
    InterlockedIncrement(&g_frames_presented);
}

static DWORD WINAPI frame_clock(LPVOID)
{
    const char* title = getenv("PS3_TITLE");
    if (!title || !*title) title = "Gran Turismo 6";

    int rsx_ok = (rsx_backend_init(WINDOW_WIDTH, WINDOW_HEIGHT, title) == 0);
    fprintf(stderr, "[rsx] %s backend init %s\n", RSX_BACKEND_NAME,
            rsx_ok ? "OK -- window open" : "FAILED");

    unsigned  last_flip = 0;
    ULONGLONG next_tick = GetTickCount64();

    for (;;) {
        Sleep(4);
        ULONGLONG now = GetTickCount64();

        int fired = 0;
        while ((long long)(now - next_tick) >= 0 && fired < 240) {
            cellGcmTickVBlank();
            cellGcmTickFlip();
            /* Present a pending flip BEFORE draining any further. The flip
             * fires at a get==put frame boundary on the guest thread, so the
             * batch held right now is exactly the completed frame; presenting
             * after the drain races the guest's next-frame writes and shows a
             * mixed one. */
            if (rsx_ok && cellGcm_take_flip_pending()) {
                present_guest_frame();
                last_flip = cellGcm_flip_request_count();
            }
            /* Drain the FIFO every tick. This is what writes the RSX sync-fence
             * labels the game's per-frame logic blocks on, so it has to keep
             * advancing at 60 Hz even while present() throttles. */
            if (rsx_ok) cellGcm_rsx_process_fifo();
            next_tick += 16;             /* ~60 Hz */
            fired++;
        }
        if (fired >= 240) next_tick = now;   /* fell too far behind -- resync */

        /* Drain at the outer cadence too, not only on the 16 ms tick: titles
         * fence every render pass on a label the drain writes, and one wave of
         * those at 16 ms apiece paces the guest into single-figure frame rates.
         * The real RSX writes them in microseconds. */
        if (rsx_ok) {
            if (cellGcm_take_flip_pending()) {
                present_guest_frame();
                last_flip = cellGcm_flip_request_count();
            }
            cellGcm_rsx_process_fifo();

            if (rsx_backend_pump() != 0) {
                rsx_ok = 0;              /* window closed */
                /* ...so quit, as the console's Quit Game does, instead of
                 * leaving the game running with no window. */
                ps3_host_quit("window closed");
                continue;
            }
            /* Present on a guest flip. A present on a fixed clock can catch the
             * drain mid-frame and flash a partial one. Before the first flip
             * present freely, so the window is not blank during boot. */
            unsigned fc = cellGcm_flip_request_count();
            if (fc != last_flip) {
                present_guest_frame();
                last_flip = fc;
            } else if (fc == 0) {
                rsx_backend_present();
            }
        }
    }
    return 0;
}

/* ---------------------------------------------------------------------------
 * VFS root
 * -----------------------------------------------------------------------*/
/* GT6: the disc layer (the directory holding PS3_GAME) and the update layer (/dev_hdd0)
 * are separate folders of the gt6unpack tree (D14), so the root is not derived from the
 * ELF path as in the template. Defaults come from the configured GT6_TREE; $PS3_VFS_ROOT and
 * $PS3_HDD0_ROOT override. Both are also published in the environment, because the two
 * file layers read them there: ppu_fs.cpp takes PS3_HDD0_ROOT on first use, and cellFs.c
 * seeds its /dev_bdvd mapping from PS3_VFS_ROOT (third_party/ps3recomp/docs/CELLFS_VFS_ROOT.md).
 * This runs before anything touches either layer.
 *
 * /dev_hdd0 defaults to <tree>/play/dev_hdd0, a clone of the verified tree carrying the 1.22
 * EBOOT's on-disk effects, made by scripts/prepare_play.py (D31, D32). The verified tree is
 * never run: EMAIN's first run changes thousands of files there. */
static char s_hdd0_mapping[1024];
static char s_hdd1_root[1100];
static char s_hdd1_mapping[1110];

static bool configure_vfs_roots(void)
{
    const char* bdvd = getenv("PS3_VFS_ROOT");
    if (!bdvd || !*bdvd) { setenv("PS3_VFS_ROOT", GT6_DEFAULT_VFS_ROOT, 1); bdvd = getenv("PS3_VFS_ROOT"); }
    ppu_vfs_root = bdvd;

    const char* hdd0 = getenv("PS3_HDD0_ROOT");
    if (!hdd0 || !*hdd0) { setenv("PS3_HDD0_ROOT", GT6_DEFAULT_HDD0_ROOT, 1); hdd0 = getenv("PS3_HDD0_ROOT"); }
    struct stat st;
    if (stat(hdd0, &st) != 0 || !S_ISDIR(st.st_mode)) {
        fprintf(stderr, "ERROR: no /dev_hdd0 folder at %s: run scripts/prepare_play.py first "
                        "(it makes <tree>/play from the verified tree)\n", hdd0);
        return false;
    }
    /* prepare_play.py writes prepare.json beside dev_hdd0, last, once the EBOOT's effects
     * are applied. Without it the folder is not a prepared play folder, and EMAIN would
     * silently skip the 1.07 data patch (FINDINGS). The same rule holds for an override:
     * $PS3_HDD0_ROOT/../prepare.json must exist. */
    char prep[1100];
    snprintf(prep, sizeof prep, "%s/../prepare.json", hdd0);
    if (stat(prep, &st) != 0 || !S_ISREG(st.st_mode)) {
        fprintf(stderr, "ERROR: %s is not a prepared play folder (no prepare.json beside it): "
                        "run scripts/prepare_play.py first\n", hdd0);
        return false;
    }
    snprintf(s_hdd0_mapping, sizeof s_hdd0_mapping, "%s/", hdd0);
    cellfs_add_path_mapping("/dev_hdd0/", s_hdd0_mapping);

    /* /dev_hdd1, the cache partition GT6's first-run install decodes into (D39): the play
     * folder's dev_hdd1, beside dev_hdd0, made empty here when missing; $PS3_HDD1_ROOT
     * overrides. Both file layers need it. Without it ppu_fs.cpp resolved /dev_hdd1/... into
     * the disc layer (<tree>/dev_bdvd/cache/..., inside the verified tree) while cellFs.c had
     * no mapping at all, so the install's rename of a decoded file failed (ENOENT) and GT6
     * stopped the install with a warning. */
    const char* hdd1 = getenv("PS3_HDD1_ROOT");
    if (!hdd1 || !*hdd1) {
        snprintf(s_hdd1_root, sizeof s_hdd1_root, "%s/../dev_hdd1", hdd0);
        setenv("PS3_HDD1_ROOT", s_hdd1_root, 1);
        hdd1 = getenv("PS3_HDD1_ROOT");
    }
    if (mkdir(hdd1, 0755) != 0 && errno != EEXIST) {
        fprintf(stderr, "ERROR: cannot make the /dev_hdd1 folder %s: %s\n", hdd1, strerror(errno));
        return false;
    }
    if (stat(hdd1, &st) != 0 || !S_ISDIR(st.st_mode)) {
        fprintf(stderr, "ERROR: /dev_hdd1 at %s is not a folder\n", hdd1);
        return false;
    }
    snprintf(s_hdd1_mapping, sizeof s_hdd1_mapping, "%s/", hdd1);
    cellfs_add_path_mapping("/dev_hdd1/", s_hdd1_mapping);
    printf("[boot] /dev_hdd1: %s\n", hdd1);
    return true;
}

/* GT6: the guest command line. The 1.22 EBOOT.BIN spawns EMAIN.SELF with argc 2, argv[0]
 * and argv[1] both its path, and no environment (sceNpDrmProcessExitSpawn2 under RPCS3,
 * FINDINGS "how EMAIN is launched", D31). ps3recomp's ppu_run builds the entry's r3/r4/r5
 * (argc, argv, envp; lv2's layout, as RPCS3's ppu_load_exec does) from $PS3_BOOT_PATH
 * (argv[0]) and $PS3_ARGV (the rest, ';'-separated), with an empty envp. Set both to the
 * contract unless the caller already set them. */
static const char GT6_EMAIN_PATH[] = "/dev_hdd0/game/BCES01977/USRDIR/EMAIN.SELF";

static void configure_guest_argv(void)
{
    setenv("PS3_BOOT_PATH", GT6_EMAIN_PATH, 0);
    setenv("PS3_ARGV", GT6_EMAIN_PATH, 0);
    const char* a0 = getenv("PS3_BOOT_PATH");
    const char* rest = getenv("PS3_ARGV");
    int argc_n = 1;
    if (rest && *rest) { argc_n++; for (const char* c = rest; *c; c++) if (*c == ';') argc_n++; }
    printf("[boot] guest argv: argc=%d %s%s%s; envp empty\n", argc_n, a0,
           (rest && *rest) ? " " : "", (rest && *rest) ? rest : "");
}

/* ---------------------------------------------------------------------------
 * Guest VM
 * -----------------------------------------------------------------------*/
#ifdef _WIN32
/* Demand-paging for the flat VM: reserve the whole 4 GB guest space, which
 * costs no commit, and commit each 64 KB page on first access. Every 32-bit
 * guest offset is then valid, so a garbage guest pointer reads zero instead of
 * killing the process. Faults outside the arena fall through untouched. */
static LONG WINAPI vm_commit_veh(EXCEPTION_POINTERS* ep)
{
    if (ep->ExceptionRecord->ExceptionCode == EXCEPTION_ACCESS_VIOLATION) {
        ULONG_PTR fault = ep->ExceptionRecord->ExceptionInformation[1];
        uintptr_t base  = (uintptr_t)vm_base;
        if (vm_base && fault >= base && fault < base + VM_SIZE) {
            void* page = (void*)(fault & ~(uintptr_t)0xFFFF);
            if (VirtualAlloc(page, 0x10000, MEM_COMMIT, PAGE_READWRITE))
                return EXCEPTION_CONTINUE_EXECUTION;
        }
    }
    return EXCEPTION_CONTINUE_SEARCH;
}
#endif

static bool alloc_guest_vm(void)
{
#ifdef _WIN32
    AddVectoredExceptionHandler(1, vm_commit_veh);
    vm_base = (uint8_t*)VirtualAlloc(NULL, VM_SIZE, MEM_RESERVE, PAGE_READWRITE);
    ppu_vm_size = 0;              /* the whole space is backed; no OOB guard needed */
#else
    /* No vectored exception handlers off Windows, so the arena is mapped up
     * front and lazily backed by the OS: only pages the title touches cost
     * anything. It spans the whole 32-bit space plus the guard, as on Windows.
     * It used to stop below 0xE0000000, but the raw SPU windows (local store
     * and problem-state registers, runtime/spu/spu_raw.c) live from there up.
     * Every load and store a title made into one was reported as an
     * out-of-bounds access and dropped, so a raw SPU was never loaded or
     * started, and sys_raw_spu_create, which clears the registers through
     * vm_base directly, wrote past the end of the mapping. With the whole
     * space backed, ppu_vm_size 0 also gives the loader's bounds check the
     * one-compare fast path Windows already has.
     *
     * mmap, not calloc: vm_commit() hands vm_base + addr to mprotect, which
     * takes page-aligned addresses only. glibc serves an allocation this big
     * from its own mmap chunk and returns a pointer 16 bytes past the page
     * start, so every commit failed with EINVAL and sys_memory_allocate
     * answered ENOMEM to every call. mmap's base is page-aligned and zeroed. */
    void* p = mmap(NULL, VM_SIZE, PROT_READ | PROT_WRITE,
                   MAP_PRIVATE | MAP_ANONYMOUS | MAP_NORESERVE, -1, 0);
    vm_base = (p == MAP_FAILED) ? nullptr : (uint8_t*)p;
    ppu_vm_size = 0;              /* the whole space is backed; no OOB guard needed */
#endif
    return vm_base != nullptr;
}

/* ---------------------------------------------------------------------------
 * Main
 * -----------------------------------------------------------------------*/
static void harness_guest_caller(uint32_t opd, uint64_t a0, uint64_t a1,
                                 uint64_t a2, uint64_t a3, uint64_t a4,
                                 uint64_t a5, uint64_t a6, uint64_t a7)
{
    ppu_guest_call(opd, a0, a1, a2, a3, a4, a5, a6, a7);
}

/* ---------------------------------------------------------------------------
 * Running the guest
 * -----------------------------------------------------------------------*/
#if defined(__APPLE__)
/* AppKit only runs on the process's main thread. The Metal backend creates
 * its window and pumps its events with dispatch_sync onto the main queue
 * when it is called from any other thread, as it is from the frame clock.
 * With the guest on the main thread nothing ever serviced that queue: the
 * frame clock blocked in its first rsx_backend_init, no vblank or flip was
 * ever delivered and the FIFO never drained. A title that waits for a flip
 * hangs there. So the guest runs on a thread of its own, with the same
 * 256 MB host stack every guest thread gets (sys_ppu_thread.c), and the
 * main thread turns the run loop until ppu_run returns. Headless runs never
 * touch the main queue, which is why CI does not see the difference. */
struct guest_run { uint32_t entry, stack_top; int rc; volatile int done; };

static void* guest_thread(void* arg)
{
    guest_run* g = (guest_run*)arg;
    g->rc = ppu_run(g->entry, g->stack_top);
    __atomic_store_n(&g->done, 1, __ATOMIC_RELEASE);
    CFRunLoopStop(CFRunLoopGetMain());
    return nullptr;
}

static int run_guest(uint32_t entry, uint32_t stack_top)
{
    static guest_run g;
    g.entry = entry; g.stack_top = stack_top; g.rc = 0; g.done = 0;
    pthread_attr_t attr;
    pthread_attr_init(&attr);
    pthread_attr_setstacksize(&attr, 256u * 1024u * 1024u);
    pthread_t th;
    int err = pthread_create(&th, &attr, guest_thread, &g);
    pthread_attr_destroy(&attr);
    if (err != 0) {
        fprintf(stderr, "[boot] could not start the guest thread (%d)\n", err);
        return -1;
    }
    /* Short slices: CFRunLoopStop only ends a run that is already going. */
    while (!__atomic_load_n(&g.done, __ATOMIC_ACQUIRE))
        CFRunLoopRunInMode(kCFRunLoopDefaultMode, 0.05, false);
    pthread_join(th, nullptr);
    return g.rc;
}
#else
static int run_guest(uint32_t entry, uint32_t stack_top) { return ppu_run(entry, stack_top); }
#endif

/* GT6: exit-spawn (D41). After its first-run install EMAIN ends its process and has the
 * system start EMAIN.SELF again (sys_game_process_exitspawn2; RPCS3 reference, FINDINGS).
 * The port starts the same native binary again on the same EMAIN.SELF.elf with exec, so the
 * process keeps its pid, stdout and stderr: the new image reads the guest command line from
 * $PS3_BOOT_PATH / $PS3_ARGV, set here from the spawn's argv. A run's per-image outputs (the
 * milestone log, the frame series and the draw statistics) would start again from the
 * beginning and overwrite the first image's, so the new image writes them under
 * spawn<n>/ beside them (frames/spawn<n>/, <milestones>.spawn<n>, <stats>.spawn<n>).
 * No other target is known to the port: for one, the call returns and the process exits. */
extern "C" {
typedef void (*ps3_exitspawn_host_fn)(const char*, const char* const*, const char* const*,
                                      const uint8_t*, uint32_t, int32_t, uint64_t);
void ps3_exitspawn_set_host(ps3_exitspawn_host_fn fn);   /* libs/system/sysGameExitspawn.c */
void rsx_metal_backend_export_window_state(void);        /* libs/video/rsx_metal_backend.m */
}
static const int GT6_EXITSPAWN_MAX = 16;   /* re-executions per process (M5 of the batch 1 review) */
static char  s_self_exe[4096];
static char* s_elf_arg;

static void gt6_exitspawn_output(const char* var, int n, bool dir)
{
    const char* v = getenv(var);
    if (!v || !*v) return;
    /* from the first image's value, so spawn2 lands beside spawn1, not inside it */
    char base[64];
    snprintf(base, sizeof base, "GT6_IMAGE1_%s", var);
    if (!getenv(base)) setenv(base, v, 1);
    char buf[4200];
    snprintf(buf, sizeof buf, dir ? "%s/spawn%d" : "%s.spawn%d", getenv(base), n);
    if (dir) mkdir(buf, 0755);
    setenv(var, buf, 1);
}

/* D44: GT6's first-run install replaces USRDIR/EMAIN.SELF with TPPS-01.22's, so the program
 * a boot or an exit-spawn starts is whichever EMAIN.SELF the play folder holds then. Each port
 * binary is one translated executable (GT6_SELF_SHA256, the SELF its ELF came from);
 * $GT6_IMAGES lists the others the harness knows, "<sha256>=<binary>|<elf>;...". Answers
 * false when this binary is the right one (or nothing better is known), else fills bin/elf. */
static bool gt6_sha256_file(const char* path, char hex[65])
{
#if defined(__APPLE__)
    FILE* f = fopen(path, "rb");
    if (!f) return false;
    CC_SHA256_CTX c;
    CC_SHA256_Init(&c);
    static unsigned char buf[1 << 16];
    size_t n;
    while ((n = fread(buf, 1, sizeof buf, f)) > 0) CC_SHA256_Update(&c, buf, (CC_LONG)n);
    fclose(f);
    unsigned char md[CC_SHA256_DIGEST_LENGTH];
    CC_SHA256_Final(md, &c);
    for (int i = 0; i < CC_SHA256_DIGEST_LENGTH; i++) snprintf(hex + 2 * i, 3, "%02x", md[i]);
    return true;
#else
    (void)path; (void)hex;
    return false;
#endif
}

static bool gt6_other_image(std::string& bin, std::string& elf)
{
    char disk[1200], hex[65];
    snprintf(disk, sizeof disk, "%sgame/BCES01977/USRDIR/EMAIN.SELF", s_hdd0_mapping);
    if (!gt6_sha256_file(disk, hex)) {
        printf("[image] cannot hash %s; staying with this binary\n", disk);
        return false;
    }
    if (strcmp(hex, GT6_SELF_SHA256) == 0) return false;
    const char* list = getenv("GT6_IMAGES");
    std::string all = list ? list : "";
    size_t pos = 0;
    while (pos < all.size()) {
        size_t end = all.find(';', pos);
        if (end == std::string::npos) end = all.size();
        const std::string item = all.substr(pos, end - pos);
        pos = end + 1;
        const size_t eq = item.find('='), bar = item.find('|');
        if (eq == std::string::npos || bar == std::string::npos || bar < eq) continue;
        if (item.compare(0, eq, hex) != 0) continue;
        bin = item.substr(eq + 1, bar - eq - 1);
        elf = item.substr(bar + 1);
        return true;
    }
    printf("[image] the play folder's EMAIN.SELF (sha256 %.16s...) is not this binary's "
           "(%.16s...) and no other build of it is known (GT6_IMAGES); running this one\n",
           hex, GT6_SELF_SHA256);
    return false;
}

static void gt6_exitspawn(const char* path, const char* const* argv, const char* const* envp,
                          const uint8_t* data, uint32_t data_size, int32_t prio, uint64_t flags)
{
    (void)data; (void)prio; (void)flags;
    if (strcmp(path, GT6_EMAIN_PATH) != 0) {
        fprintf(stderr, "[exitspawn] %s is not EMAIN.SELF: the port has no executable for it\n", path);
        return;
    }
    if (envp && envp[0])
        fprintf(stderr, "[exitspawn] the new image gets no envp (ps3recomp starts every image with an empty one)\n");
    if (data_size)
        fprintf(stderr, "[exitspawn] the %u-byte data block is not passed on\n", data_size);
    /* PS3_ARGV is ';'-separated (configure_guest_argv), so an argv entry holding a ';' would
     * be split in two in the new image. GT6 passes only paths, which never hold one. */
    std::string rest;
    for (int i = 1; argv[i]; i++) { if (i > 1) rest += ';'; rest += argv[i]; }
    setenv("PS3_BOOT_PATH", argv[0], 1);
    setenv("PS3_ARGV", rest.c_str(), 1);
    const char* c = getenv("GT6_EXITSPAWN_COUNT");
    const int n = (c ? atoi(c) : 0) + 1;
    /* A title that exit-spawns on every start would re-execute for ever outside the harness
     * (whose --seconds bounds a run). 16 images is far more than GT6's two. */
    if (n > GT6_EXITSPAWN_MAX) {
        fprintf(stderr, "[exitspawn] %d exit-spawns already: refusing another; the process exits\n",
                GT6_EXITSPAWN_MAX);
        return;
    }
    /* Pad presses are per image (D40, D41): image n+1 gets GT6_PAD_SCRIPT_IMAGE<n+1> as its
     * PAD_SCRIPT, or none, so presses meant for one image never replay in the next. */
    {
        char key[48];
        snprintf(key, sizeof key, "GT6_PAD_SCRIPT_IMAGE%d", n + 1);
        const char* ps = getenv(key);
        if (ps && *ps) setenv("PAD_SCRIPT", ps, 1);
        else unsetenv("PAD_SCRIPT");
    }
    char nbuf[16];
    snprintf(nbuf, sizeof nbuf, "%d", n);
    setenv("GT6_EXITSPAWN_COUNT", nbuf, 1);
    gt6_exitspawn_output("PS3_MILESTONE_OUT", n, false);
    gt6_exitspawn_output("PS3RECOMP_DRAW_STATS", n, false);
    gt6_exitspawn_output("PS3RECOMP_METAL_FRAME_DIR", n, true);
    rsx_metal_backend_export_window_state();
    printf("[exitspawn] exec %s %s (image %d; guest argv %s%s%s)\n", s_self_exe, s_elf_arg, n + 1,
           argv[0], rest.empty() ? "" : ";", rest.c_str());
    /* lv2's file writes are unbuffered system calls; the port's guest files are stdio streams
     * (ppu_fs.cpp). Flush every stream so a file the guest still holds open keeps its tail,
     * then keep the guest's descriptors (and any other the process opened) out of the new
     * image: only stdin, stdout and stderr pass through the exec. */
    fflush(NULL);
    {
        const int maxfd = (int)sysconf(_SC_OPEN_MAX);
        for (int fd = 3; fd < (maxfd > 0 && maxfd < 65536 ? maxfd : 4096); fd++) {
            const int fl = fcntl(fd, F_GETFD);
            if (fl >= 0) fcntl(fd, F_SETFD, fl | FD_CLOEXEC);
        }
    }
    /* the executable now on disk, which the first-run install may have replaced (D44) */
    std::string obin = s_self_exe, oelf = s_elf_arg;
    if (gt6_other_image(obin, oelf))
        printf("[exitspawn] the play folder's EMAIN.SELF is another executable: %s %s\n",
               obin.c_str(), oelf.c_str());
    fflush(stdout);
    char* const args[] = { (char*)obin.c_str(), (char*)oelf.c_str(), nullptr };
    execv(obin.c_str(), args);
    fprintf(stderr, "[exitspawn] exec %s failed: %s\n", obin.c_str(), strerror(errno));
}

/* GT6: the PARAM.SFO cellGame answers from (D43). A PS3 with the disc in the drive and the
 * 1.22 update installed boots the update: /dev_hdd0/game/BCES01977/USRDIR/EBOOT.BIN, under
 * the update's PARAM.SFO (CATEGORY "GD", APP_VER 01.22), and so does the EMAIN.SELF it
 * spawns. cellGameBootCheck then reports a disc game with the PATCH attribute, and
 * cellGameGetParamString the update's TITLE_ID / VERSION / APP_VER (RPCS3 does the same for
 * the GD category). Without this cellGame kept its placeholders (title id BLES00000, app
 * version 01.00). Falls back to the disc's PARAM.SFO when the play folder has no update. */
static void configure_game_params(void)
{
    char sfo[1200];
    struct stat st;
    snprintf(sfo, sizeof sfo, "%sgame/BCES01977/PARAM.SFO", s_hdd0_mapping);
    if (stat(sfo, &st) != 0 || !S_ISREG(st.st_mode))
        snprintf(sfo, sizeof sfo, "%s/PS3_GAME/PARAM.SFO", ppu_vfs_root);
    printf("[boot] PARAM.SFO: %s\n", sfo);
    cellGame_init_from_paramsfo(sfo);
}

int main(int argc, char** argv)
{
    if (argc < 2) {
        printf("usage: %s <path to EMAIN.SELF.elf>\n", argv[0]);
        return 2;
    }
    {   /* for an exit-spawn: the binary and the ELF to start again */
#if defined(__APPLE__)
        uint32_t sz = sizeof s_self_exe;
        if (_NSGetExecutablePath(s_self_exe, &sz) != 0)
#endif
            snprintf(s_self_exe, sizeof s_self_exe, "%s", argv[0]);
        s_elf_arg = argv[1];
        ps3_exitspawn_set_host(gt6_exitspawn);
    }

#ifdef _WIN32
#pragma comment(lib, "winmm.lib")
    /* 1 ms timer resolution. The default granularity is about 15.6 ms, which
     * inflates every shorter wait the title makes and throttles the whole
     * thing. POSIX timers are already fine-grained. */
    timeBeginPeriod(1);
    setvbuf(stdout, NULL, _IONBF, 0);   /* unbuffered: do not lose prints on a kill */
#endif

    printf("=== Gran Turismo 6 (ps3recomp runner) ===\n");

    if (!configure_vfs_roots())
        return 1;
    {   /* D44: run the build of the EMAIN.SELF the play folder holds */
        std::string obin, oelf;
        if (!getenv("GT6_IMAGE_SWITCHED") && gt6_other_image(obin, oelf)) {
            setenv("GT6_IMAGE_SWITCHED", "1", 1);
            printf("[image] the play folder's EMAIN.SELF is another executable: exec %s %s\n",
                   obin.c_str(), oelf.c_str());
            fflush(NULL);
            char* const args[] = { (char*)obin.c_str(), (char*)oelf.c_str(), nullptr };
            execv(obin.c_str(), args);
            fprintf(stderr, "[image] exec %s failed: %s; running this one\n", obin.c_str(),
                    strerror(errno));
        }
        unsetenv("GT6_IMAGE_SWITCHED");
        printf("[image] this binary: %s (SELF sha256 %.16s...)\n", GT6_LIFT_ELF_PATH, GT6_SELF_SHA256);
    }
    configure_game_params();
    configure_guest_argv();
    gt6_configure_spurs();

    if (!alloc_guest_vm()) {
        fprintf(stderr, "ERROR: could not allocate the guest address space\n");
        return 1;
    }

    uint32_t entry = ppu_load_elf(argv[1]);
    if (!entry) {
        fprintf(stderr, "ERROR: could not load %s\n", argv[1]);
        return 1;
    }

    printf("[boot] VFS root: %s\n[boot] /dev_hdd0: %s\n", ppu_vfs_root, s_hdd0_mapping);

    ppu_recomp_register();   /* lifted function table -> address map */
    ps3_load_prx_modules();  /* this game's lifted system PRX, if it has any */
    ppu_hle_init();          /* firmware import NID -> HLE handlers */
    ppu_sysprx_register();   /* boot-critical CRT */
    ppu_fs_register();       /* cellFs over the game directory */
    lv2_init_syscalls();     /* the lv2 syscall table */

    /* Install the guest-callback hook, then start the frame clock. It no-ops
     * until the title registers its vblank and flip handlers during init. */
    g_ps3_guest_caller = harness_guest_caller;
    CreateThread(NULL, 4u * 1024 * 1024, frame_clock, NULL, 0, NULL);

    printf("\n[boot] dispatching entry OPD 0x%08X (stack top 0x%08X)\n\n",
           entry, STACK_TOP);

    /* A title that reads its own stack bounds (to find data its parent left
     * below the top, say) gets the stack it really runs on. */
    g_ppu_main_stack_addr = STACK_TOP - STACK_SIZE;
    g_ppu_main_stack_size = STACK_SIZE;

    int rc = run_guest(entry, STACK_TOP);
    printf("\n[boot] ppu_run returned %d (entry function unwound)\n", rc);

    /* A title that called sys_process_exit never reaches this line: that path
     * ends in the host exit(). Getting here means the entry function returned
     * instead, so hand back the status the guest published if it published
     * one. Returning a hardcoded 0 would report success for a run that never
     * got anywhere. */
    return g_sys_process_exit_called ? (int)g_sys_process_exit_code : 0;
}
