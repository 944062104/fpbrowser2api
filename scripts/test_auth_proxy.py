import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('192.129.200.213', port=22, username='root', password='p6L02UcboJiaK6RQ39')

cmd = 'docker exec 1Panel-sub2api-rOYX curl -s -x socks5://zqmjj:zqmjj123@172.18.0.1:40001 https://cloudflare.com/cdn-cgi/trace'
stdin, stdout, stderr = ssh.exec_command(cmd)
print("WARP TRACE:")
print(stdout.read().decode('utf-8', errors='ignore'))

ssh.close()
