import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('192.129.200.213', port=22, username='root', password='p6L02UcboJiaK6RQ39')

cmd = 'docker inspect warp-1 --format "{{json .Config.Env}}"'
stdin, stdout, stderr = ssh.exec_command(cmd)
print("WARP-1 ENV:")
print(stdout.read().decode())

cmd = 'docker logs --tail 20 warp-1'
stdin, stdout, stderr = ssh.exec_command(cmd)
print("WARP-1 LOGS:")
print(stdout.read().decode())

ssh.close()
