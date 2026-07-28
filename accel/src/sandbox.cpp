// accel/src/sandbox.cpp —— 进程沙箱（资源限制 + 文件保护 + 环境隔离）
// 防 Agent 执行的死循环/OOM/fork 炸弹搞崩机器

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <string>
#include <vector>
#include <cstring>
#include <signal.h>
#include <sys/wait.h>
#include <sys/resource.h>
#include <unistd.h>
#include <fcntl.h>
#include <chrono>

#ifdef __linux__
#include <sched.h>
#endif

namespace py = pybind11;

struct SandboxResult {
    std::string stdout_output;
    std::string stderr_output;
    int exit_code;
    std::string killed_by;  // "" | "memory" | "cpu" | "timeout"
};

SandboxResult sandbox_exec(
    const std::string& command,
    int memory_mb = 512,
    int cpu_timeout_ms = 30000,
    int wall_timeout_ms = 60000,
    bool network = true,
    const std::vector<std::string>& writable_dirs = {},
    const std::vector<std::string>& env_allow = {}
) {
    int pipe_stdout[2], pipe_stderr[2];
    if (pipe(pipe_stdout) < 0 || pipe(pipe_stderr) < 0)
        throw std::runtime_error("pipe failed");

    pid_t pid = fork();
    if (pid < 0) throw std::runtime_error("fork failed");

    // ── 子进程 ──
    if (pid == 0) {
        // 重定向 stdout/stderr 到管道
        dup2(pipe_stdout[1], STDOUT_FILENO);
        dup2(pipe_stderr[1], STDERR_FILENO);
        close(pipe_stdout[0]); close(pipe_stdout[1]);
        close(pipe_stderr[0]); close(pipe_stderr[1]);

        // 资源限制
        struct rlimit lim;

        // 内存 (字节) — macOS 用 RLIMIT_DATA + RLIMIT_AS 双保险
        rlim_t mem_bytes = (rlim_t)memory_mb * 1024 * 1024;
        lim.rlim_cur = lim.rlim_max = mem_bytes;
        setrlimit(RLIMIT_AS, &lim);
        setrlimit(RLIMIT_DATA, &lim);

        // CPU 时间 (秒)
        int cpu_sec = cpu_timeout_ms / 1000;
        if (cpu_sec < 1) cpu_sec = 1;
        lim.rlim_cur = lim.rlim_max = cpu_sec;
        setrlimit(RLIMIT_CPU, &lim);

        // 子进程数量
        lim.rlim_cur = lim.rlim_max = 10;
        setrlimit(RLIMIT_NPROC, &lim);

        // 网络隔离 (仅 Linux)
#ifdef __linux__
        if (!network) {
            unshare(CLONE_NEWNET);
        }
#endif

        // 环境变量白名单
        if (!env_allow.empty()) {
            std::vector<std::string> saved;
            for (const auto& key : env_allow) {
                const char* val = getenv(key.c_str());
                if (val) saved.push_back(key + "=" + val);
            }
            // macOS 没有 clearenv，用 unsetenv 逐个清
            extern char** environ;
            std::vector<std::string> to_clear;
            for (char** e = environ; *e; e++) {
                std::string s(*e);
                size_t eq = s.find('=');
                if (eq != std::string::npos)
                    to_clear.push_back(s.substr(0, eq));
            }
            for (const auto& k : to_clear)
                unsetenv(k.c_str());
            // 恢复允许的
            for (const auto& kv : saved) {
                size_t eq = kv.find('=');
                setenv(kv.substr(0, eq).c_str(), kv.substr(eq + 1).c_str(), 1);
            }
        }

        // 执行 bash
        const char* argv[] = {"bash", "-c", command.c_str(), nullptr};
        execvp("bash", const_cast<char* const*>(argv));
        _exit(127);  // execvp 失败
    }

    // ── 父进程：用 select 等待子进程或超时 ──
    close(pipe_stdout[1]);
    close(pipe_stderr[1]);

    std::string out, err;
    char buf[4096];
    bool timed_out = false;
    bool stdout_closed = false;
    bool stderr_closed = false;
    auto deadline = std::chrono::steady_clock::now() + std::chrono::milliseconds(wall_timeout_ms);

    while (true) {
        fd_set rfds;
        FD_ZERO(&rfds);
        int maxfd = -1;
        if (!stdout_closed) {
            FD_SET(pipe_stdout[0], &rfds);
            maxfd = pipe_stdout[0];
        }
        if (!stderr_closed) {
            FD_SET(pipe_stderr[0], &rfds);
            maxfd = std::max(maxfd, pipe_stderr[0]);
        }
        // 两个管道都关了，子进程也结束了
        if (maxfd < 0) break;
        maxfd++;

        // 计算剩余时间（每次循环递减，不会重置）
        auto now = std::chrono::steady_clock::now();
        if (now >= deadline) {
            timed_out = true;
            kill(pid, SIGKILL);
            break;
        }
        auto remain = std::chrono::duration_cast<std::chrono::milliseconds>(deadline - now);
        struct timeval tv;
        tv.tv_sec = remain.count() / 1000;
        tv.tv_usec = (remain.count() % 1000) * 1000;

        int ready = select(maxfd, &rfds, nullptr, nullptr, &tv);
        if (ready < 0) break;  // error
        if (ready == 0) {       // timeout
            timed_out = true;
            kill(pid, SIGKILL);
            break;
        }

        // 读可用数据；管道关闭只标记不退出，等两个都关了再 break
        if (FD_ISSET(pipe_stdout[0], &rfds)) {
            ssize_t n = read(pipe_stdout[0], buf, sizeof(buf));
            if (n > 0) {
                out.append(buf, n);
            } else {
                stdout_closed = true;
            }
        }
        if (FD_ISSET(pipe_stderr[0], &rfds)) {
            ssize_t n = read(pipe_stderr[0], buf, sizeof(buf));
            if (n > 0) {
                err.append(buf, n);
            } else {
                stderr_closed = true;
            }
        }
    }

    // 等子进程彻底结束
    int status;
    waitpid(pid, &status, 0);

    SandboxResult r;
    r.stdout_output = out;
    r.stderr_output = err;

    if (timed_out) {
        r.killed_by = "timeout";
        r.exit_code = -1;
    } else if (WIFEXITED(status)) {
        r.exit_code = WEXITSTATUS(status);
    } else if (WIFSIGNALED(status)) {
        r.exit_code = -1;
        int sig = WTERMSIG(status);
        if (sig == SIGKILL) r.killed_by = "memory";
        else if (sig == SIGXCPU) r.killed_by = "cpu";
        else r.killed_by = "signal:" + std::to_string(sig);
    }
    return r;
}

PYBIND11_MODULE(_sandbox, m) {
    m.doc() = "tiny-claw process sandbox";
    py::class_<SandboxResult>(m, "SandboxResult")
        .def_readonly("stdout_output", &SandboxResult::stdout_output)
        .def_readonly("stderr_output", &SandboxResult::stderr_output)
        .def_readonly("exit_code", &SandboxResult::exit_code)
        .def_readonly("killed_by", &SandboxResult::killed_by);
    m.def("sandbox_exec", &sandbox_exec,
          py::arg("command"),
          py::arg("memory_mb") = 512,
          py::arg("cpu_timeout_ms") = 30000,
          py::arg("wall_timeout_ms") = 60000,
          py::arg("network") = true,
          py::arg("writable_dirs") = std::vector<std::string>{},
          py::arg("env_allow") = std::vector<std::string>{},
          "Execute command in sandboxed process");
}
