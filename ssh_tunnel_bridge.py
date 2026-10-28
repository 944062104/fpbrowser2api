"""SSH Tunnel & SOCKS5 Auth Bridge for AI Browser Farm
===================================================
通过 SSH 隧道将远程 VPS (192.129.200.213) 上的 WARP SOCKS5 代理 (带账密认证)
安全映射到本地 127.0.0.1:40001~40005，并向本地 Chromium 提供透明免密代理。

解决的核心痛点：
Chromium 启动参数 --proxy-server=socks5://... 原生不支持账密认证。
本地 Bridge 负责在底层自动完成向远程 GOST 代理注入账号密码握手，
使浏览器完全无感知，无需任何输入弹窗，直接畅享 Cloudflare WARP 出口。
"""

import os
import select
import socket
import sys
import threading
import time
import warnings

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

warnings.filterwarnings("ignore")

try:
    import paramiko
except ImportError:
    print("[Error] 缺少 paramiko 库，请先安装: pip install paramiko")
    sys.exit(1)

# 配置项
SSH_HOST = os.environ.get("WARP_SSH_HOST", "192.129.200.213")
SSH_PORT = int(os.environ.get("WARP_SSH_PORT", "22"))
SSH_USER = os.environ.get("WARP_SSH_USER", "root")
SSH_PASS = os.environ.get("WARP_SSH_PASS", "p6L02UcboJiaK6RQ39")

PROXY_USER = os.environ.get("WARP_PROXY_USER", "zqmjj")
PROXY_PASS = os.environ.get("WARP_PROXY_PASS", "zqmjj123")

PORTS = [40001, 40002, 40003, 40004, 40005]


class SSHTunnelManager:
    """维持 SSH 长连接与自动重连"""

    def __init__(self):
        self._lock = threading.Lock()
        self.client = None
        self.transport = None
        self._running = True

    def get_transport(self, timeout=10):
        with self._lock:
            if self.transport and self.transport.is_active():
                return self.transport

            # 尝试重新连接
            self._reconnect(timeout)
            return self.transport

    def _reconnect(self, timeout=15):
        if self.client:
            try:
                self.client.close()
            except Exception:
                pass
            self.client = None
            self.transport = None

        print(f"[*] 正在建立 SSH 隧道连接: {SSH_USER}@{SSH_HOST}:{SSH_PORT}...")
        last_err = None
        for attempt in range(1, 4):
            try:
                import socks
                s = None
                try:
                    s = socks.socksocket()
                    s.set_proxy(socks.HTTP, "127.0.0.1", 7890)
                    s.settimeout(timeout)
                    s.connect((SSH_HOST, SSH_PORT))
                except Exception:
                    s = None

                client = paramiko.SSHClient()
                client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                if s:
                    client.connect(
                        SSH_HOST,
                        port=SSH_PORT,
                        username=SSH_USER,
                        password=SSH_PASS,
                        sock=s,
                        timeout=timeout,
                        banner_timeout=30,
                    )
                else:
                    client.connect(
                        SSH_HOST,
                        port=SSH_PORT,
                        username=SSH_USER,
                        password=SSH_PASS,
                        timeout=timeout,
                        banner_timeout=45,
                    )
                transport = client.get_transport()
                if transport:
                    transport.set_keepalive(30)
                self.client = client
                self.transport = transport
                print("    SSH 隧道建立成功！")
                return
            except Exception as e:
                last_err = e
                print(f"    [-] SSH 连接尝试 {attempt}/3 失败: {e}")
                time.sleep(2)
        if last_err:
            raise last_err

    def close(self):
        self._running = False
        with self._lock:
            if self.client:
                try:
                    self.client.close()
                except Exception:
                    pass
                self.client = None
                self.transport = None


ssh_manager = SSHTunnelManager()


def pipe_stream(src, dst):
    """双向流转发"""
    try:
        while True:
            data = src.recv(32768)
            if not data:
                break
            dst.sendall(data)
    except Exception:
        pass
    finally:
        try:
            src.close()
        except Exception:
            pass
        try:
            dst.close()
        except Exception:
            pass


def handle_client_connection(client_sock: socket.socket, remote_port: int):
    """处理单个本地客户端/浏览器 SOCKS5 请求并转发至远程"""
    chan = None
    try:
        client_sock.settimeout(15)

        # 1. 读取浏览器/客户端 SOCKS5 握手问候 (Greeting)
        greeting = client_sock.recv(256)
        if not greeting or greeting[0] != 0x05:
            client_sock.close()
            return

        # 本地直接回应: 0x05 0x00 (No Authentication Required，无需认证)
        client_sock.sendall(b"\x05\x00")

        # 2. 读取客户端连接请求 (Connect Request)
        client_req = client_sock.recv(1024)
        if not client_req or client_req[0] != 0x05:
            client_sock.close()
            return

        # 3. 获取 SSH Transport 并打开直通 channel
        transport = ssh_manager.get_transport()
        if not transport or not transport.is_active():
            # 回复连接失败
            client_sock.sendall(b"\x05\x01\x00\x01\x00\x00\x00\x00\x00\x00")
            client_sock.close()
            return

        chan = transport.open_channel("direct-tcpip", ("127.0.0.1", remote_port), ("127.0.0.1", 0))
        if chan is None:
            client_sock.sendall(b"\x05\x05\x00\x01\x00\x00\x00\x00\x00\x00")
            client_sock.close()
            return

        chan.settimeout(15)

        # 4. 向远程 SOCKS5 发起认证协商 (RFC 1928 / RFC 1929)
        chan.sendall(b"\x05\x01\x02")  # 支持 Username/Password 认证
        method_resp = chan.recv(2)
        if method_resp != b"\x05\x02":
            client_sock.sendall(b"\x05\x01\x00\x01\x00\x00\x00\x00\x00\x00")
            client_sock.close()
            chan.close()
            return

        # 发送远程账密
        auth_bytes = (
            bytes([1, len(PROXY_USER)])
            + PROXY_USER.encode()
            + bytes([len(PROXY_PASS)])
            + PROXY_PASS.encode()
        )
        chan.sendall(auth_bytes)
        auth_resp = chan.recv(2)
        if auth_resp != b"\x01\x00":
            client_sock.sendall(b"\x05\x01\x00\x01\x00\x00\x00\x00\x00\x00")
            client_sock.close()
            chan.close()
            return

        # 5. 将客户端目标连接请求发送给远程 SOCKS5
        chan.sendall(client_req)

        # 读取远程 SOCKS5 的连接响应
        remote_resp = chan.recv(1024)
        if not remote_resp:
            client_sock.close()
            chan.close()
            return

        # 将远程响应原样回传给本地客户端
        client_sock.sendall(remote_resp)

        if remote_resp[1] != 0x00:
            # 连接失败，关闭通道
            client_sock.close()
            chan.close()
            return

        # 6. 进入全双工双向透明传输
        client_sock.settimeout(None)
        chan.settimeout(None)
        t1 = threading.Thread(target=pipe_stream, args=(client_sock, chan), daemon=True)
        t2 = threading.Thread(target=pipe_stream, args=(chan, client_sock), daemon=True)
        t1.start()
        t2.start()

    except Exception:
        try:
            client_sock.close()
        except Exception:
            pass
        if chan is not None:
            try:
                chan.close()
            except Exception:
                pass


def run_port_listener(port: int):
    """单端口监听器"""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        server.bind(("127.0.0.1", port))
    except Exception as e:
        print(f"[!] 绑定端口 127.0.0.1:{port} 失败: {e}")
        return

    server.listen(100)
    print(f"    [+] 端口 127.0.0.1:{port} 代理桥已就绪 -> 映射远程 WARP :{port}")

    while True:
        try:
            client_sock, _ = server.accept()
            threading.Thread(
                target=handle_client_connection,
                args=(client_sock, port),
                daemon=True,
            ).start()
        except Exception:
            time.sleep(0.1)


def start_all_bridges():
    """启动全部 5 个端口的代理转发"""
    print("=" * 65)
    print("   🌐 启动 SSH 隧道 & 透明 SOCKS5 代理桥")
    print(f"   [*] 远程主机: {SSH_HOST}:{SSH_PORT}")
    print(f"   [*] 映射端口: {PORTS}")
    print("=" * 65)

    # 1. 立即启动本地监听线程 (毫秒级就绪，避免外部启动器阻塞)
    threads = []
    for port in PORTS:
        t = threading.Thread(target=run_port_listener, args=(port,), daemon=True)
        t.start()
        threads.append(t)

    # 2. 异步建立 SSH 隧道长连接
    threading.Thread(target=ssh_manager.get_transport, daemon=True).start()

    print("=" * 65)
    print("   ✅ 全部 5 个 WARP 端口桥接已启动并处于监听状态！")
    print("=" * 65)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[*] 正在关闭代理桥...")
        ssh_manager.close()


def test_proxies():
    """测试本地 5 个端口的连通性"""
    import subprocess

    print("\n🔍 正在测试本地 40001~40005 端口代理连通性...")
    all_ok = True
    for p in PORTS:
        try:
            res = subprocess.run(
                ["curl.exe", "-s", "-x", f"socks5h://127.0.0.1:{p}", "https://api.ipify.org", "--max-time", "8"],
                capture_output=True,
                text=True,
            )
            ip = res.stdout.strip()
            if ip:
                print(f"   ✅ 端口 {p}: 出口 IP -> {ip}")
            else:
                print(f"   ❌ 端口 {p}: 失败 -> {res.stderr.strip()}")
                all_ok = False
        except Exception as e:
            print(f"   ❌ 端口 {p}: 异常 -> {e}")
            all_ok = False
    return all_ok


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        test_proxies()
    else:
        start_all_bridges()
