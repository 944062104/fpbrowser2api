import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('192.129.200.213', port=22, username='root', password='p6L02UcboJiaK6RQ39')

cmd = """docker exec 1Panel-sub2api-rOYX sh -c 'PGPASSWORD=sub2api_bjs6WT psql -h postgresql -U sub2api -d sub2api -c "SELECT id, name, protocol, host, port, status FROM proxies;"' """
stdin, stdout, stderr = ssh.exec_command(cmd)
print("PROXIES IN DB:")
print(stdout.read().decode())

cmd = """docker inspect 1Panel-sub2api-rOYX --format '{{json .NetworkSettings.Networks}}' """
stdin, stdout, stderr = ssh.exec_command(cmd)
print("SUB2API NETWORKS:")
print(stdout.read().decode())

cmd = """docker inspect warp-1 --format '{{json .NetworkSettings.Networks}}' """
stdin, stdout, stderr = ssh.exec_command(cmd)
print("WARP-1 NETWORKS:")
print(stdout.read().decode())

ssh.close()
