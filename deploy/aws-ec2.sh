#!/usr/bin/env bash
# Sunrise backend -> AWS EC2 (t4g.small, us-east-1)
#
# Everything runs on one instance via Docker Compose; the dashboard stays on
# Cloudflare Pages and reaches the backend through the Cloudflare Worker.
#
# Access model:
#   - No SSH key pair and no port 22 ingress. Use AWS Systems Manager:
#       aws ssm start-session --target <instance-id> --region us-east-1
#   - Caddy terminates TLS on 80/443 and proxies to the backend over the
#     private compose network. Port 8000 is never published to the internet.
#   - The instance profile must allow SSM plus read access to the app secret.
#
# Usage: PROFILE_NAME=sunrise-backend-ssm-role ./deploy/aws-ec2.sh
set -euo pipefail

REGION="us-east-1"
INSTANCE_TYPE="t4g.small"          # 2 vCPU ARM, 2 GB RAM
SG_NAME="sunrise-backend-public-api"
PROFILE_NAME="${PROFILE_NAME:-sunrise-backend-ssm-role}"
VOLUME_GB=20
REPO_URL="https://github.com/devbulchandani/sunrise.git"

echo "==> resolving latest Ubuntu 22.04 arm64 AMI"
AMI=$(aws ec2 describe-images --region "$REGION" --owners 099720109477 \
  --filters "Name=name,Values=ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-arm64-server-*" "Name=state,Values=available" \
  --query 'sort_by(Images,&CreationDate)[-1].ImageId' --output text)

echo "==> ensuring security group (80/443 only; no SSH, no 8000)"
SG_ID=$(aws ec2 describe-security-groups --region "$REGION" \
  --group-names "$SG_NAME" --query 'SecurityGroups[0].GroupId' --output text 2>/dev/null || true)
if [ -z "$SG_ID" ] || [ "$SG_ID" = "None" ]; then
  SG_ID=$(aws ec2 create-security-group --region "$REGION" --group-name "$SG_NAME" \
    --description "Sunrise API behind Caddy TLS" --query 'GroupId' --output text)
fi
for port in 80 443; do
  aws ec2 authorize-security-group-ingress --region "$REGION" --group-id "$SG_ID" \
    --protocol tcp --port "$port" --cidr 0.0.0.0/0 2>/dev/null || true
  aws ec2 authorize-security-group-ingress --region "$REGION" --group-id "$SG_ID" \
    --ip-permissions "IpProtocol=tcp,FromPort=$port,ToPort=$port,Ipv6Ranges=[{CidrIpv6=::/0}]" 2>/dev/null || true
done

echo "==> launching instance (no SSH key pair)"
INSTANCE_ID=$(aws ec2 run-instances --region "$REGION" \
  --image-id "$AMI" --instance-type "$INSTANCE_TYPE" \
  --security-group-ids "$SG_ID" \
  --iam-instance-profile "Name=$PROFILE_NAME" \
  --block-device-mappings "DeviceName=/dev/sda1,Ebs={VolumeSize=$VOLUME_GB,VolumeType=gp3,Encrypted=true}" \
  --user-data file://deploy/user-data.sh \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=sunrise-backend}]' \
  --query 'Instances[0].InstanceId' --output text)

echo "==> waiting for instance ($INSTANCE_ID)..."
aws ec2 wait instance-running --region "$REGION" --instance-ids "$INSTANCE_ID"
PUBLIC_IP=$(aws ec2 describe-instances --region "$REGION" --instance-ids "$INSTANCE_ID" \
  --query 'Reservations[0].Instances[0].PublicIpAddress' --output text)

cat <<EOF

==========================================================
Instance : $INSTANCE_ID  ($INSTANCE_TYPE)
Public IP: $PUBLIC_IP
SSM      : aws ssm start-session --target $INSTANCE_ID --region $REGION
API      : https://$PUBLIC_IP.sslip.io  (Caddy obtains a certificate on boot)
==========================================================

Next steps:
  1. Store runtime settings in Secrets Manager (sunrise/production/app-env).
  2. Open an SSM session and run:
       cd /home/ubuntu/sunrise
       git pull
       docker compose -f docker-compose.aws.yml up -d --build
  3. Point the Cloudflare Worker origin at https://$PUBLIC_IP.sslip.io
EOF
