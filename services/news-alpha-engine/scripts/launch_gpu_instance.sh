#!/bin/bash
# ============================================
# Launch GPU Instance for Training
# ============================================
# This script launches a g5.xlarge spot instance
# for training the News Alpha Engine models.
#
# Prerequisites:
# - AWS CLI configured
# - SSH key pair created
# - Security group with SSH access
#
# Usage:
#   ./scripts/launch_gpu_instance.sh
# ============================================

set -e

# Configuration - EDIT THESE
KEY_NAME="your-key-name"           # Your AWS key pair name
SECURITY_GROUP="sg-xxxxxxxxxx"     # Security group ID with SSH access
SUBNET_ID="subnet-xxxxxxxxxx"      # Your subnet ID (optional)
REGION="eu-west-3"                  # Your AWS region

# Instance configuration
INSTANCE_TYPE="g5.xlarge"
AMI_ID="ami-0c7217cdde317cfec"  # Deep Learning AMI Ubuntu 22.04 (check for latest)

echo "============================================"
echo "Launching GPU Training Instance"
echo "============================================"
echo ""
echo "Instance Type: $INSTANCE_TYPE"
echo "Region: $REGION"
echo ""

# Check AWS CLI
if ! command -v aws &> /dev/null; then
    echo "ERROR: AWS CLI not installed"
    echo "Install with: pip install awscli && aws configure"
    exit 1
fi

# Launch spot instance
echo "Launching spot instance..."

LAUNCH_SPEC=$(cat <<EOF
{
    "ImageId": "$AMI_ID",
    "InstanceType": "$INSTANCE_TYPE",
    "KeyName": "$KEY_NAME",
    "SecurityGroupIds": ["$SECURITY_GROUP"],
    "BlockDeviceMappings": [
        {
            "DeviceName": "/dev/sda1",
            "Ebs": {
                "VolumeSize": 200,
                "VolumeType": "gp3",
                "DeleteOnTermination": true
            }
        }
    ],
    "TagSpecifications": [
        {
            "ResourceType": "instance",
            "Tags": [
                {"Key": "Name", "Value": "news-alpha-training"},
                {"Key": "Project", "Value": "tradeul"}
            ]
        }
    ]
}
EOF
)

# Request spot instance
RESULT=$(aws ec2 run-instances \
    --region $REGION \
    --cli-input-json "$LAUNCH_SPEC" \
    --instance-market-options '{"MarketType":"spot","SpotOptions":{"SpotInstanceType":"one-time"}}' \
    --output json)

INSTANCE_ID=$(echo $RESULT | python3 -c "import sys, json; print(json.load(sys.stdin)['Instances'][0]['InstanceId'])")

echo "Instance ID: $INSTANCE_ID"
echo ""
echo "Waiting for instance to start..."

aws ec2 wait instance-running --instance-ids $INSTANCE_ID --region $REGION

# Get public IP
PUBLIC_IP=$(aws ec2 describe-instances \
    --instance-ids $INSTANCE_ID \
    --region $REGION \
    --query 'Reservations[0].Instances[0].PublicIpAddress' \
    --output text)

echo ""
echo "============================================"
echo "Instance Ready!"
echo "============================================"
echo ""
echo "Instance ID: $INSTANCE_ID"
echo "Public IP: $PUBLIC_IP"
echo ""
echo "Connect with:"
echo "  ssh -i ~/.ssh/${KEY_NAME}.pem ubuntu@${PUBLIC_IP}"
echo ""
echo "Then run:"
echo "  git clone <your-repo> /opt/tradeul"
echo "  cd /opt/tradeul/services/news-alpha-engine"
echo "  chmod +x scripts/setup_gpu_instance.sh"
echo "  ./scripts/setup_gpu_instance.sh"
echo ""
echo "To stop and save money:"
echo "  aws ec2 terminate-instances --instance-ids $INSTANCE_ID --region $REGION"
echo ""

