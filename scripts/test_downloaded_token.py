import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('192.129.200.213', port=22, username='root', password='p6L02UcboJiaK6RQ39')

with open(r'd:\Personal\Downloads\FF261019842540 - 副本.txt', 'r', encoding='utf-8') as f:
    lines = [l.strip() for l in f if l.strip()]

line1 = lines[0]
parts = line1.split('----')
email = parts[0]
token = parts[4]

remote_script = f"""
import urllib.request
import urllib.error
import ssl

proxy_handler = urllib.request.ProxyHandler({{
    'http': 'socks5h://zqmjj:zqmjj123@127.0.0.1:40001',
    'https': 'socks5h://zqmjj:zqmjj123@127.0.0.1:40001'
}})
opener = urllib.request.build_opener(proxy_handler)

token = {repr(token)}

# Test on chatgpt.com/backend-api/models
req = urllib.request.Request(
    'https://chatgpt.com/backend-api/models',
    headers={{'Authorization': f'Bearer {{token}}', 'User-Agent': 'Mozilla/5.0'}}
)
try:
    with opener.open(req, timeout=10) as r:
        print('Models status:', r.status)
        print('Models body:', r.read().decode()[:200])
except Exception as e:
    print('Models error:', e)

# Test on codex/responses
req2 = urllib.request.Request(
    'https://chatgpt.com/backend-api/codex/responses',
    data=b'{{"model":"gpt-4o","input":"test"}}',
    headers={{
        'Authorization': f'Bearer {{token}}',
        'Content-Type': 'application/json',
        'User-Agent': 'OpenAI-Codex/0.163.0'
    }}
)
try:
    with opener.open(req2, timeout=10) as r:
        print('Codex status:', r.status)
except urllib.error.HTTPError as e:
    print('Codex HTTP error:', e.code)
    print('Codex error body:', e.read().decode())
except Exception as e:
    print('Codex other error:', e)
"""

sftp = ssh.open_sftp()
with sftp.open('/tmp/test_downloaded.py', 'w') as f:
    f.write(remote_script)
sftp.close()

stdin, stdout, stderr = ssh.exec_command('python3 /tmp/test_downloaded.py')
print("RESULT:\n", stdout.read().decode('utf-8', errors='ignore'))
print("ERR:\n", stderr.read().decode('utf-8', errors='ignore'))

ssh.close()
