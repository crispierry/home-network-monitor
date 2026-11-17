#include <errno.h>
#include <signal.h>
#include <spawn.h>
#include <stdio.h>
#include <sys/wait.h>
#include <unistd.h>

extern char **environ;
static volatile sig_atomic_t child_pid;

static void forward_signal(int signal_number) {
    if (child_pid > 0) kill((pid_t)child_pid, signal_number);
}

int main(int argc, char **argv) {
    if (argc < 2) return 64;
    sigset_t signals, previous;
    sigemptyset(&signals);
    sigaddset(&signals, SIGTERM);
    sigaddset(&signals, SIGINT);
    sigprocmask(SIG_BLOCK, &signals, &previous);
    struct sigaction action = {0};
    action.sa_handler = forward_signal;
    sigemptyset(&action.sa_mask);
    sigaction(SIGTERM, &action, NULL);
    sigaction(SIGINT, &action, NULL);
    posix_spawnattr_t attributes;
    posix_spawnattr_init(&attributes);
    posix_spawnattr_setsigmask(&attributes, &previous);
    posix_spawnattr_setflags(&attributes, POSIX_SPAWN_SETSIGMASK);
    pid_t child;
    int error = posix_spawn(&child, argv[1], NULL, &attributes, argv + 1, environ);
    posix_spawnattr_destroy(&attributes);
    if (error) {
        fprintf(stderr, "Monitor worker could not start: %d\n", error);
        return 71;
    }
    child_pid = child;
    sigprocmask(SIG_SETMASK, &previous, NULL);
    int status;
    while (waitpid(child, &status, 0) < 0) {
        if (errno != EINTR) return 71;
    }
    return WIFEXITED(status) ? WEXITSTATUS(status) : 128 + WTERMSIG(status);
}
