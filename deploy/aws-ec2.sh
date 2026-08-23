#!/usr/bin/env bash
# Sunrise backend -> AWS EC2 free tier (t2.micro, us-east-1)
# Everything runs on one instance via Docker Compose; frontend stays on Cloudflare Pages.
set -euo pipefail

REGION="us-east-1"
INSTANCE_TYPE="t4g.small"         # free-tier eligible: 2 vCPU ARM, 1GB... actually 2GB RAM
KEY_NAME="sunrise-deploy-key"
SG_NAME="sunrise-sg"
VOLUME_GB=20                      # under the 30GB free EBS allowance
REPO_URL="https://github.com/devbulchandani/sunrise.git"

echo "==> resolving latest Ubuntu 22.04 AMI"
AMI=$(aws ec2 describe-images --region $REGION --owners 099720109477 \
  --filters "Name=name,Values=ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-arm64-server-*" "Name=state,Values=available" \
  --query 'sort_by(Images,&CreationDate)[-1].ImageId' --output text)

echo "==> creating key pair"
PEM_PATH="$(dirname "$0")/$KEY_NAME.pem"
rm -f "$PEM_PATH"
aws ec2 delete-key-pair --region $REGION --key-name $KEY_NAME 2>/dev/null || true
aws ec2 create-key-pair --region $REGION --key-name $KEY_NAME \
  --query 'KeyMaterial' --output text > "$PEM_PATH"
chmod 400 "$PEM_PATH"

echo "==> creating security group"
SG_ID=$(aws ec2 describe-security-groups --region $REGION \
  --group-names $SG_NAME --query 'SecurityGroups[0].GroupId' --output text 2>/dev/null || true)
if [ -z "$SG_ID" ] || [ "$SG_ID" == "None" ]; then
  SG_ID=$(aws ec2 create-security-group --region $REGION --group-name $SG_NAME \
    --description "Sunrise backend" --query 'GroupId' --output text)
  aws ec2 authorize-security-group-ingress --region $REGION --group-id $SG_ID \
    --protocol tcp --port 22 --cidr 0.0.0.0/0
  aws ec2 authorize-security-group-ingress --region $REGION --group-id $SG_ID \
    --protocol tcp --port 8000 --cidr 0.0.0.0/0
fi

echo "==> launching t2.micro"
INSTANCE_ID=$(aws ec2 run-instances --region $REGION \
  --image-id "$AMI" --instance-type $INSTANCE_TYPE --key-name $KEY_NAME \
  --security-group-ids $SG_ID \
  --block-device-mappings "DeviceName=/dev/sda1,Ebs={VolumeSize=$VOLUME_GB,VolumeType=gp2}" \
  --user-data file://deploy/user-data.sh \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=sunrise-backend}]' \
  --query 'Instances[0].InstanceId' --output text)

echo "==> waiting for instance ($INSTANCE_ID)..."
aws ec2 wait instance-running --region $REGION --instance-ids $INSTANCE_ID
PUBLIC_IP=$(aws ec2 describe-instances --region $REGION --instance-ids $INSTANCE_ID \
  --query 'Reservations[0].Instances[0].PublicIpAddress' --output text)

cat <<EOF

==========================================================
Instance : $INSTANCE_ID  ($INSTANCE_TYPE, free tier)
SSH      : ssh -i ~/$KEY_NAME.pem ubuntu@$PUBLIC_IP
API URL  : http://$PUBLIC_IP:8000  (once booted + seeded)
==========================================================

Next steps (automated by user-data; verify with):
  ssh -i ~/$KEY_NAME.pem ubuntu@$PUBLIC_IP 'docker ps'

If .env wasn't uploaded yet:
  scp -i ~/$KEY_NAME.pem .env ubuntu@$PUBLIC_IP:~/sunrise/.env
  ssh -i ~/$KEY_NAME.pem ubuntu@$PUBLIC_IP 'cd ~/sunrise && sudo docker compose -f docker-compose.aws.yml up -d'
EOF