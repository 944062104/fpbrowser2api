"""AI 号池双服务跨平台停止器 (VirtualBrowser & FPBrowser2API)
============================================================
基于纯 Python psutil 实现，完全消除操作系统差异 (跨平台通用于 Windows / Linux / macOS)。
按端口精准定位监听服务，安全杀死进程及其所有子孙进程。
"""

import sys
import time

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

try:
    import psutil
except ImportError:
    print("[错误] 缺少 psutil 库，请先安装: pip install psutil")
    sys.exit(1)


def kill_proc_tree(proc: psutil.Process) -> None:
    """递归杀死进程树"""
    try:
        children = proc.children(recursive=True)
        for child in children:
            try:
                child.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        proc.kill()
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass


ALL_SERVICE_PORTS = (9000, 8000, 40001, 40002, 40003, 40004, 40005)


def stop_port_listeners(ports=ALL_SERVICE_PORTS) -> int:
    """按监听端口寻找并停止服务进程"""
    stopped_count = 0
    killed_pids = set()

    try:
        connections = psutil.net_connections(kind="inet")
    except Exception as e:
        # 某些 Linux/macOS 权限受限场景回退
        connections = []
        for p in psutil.process_iter(["pid", "name"]):
            try:
                for c in p.net_connections():
                    connections.append(c)
            except Exception:
                continue

    for conn in connections:
        if conn.status == psutil.CONN_LISTEN and conn.laddr and conn.laddr.port in ports:
            pid = conn.pid
            if pid and pid not in killed_pids:
                try:
                    proc = psutil.Process(pid)
                    pname = proc.name()
                    print(f"[*] 正在关闭端口 {conn.laddr.port} 上的服务: {pname} [PID: {pid}]...")
                    kill_proc_tree(proc)
                    killed_pids.add(pid)
                    stopped_count += 1
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
                except Exception as e:
                    print(f"[!] 关闭 PID={pid} 失败: {e}")

    return stopped_count


def main():
    print("=" * 60)
    print("  🛑 正在停止全套 AI 号池服务 (VB + 网关 + SSH WARP 代理桥)...")
    print("=" * 60)

    count = stop_port_listeners(ports=ALL_SERVICE_PORTS)
    time.sleep(0.5)

    print("=" * 60)
    if count > 0:
        print(f"  ✅ 服务已成功停止 (共处理 {count} 个相关进程)。")
    else:
        print("  ℹ️ 未检测到运行中的相关服务端口 (9000/8000/40001~40005)。")
    print("=" * 60)


if __name__ == "__main__":
    main()
