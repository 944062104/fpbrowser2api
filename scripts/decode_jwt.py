import paramiko
import json
import base64

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('192.129.200.213', port=22, username='root', password='p6L02UcboJiaK6RQ39')

cmd = 'docker exec 1Panel-sub2api-rOYX sh -c "PGPASSWORD=sub2api_bjs6WT psql -h postgresql -U sub2api -d sub2api -t -A -c \\"SELECT credentials FROM accounts WHERE id = 1;\\""'
stdin, stdout, stderr = ssh.exec_command(cmd)
creds_str = stdout.read().decode('utf-8', errors='ignore').strip()
creds = json.loads(creds_str)

token = creds.get('access_token', '')
parts = token.split('.')
if len(parts) >= 2:
    payload = parts[1]
    # pad base64
    payload += '=' * (-len(payload) % 4)
    data = json.loads(base64.urlsafe_b64decode(payload.encode()))
    print("JWT PAYLOAD:")
    for k, v in data.items():
        if k != 'https://api.openai.com/auth':
            print(f"  {k}: {v}")
        else:
            print(f"  {k}: {v}")

ssh.close()
