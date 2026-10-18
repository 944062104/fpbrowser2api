"""AI 号池双服务跨平台一键启动器 (VirtualBrowser + FPBrowser2API)
============================================================
基于纯 Python 实现，零平台依赖 (通用于 Windows / Linux / macOS)。
按顺序检测并异步拉起双端服务，提供统一运行日志与管理链接。
"""

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


def is_port_listening(port: int, host: str = "127.0.0.1") -> bool:
    """检查指定端口是否已处于监听状态"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0


def get_python_exe() -> str:
    """获取当前或优先的 Python 解释器路径"""
    if os.environ.get("VB_PY"):
        return os.environ["VB_PY"]
    conda_py = Path(r"D:\Program Files\anaconda3\python.exe")
    if conda_py.is_file():
        return str(conda_py)
    return sys.executable


def main():
    root_dir = Path(__file__).parent.resolve()
    vb_server_dir = (root_dir.parent / "VirtualBrowser" / "api_server").resolve()
    py_exe = get_python_exe()

    print("=" * 65)
    print("   🚀 启动 AI号池双服务 (VirtualBrowser + FPBrowser2API)")
    print(f"   [*] 运行平台: {sys.platform}")
    print(f"   [*] Python 路径: {py_exe}")
    print("=" * 65)

    # 1. 启动 VirtualBrowser API (端口 9000)
    print("\n[1/2] 检查 VirtualBrowser API 服务 (端口: 9000)...")
    if is_port_listening(9000):
        print("   ✅ VirtualBrowser API 服务已在运行 (端口 9000)")
    else:
        server_py = vb_server_dir / "server.py"
        if server_py.is_file():
            print("   ▶️ 正在启动 VirtualBrowser API 服务...")
            popen_kwargs: dict = {"cwd": str(vb_server_dir)}
            if sys.platform == "win32":
                # CREATE_NO_WINDOW (0x08000000) 配合 CREATE_NEW_PROCESS_GROUP 保证无黑框常驻
                popen_kwargs["creationflags"] = 0x08000000 | subprocess.CREATE_NEW_PROCESS_GROUP
            else:
                popen_kwargs["preexec_fn"] = os.setsid
            subprocess.Popen([py_exe, "server.py"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **popen_kwargs)
        else:
            print(f"   ⚠️ 未在 {vb_server_dir} 找到 server.py，跳过启动。")

    # 等待 9000 就绪
    for _ in range(25):
        if is_port_listening(9000):
            break
        time.sleep(0.3)

    # 2. 启动 FPBrowser2API 调度网关 (端口 8000)
    print("\n[2/2] 检查 FPBrowser2API 调度网关 (端口: 8000)...")
    if is_port_listening(8000):
        print("   ✅ FPBrowser2API 网关已在运行 (端口 8000)")
    else:
        main_py = root_dir / "main.py"
        if main_py.is_file():
            print("   ▶️ 正在启动 FPBrowser2API 网关...")
            popen_kwargs = {"cwd": str(root_dir)}
            if sys.platform == "win32":
                popen_kwargs["creationflags"] = 0x08000000 | subprocess.CREATE_NEW_PROCESS_GROUP
            else:
                popen_kwargs["preexec_fn"] = os.setsid
            subprocess.Popen([py_exe, "main.py"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **popen_kwargs)
        else:
            print(f"   ⚠️ 未在 {root_dir} 找到 main.py，跳过启动。")

    # 等待 8000 就绪
    for _ in range(20):
        if is_port_listening(8000):
            break
        time.sleep(0.3)

    print("\n" + "=" * 65)
    print("   🎉 AI号池双服务启动就绪！")
    print("   - VirtualBrowser API: http://127.0.0.1:9000")
    print("   - FPBrowser2API 网关: http://127.0.0.1:8000")
    print("   - Web 管理后台:       http://127.0.0.1:8000/login")
    print("   提示: 可随时运行 python stop_services.py 一键安全停止双服务。")
    print("=" * 65)


if __name__ == "__main__":
    main()
