"""跨平台安全服务停止脚本。

按端口定位并优雅终止正在运行的 9000 (VirtualBrowser), 8000 (FPBrowser2API), 40001~40005 (SSH WARP 代理桥) 进程及其子进程树。
优先保护外部正在运行的系统代理工具（如 proxy app / Clash / v2ray 等）。
"""

import sys
import time
import psutil

ALL_SERVICE_PORTS = (9000, 8000, 40001, 40002, 40003, 40004, 40005)


def kill_proc_tree(proc: psutil.Process) -> None:
    """递归终止进程及其所有子进程"""
    try:
        children = proc.children(recursive=True)
        for child in children:
            try:
                child.terminate()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        gone, alive = psutil.wait_procs(children, timeout=2)
        for p in alive:
            try:
                p.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        proc.terminate()
        proc.wait(timeout=2)
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass
    except psutil.TimeoutExpired:
        try:
            proc.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass


def stop_port_listeners(ports=ALL_SERVICE_PORTS) -> int:
    """按监听端口寻找并停止服务进程"""
    stopped_count = 0
    killed_pids = set()

    for conn in psutil.net_connections(kind="inet"):
        if conn.status == psutil.CONN_LISTEN and conn.laddr:
            port = conn.laddr.port
            if port in ports and conn.pid:
                pid = conn.pid
                if pid in killed_pids or pid == 0:
                    continue
                try:
                    proc = psutil.Process(pid)
                    pname = proc.name().lower()

                    # 保护常用系统代理/梯子进程，避免误杀
                    if any(x in pname for x in ("clash", "sing-box", "v2ray", "xray", "nekoray", "shadowsocks")):
                        continue

                    print(f"[*] 正在关闭端口 {port} 的服务进程: {proc.name()} [PID: {pid}]...")
                    kill_proc_tree(proc)
                    killed_pids.add(pid)
                    stopped_count += 1
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
                except Exception as e:
                    print(f"[!] 关闭 PID={pid} 失败: {e}")

    # 清理 mihomo 代理进程
    for p in psutil.process_iter(["pid", "name"]):
        try:
            if "mihomo" in p.info["name"].lower():
                print(f"[*] 正在关闭代理进程: {p.info['name']} [PID: {p.info['pid']}]...")
                kill_proc_tree(p)
                stopped_count += 1
        except Exception:
            pass

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
