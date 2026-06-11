import subprocess
import os
import time

NO_PROCESS = "NO_PROCESS"
HZ = os.sysconf(os.sysconf_names['SC_CLK_TCK'])
PAGE_SIZE_KB = os.sysconf("SC_PAGE_SIZE") // 1024
MEM_TOTAL_KB = 0
with open("/proc/meminfo") as f:
    for line in f:
        if line.startswith("MemTotal:"):
            MEM_TOTAL_KB = int(line.split()[1])
            break

def get_pids(cmd: str):
    result = subprocess.check_output(["pgrep -f " + cmd], shell=True, universal_newlines=True)
    lines = result.split("\n")
    pids = []
    for line in lines:
        try:
            pids.append(int(line))
        except:
            pass
    return pids

##
# @brief get up and down tree for the pid
def get_tree(pid):
    pid_str = str(pid)
    result = subprocess.check_output(["pstree -s -p " + pid_str], shell=True, universal_newlines=True)
    if result is None:
        result = NO_PROCESS
    if f"({pid_str})" not in result:
        result = NO_PROCESS
    return result

def get_ancestor_pids(pid):
    ancestors = []
    try:
        pid = int(pid)
        while pid > 1:
            ancestors.append(pid)
            status_file = f"/proc/{pid}/status"
            if not os.path.exists(status_file):
                break
            with open(status_file) as f:
                for line in f:
                    if line.startswith("PPid:"):
                        ppid = int(line.split()[1])
                        if ppid == 0 or ppid == pid:
                            return ancestors
                        pid = ppid
                        break
                else:
                    break
        ancestors.append(1)  # include init/systemd
    except Exception as e:
        print(f"Error: {e}")
    return ancestors[::-1]  # return in top-down order

def get_cpu_total():
    with open("/proc/stat") as f:
        parts = f.readline().split()[1:]
        return sum(map(int, parts))

def get_proc_info():
    info = {}
    for pid in filter(str.isdigit, os.listdir("/proc")):
        try:
            with open(f"/proc/{pid}/stat") as f:
                parts = f.read().split()
                utime, stime = int(parts[13]), int(parts[14])
                rss_pages = int(parts[23])
            with open(f"/proc/{pid}/cmdline") as f:
                cmdline = f.read().replace('\x00', ' ').strip()
            if not cmdline:
                with open(f"/proc/{pid}/comm") as f:
                    cmdline = f.read().strip()
            info[int(pid)] = {
                "time": utime + stime,
                "cmd": cmdline,
                "rss_kb": rss_pages * PAGE_SIZE_KB
            }
        except Exception:
            continue
    return info

def get_process_resources(cpu_cut: float = 1.0, mem_cut: float = 1.0):
    cpu_total = get_cpu_total()
    proc_info = get_proc_info()
    cpu_total_last = get_process_resources.cpu_total_last
    proc_info_last = get_process_resources.proc_info_last
    proc_dict_list = []
    if ((cpu_total_last is not None) and (proc_info_last is not None)):
        delta_cpu = cpu_total - cpu_total_last
        for pid in proc_info_last:
            if pid in proc_info:
                delta_proc = proc_info[pid]["time"] - proc_info_last[pid]["time"]
                cpu_pct = 100.0 * delta_proc / delta_cpu * os.cpu_count()
                mem_kb = proc_info[pid]["rss_kb"]
                mem_pct = 100.0 * mem_kb / MEM_TOTAL_KB
                if (cpu_pct >= cpu_cut) or (mem_pct >= mem_cut):
                    # print(f"{pid:>6}  CPU: {cpu_pct:5.1f}%  MEM: {mem_pct:5.1f}%  CMD: {proc_info[pid]['cmd']}")
                    proc_dict_list.append(
                        dict(
                            cpu_percent=float(cpu_pct),
                            mem_mb=float(mem_kb/1000.0),
                            mem_percent=float(mem_pct),
                            name=proc_info[pid]['cmd'],
                            pid=pid
                        )
                    )
    get_process_resources.cpu_total_last = cpu_total
    get_process_resources.proc_info_last = proc_info
    return proc_dict_list

get_process_resources.cpu_total_last = None
get_process_resources.proc_info_last = None

def extract_name_from_cmd(cmd):
    token_walker = 0
    name = "-"
    tokens = cmd.split(" ")
    while (
            (name in ['python', 'python3', 'bash', 'sh'])
            or name.startswith("-")
    ):
        if token_walker >= len(tokens):
            name = tokens[0].split("/")[-1]
            break
        else:
            name = tokens[token_walker].split("/")[-1]
            token_walker += 1
    return name