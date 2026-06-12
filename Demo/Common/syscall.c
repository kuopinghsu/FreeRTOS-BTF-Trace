#include <errno.h>
#include <fcntl.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/types.h>

#ifndef __caddr_t_defined
typedef char *caddr_t;
#define __caddr_t_defined 1
#endif

extern char __heap_start;
extern char __heap_end;

/* Symbols used by the simulator to discover HTIF mailboxes. */
volatile uint64_t tohost __attribute__((section(".htif"), aligned(64), used));
volatile uint64_t fromhost __attribute__((section(".htif"), aligned(64), used));

enum {
    HTIF_DEV_SYSCALL = 0,
    HTIF_DEV_CONSOLE = 1,
    HTIF_SYS_GETCWD = 17,
    HTIF_SYS_FCNTL = 25,
    HTIF_SYS_MKDIRAT = 34,
    HTIF_SYS_UNLINKAT = 35,
    HTIF_SYS_LINKAT = 37,
    HTIF_SYS_RENAMEAT = 38,
    HTIF_SYS_FACCESSAT = 48,
    HTIF_SYS_CHDIR = 49,
    HTIF_SYS_OPENAT = 56,
    HTIF_SYS_CLOSE = 57,
    HTIF_SYS_LSEEK = 62,
    HTIF_SYS_READ = 63,
    HTIF_SYS_WRITE = 64,
    HTIF_SYS_PREAD = 67,
    HTIF_SYS_PWRITE = 68,
    HTIF_SYS_READLINKAT = 78,
    HTIF_SYS_FSTATAT = 79,
    HTIF_SYS_FSTAT = 80,
    HTIF_SYS_EXIT = 93,
    HTIF_SYS_GETMAINVARS = 2011,
    HTIF_CONSOLE_GETC = 0,
    HTIF_CONSOLE_PUTC = 1,
    HTIF_AT_FDCWD = -100
};

struct riscv_stat {
    uint64_t dev;
    uint64_t ino;
    uint32_t mode;
    uint32_t nlink;
    uint32_t uid;
    uint32_t gid;
    uint64_t rdev;
    uint64_t pad1;
    uint64_t size;
    uint32_t blksize;
    uint32_t pad2;
    uint64_t blocks;
    uint64_t atime;
    uint64_t pad3;
    uint64_t mtime;
    uint64_t pad4;
    uint64_t ctime;
    uint64_t pad5;
    uint32_t unused4;
    uint32_t unused5;
};

static inline uint64_t htif_make_cmd(uint8_t dev, uint8_t cmd, uint64_t payload) {
    return ((uint64_t)dev << 56) | ((uint64_t)cmd << 48) | (payload & 0x0000FFFFFFFFFFFFull);
}

static uint64_t htif_exchange(uint64_t cmd) {
    while (tohost != 0) {
    }
    tohost = cmd;

    while (fromhost == 0) {
    }

    uint64_t response = fromhost;
    fromhost = 0;
    return response;
}

static int htif_console_getc(void) {
    uint64_t rsp = htif_exchange(htif_make_cmd(HTIF_DEV_CONSOLE, HTIF_CONSOLE_GETC, 0));
    return (int)(rsp & 0xFFu);
}

static void htif_console_putc(char ch) {
    (void)htif_exchange(htif_make_cmd(HTIF_DEV_CONSOLE, HTIF_CONSOLE_PUTC, (uint8_t)ch));
}

static int64_t htif_syscall(uint64_t no,
                            uint64_t a1,
                            uint64_t a2,
                            uint64_t a3,
                            uint64_t a4,
                            uint64_t a5,
                            uint64_t a6,
                            uint64_t a7) {
    volatile uint64_t magic[8];
    magic[0] = no;
    magic[1] = a1;
    magic[2] = a2;
    magic[3] = a3;
    magic[4] = a4;
    magic[5] = a5;
    magic[6] = a6;
    magic[7] = a7;

    uint64_t payload = (uint64_t)(uintptr_t)&magic[0];
    (void)htif_exchange(htif_make_cmd(HTIF_DEV_SYSCALL, 0, payload));
    return (int64_t)magic[0];
}

static int htif_result_to_errno(int64_t rc) {
    if (rc < 0) {
        errno = (int)-rc;
        return -1;
    }
    return (int)rc;
}

static ssize_t htif_result_to_ssize(int64_t rc) {
    if (rc < 0) {
        errno = (int)-rc;
        return -1;
    }
    return (ssize_t)rc;
}

static off_t htif_result_to_off(int64_t rc) {
    if (rc < 0) {
        errno = (int)-rc;
        return (off_t)-1;
    }
    return (off_t)rc;
}

caddr_t _sbrk(int incr) {
    static char *heap = &__heap_start;
    char *prev_heap = heap;

    if ((incr > 0 && (heap + incr) > &__heap_end) ||
        (incr < 0 && (heap + incr) < &__heap_start)) {
        errno = ENOMEM;
        return (caddr_t)-1;
    }

    heap += incr;
    return (caddr_t)prev_heap;
}

int _open(const char *path, int flags, int mode) {
    size_t len = strlen(path);
    int64_t rc = htif_syscall(HTIF_SYS_OPENAT,
                              (uint64_t)(int64_t)HTIF_AT_FDCWD,
                              (uint64_t)(uintptr_t)path,
                              (uint64_t)len,
                              (uint64_t)(uint32_t)flags,
                              (uint64_t)(uint32_t)mode,
                              0,
                              0);
    return htif_result_to_errno(rc);
}

int _close(int fd) {
    int64_t rc = htif_syscall(HTIF_SYS_CLOSE, (uint64_t)(uint32_t)fd, 0, 0, 0, 0, 0, 0);
    return htif_result_to_errno(rc);
}

ssize_t _read(int fd, void *buf, size_t len) {
    if (fd == 0) {
        char *cbuf = (char *)buf;
        size_t i;
        for (i = 0; i < len; ++i) {
            int ch = htif_console_getc();
            if (ch == 0) {
                break;
            }
            cbuf[i] = (char)ch;
            if (ch == '\n') {
                ++i;
                break;
            }
        }
        return (ssize_t)i;
    }

    int64_t rc = htif_syscall(HTIF_SYS_READ,
                              (uint64_t)(uint32_t)fd,
                              (uint64_t)(uintptr_t)buf,
                              (uint64_t)len,
                              0,
                              0,
                              0,
                              0);
    return htif_result_to_ssize(rc);
}

ssize_t _write(int fd, const void *buf, size_t len) {
    if (fd == 1 || fd == 2) {
        const char *cbuf = (const char *)buf;
        size_t i;
        for (i = 0; i < len; ++i) {
            if (cbuf[i] == '\n') {
                htif_console_putc('\r');
            }
            htif_console_putc(cbuf[i]);
        }
        return (ssize_t)len;
    }

    int64_t rc = htif_syscall(HTIF_SYS_WRITE,
                              (uint64_t)(uint32_t)fd,
                              (uint64_t)(uintptr_t)buf,
                              (uint64_t)len,
                              0,
                              0,
                              0,
                              0);
    return htif_result_to_ssize(rc);
}

off_t _lseek(int fd, off_t offset, int whence) {
    int64_t rc = htif_syscall(HTIF_SYS_LSEEK,
                              (uint64_t)(uint32_t)fd,
                              (uint64_t)offset,
                              (uint64_t)(uint32_t)whence,
                              0,
                              0,
                              0,
                              0);
    return htif_result_to_off(rc);
}

int _fstat(int fd, struct stat *st) {
    struct riscv_stat rst;
    int64_t rc = htif_syscall(HTIF_SYS_FSTAT,
                              (uint64_t)(uint32_t)fd,
                              (uint64_t)(uintptr_t)&rst,
                              0,
                              0,
                              0,
                              0,
                              0);
    if (rc < 0) {
        errno = (int)-rc;
        return -1;
    }

    memset(st, 0, sizeof(*st));
    st->st_mode = (mode_t)rst.mode;
    st->st_nlink = (nlink_t)rst.nlink;
    st->st_size = (off_t)rst.size;
    st->st_blksize = rst.blksize;
    st->st_blocks = rst.blocks;
    st->st_atime = rst.atime;
    st->st_mtime = rst.mtime;
    st->st_ctime = rst.ctime;
    return 0;
}

int _stat(const char *path, struct stat *st) {
    struct riscv_stat rst;
    size_t len = strlen(path);
    int64_t rc = htif_syscall(HTIF_SYS_FSTATAT,
                              (uint64_t)(int64_t)HTIF_AT_FDCWD,
                              (uint64_t)(uintptr_t)path,
                              (uint64_t)len,
                              (uint64_t)(uintptr_t)&rst,
                              0,
                              0,
                              0);
    if (rc < 0) {
        errno = (int)-rc;
        return -1;
    }

    memset(st, 0, sizeof(*st));
    st->st_mode = (mode_t)rst.mode;
    st->st_nlink = (nlink_t)rst.nlink;
    st->st_size = (off_t)rst.size;
    st->st_blksize = rst.blksize;
    st->st_blocks = rst.blocks;
    st->st_atime = rst.atime;
    st->st_mtime = rst.mtime;
    st->st_ctime = rst.ctime;
    return 0;
}

int _isatty(int fd) {
    return (fd == 0 || fd == 1 || fd == 2) ? 1 : 0;
}

int _unlink(const char *path) {
    size_t len = strlen(path);
    int64_t rc = htif_syscall(HTIF_SYS_UNLINKAT,
                              (uint64_t)(int64_t)HTIF_AT_FDCWD,
                              (uint64_t)(uintptr_t)path,
                              (uint64_t)len,
                              0,
                              0,
                              0,
                              0);
    return htif_result_to_errno(rc);
}

int _access(const char *path, int mode) {
    size_t len = strlen(path);
    int64_t rc = htif_syscall(HTIF_SYS_FACCESSAT,
                              (uint64_t)(int64_t)HTIF_AT_FDCWD,
                              (uint64_t)(uintptr_t)path,
                              (uint64_t)len,
                              (uint64_t)(uint32_t)mode,
                              0,
                              0,
                              0);
    return htif_result_to_errno(rc);
}

int _kill(int pid, int sig) {
    (void)pid;
    (void)sig;
    errno = ENOSYS;
    return -1;
}

int _getpid(void) {
    return 1;
}

void _exit(int status) {
    uint64_t payload = ((uint64_t)(uint32_t)status << 1) | 1u;
    (void)htif_exchange(htif_make_cmd(HTIF_DEV_SYSCALL, 0, payload));
    for (;;) {
#if defined(__riscv)
        __asm__ volatile("wfi");
#else
        __asm__ volatile("nop");
#endif
    }
}
