#!/bin/bash
# EC2 user-data: prepare a 1GB t2.micro to run the full Sunrise stack.
set -euxo pipefail

# swap — the free tier only has 1GB RAM
fallocate -l 2G /swapfile
chmod 600 /swapfile
mkswap /swapfile
swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab

# docker + compose plugin (Ubuntu)
apt-get update -y
apt-get install -y ca-certificates curl git
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
  https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" \
  > /etc/apt/sources.list.d/docker.list
apt-get update -y
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

systemctl enable --now docker

# clone the repo; .env is scp'd manually after boot (never baked into images)
cd /home/ubuntu
sudo -u ubuntu git clone https://github.com/devbulchandani/sunrise.git || true
cd sunrise
if [ -f ../.env ]; then cp ../.env .; fi

echo "user-data complete" > /var/log/sunrise-user-data.log
