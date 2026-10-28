import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('192.129.200.213', port=22, username='root', password='p6L02UcboJiaK6RQ39')

sql = """
-- Update proxy 16 to 20 with proper host and auth
UPDATE proxies SET host = '172.18.0.1', port = 40001, username = 'zqmjj', password = 'zqmjj123', status = 'active' WHERE id = 16;
UPDATE proxies SET host = '172.18.0.1', port = 40002, username = 'zqmjj', password = 'zqmjj123', status = 'active' WHERE id = 17;
UPDATE proxies SET host = '172.18.0.1', port = 40003, username = 'zqmjj', password = 'zqmjj123', status = 'active' WHERE id = 18;
UPDATE proxies SET host = '172.18.0.1', port = 40004, username = 'zqmjj', password = 'zqmjj123', status = 'active' WHERE id = 19;
UPDATE proxies SET host = '172.18.0.1', port = 40005, username = 'zqmjj', password = 'zqmjj123', status = 'active' WHERE id = 20;

-- Bind accounts 1-10 to proxies 16-20
UPDATE accounts SET proxy_id = 16, status = 'active', schedulable = true, error_message = '' WHERE id = 1;
UPDATE accounts SET proxy_id = 17, status = 'active', schedulable = true, error_message = '' WHERE id = 2;
UPDATE accounts SET proxy_id = 18, status = 'active', schedulable = true, error_message = '' WHERE id = 3;
UPDATE accounts SET proxy_id = 19, status = 'active', schedulable = true, error_message = '' WHERE id = 4;
UPDATE accounts SET proxy_id = 20, status = 'active', schedulable = true, error_message = '' WHERE id = 5;
UPDATE accounts SET proxy_id = 16, status = 'active', schedulable = true, error_message = '' WHERE id = 6;
UPDATE accounts SET proxy_id = 17, status = 'active', schedulable = true, error_message = '' WHERE id = 7;
UPDATE accounts SET proxy_id = 18, status = 'active', schedulable = true, error_message = '' WHERE id = 8;
UPDATE accounts SET proxy_id = 19, status = 'active', schedulable = true, error_message = '' WHERE id = 9;
UPDATE accounts SET proxy_id = 20, status = 'active', schedulable = true, error_message = '' WHERE id = 10;

SELECT a.id, a.name, a.proxy_id, p.port, p.username, a.status, a.schedulable 
FROM accounts a 
JOIN proxies p ON a.proxy_id = p.id 
ORDER BY a.id;
"""

sftp = ssh.open_sftp()
with sftp.open('/tmp/update_proxies.sql', 'w') as f:
    f.write(sql)
sftp.close()

cmd = "docker exec -i 1Panel-postgresql-UlLX psql -U sub2api -d sub2api < /tmp/update_proxies.sql"
stdin, stdout, stderr = ssh.exec_command(cmd)
print("RESULT:\n", stdout.read().decode('utf-8', errors='ignore'))
print("ERR:\n", stderr.read().decode('utf-8', errors='ignore'))

ssh.close()
