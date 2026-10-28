import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('192.129.200.213', port=22, username='root', password='p6L02UcboJiaK6RQ39')

for port in [40001, 40002, 40003, 40004, 40005]:
    cmd = f'docker exec 1Panel-sub2api-rOYX curl -s --connect-timeout 5 -x socks5://zqmjj:zqmjj123@172.18.0.1:{port} https://cloudflare.com/cdn-cgi/trace | grep -E "ip=|loc=|warp="'
    stdin, stdout, stderr = ssh.exec_command(cmd)
    res = stdout.read().decode('utf-8', errors='ignore').strip().replace('\n', ', ')
    print(f"Port {port}: {res}")

ssh.close()
