#!/bin/bash
set -e

cat > /etc/systemd/system/meshcore-backup.service << 'EOF'
[Unit]
Description=MeshCore Dashboard DB Backup

[Service]
Type=oneshot
ExecStart=/bin/bash -c 'sqlite3 /opt/meshcore-dashboard/data/meshcore.db ".backup /mnt/backup/meshcore-$(date +%%Y%%m%%d).db"'
EOF

cat > /etc/systemd/system/meshcore-backup.timer << 'EOF'
[Unit]
Description=Daily MeshCore DB backup

[Timer]
OnCalendar=*-*-* 03:00:00 UTC
Persistent=true

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable meshcore-backup.timer
echo "Backup timer installed (daily at 03:00 UTC)"
echo "Ensure /mnt/backup is a bind mount from Proxmox host"
