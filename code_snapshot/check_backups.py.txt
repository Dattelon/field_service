import paramiko
import os
from dotenv import load_dotenv

load_dotenv('C:/ProjectF/field-service/control-bot/.env')

SERVER_HOST = os.getenv("SERVER_HOST", "195.230.131.10")
SERVER_USER = os.getenv("SERVER_USER", "root")
SERVER_PASSWORD = os.getenv("SERVER_PASSWORD")

print(f"Connecting to {SERVER_HOST}...")

try:
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(SERVER_HOST, username=SERVER_USER, password=SERVER_PASSWORD, timeout=10)
    
    # Проверяем директории бэкапов
    commands = [
        "ls -lah /opt/backups/ 2>&1",
        "ls -lah /opt/backups/daily/ 2>&1 | head -20",
        "ls -lah /backups/ 2>&1",
        "crontab -l | grep field-service",
        "cat /var/log/field-service-backup.log 2>&1 | tail -30"
    ]
    
    for cmd in commands:
        print(f"\n{'='*60}")
        print(f"Command: {cmd}")
        print('='*60)
        stdin, stdout, stderr = ssh.exec_command(cmd, timeout=10)
        output = stdout.read().decode('utf-8', errors='ignore')
        error = stderr.read().decode('utf-8', errors='ignore')
        print(output + error)
    
    ssh.close()
    print("\n✅ Check completed!")
    
except Exception as e:
    print(f"❌ Error: {e}")
