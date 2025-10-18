#!/usr/bin/env python3
"""Bedrock 애플리케이션용 IAM Role 생성 스크립트"""

import boto3
import json

def create_bedrock_roles():
    """Bedrock 애플리케이션용 IAM Role 생성"""

    iam = boto3.client('iam', region_name='us-east-1')
    sts = boto3.client('sts', region_name='us-east-1')

    # 현재 계정 ID 가져오기
    account_id = sts.get_caller_identity()['Account']

    # 애플리케이션 목록
    applications = [
        'AmazonQ-CLI-Role',  # Amazon Q CLI 전용
        'CustomerServiceApp-BedrockRole',
        'DataAnalysisApp-BedrockRole',
        'ChatbotApp-BedrockRole',
        'DocumentProcessorApp-BedrockRole'
    ]

    # 지원 리전 목록
    regions = ['us-east-1', 'us-west-2', 'ap-northeast-1', 'ap-northeast-2', 'ap-southeast-1']

    # Trust Policy
    trust_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {
                    "AWS": f"arn:aws:iam::{account_id}:root"
                },
                "Action": "sts:AssumeRole"
            }
        ]
    }

    # Bedrock 사용 권한 정책 (모든 리전)
    bedrock_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": [
                    "bedrock:InvokeModel",
                    "bedrock:InvokeModelWithResponseStream",
                    "bedrock:ListFoundationModels"
                ],
                "Resource": [f"arn:aws:bedrock:{region}:{account_id}:*" for region in regions] + 
                           [f"arn:aws:bedrock:{region}::foundation-model/*" for region in regions] + ["*"]
            },
            {
                "Effect": "Allow",
                "Action": [
                    "s3:GetObject",
                    "s3:ListBucket"
                ],
                "Resource": [
                    f"arn:aws:s3:::bedrock-analytics-{account_id}-*",
                    f"arn:aws:s3:::bedrock-analytics-{account_id}-*/*",
                    "arn:aws:s3:::bedrock-logs-*",
                    "arn:aws:s3:::bedrock-logs-*/*"
                ]
            }
        ]
    }

    print("=" * 80)
    print("🔧 Creating Bedrock IAM Roles for Multi-Region Support")
    print("=" * 80)
    print(f"\n📝 Account ID: {account_id}")
    print(f"🌍 Supported Regions: {', '.join(regions)}\n")

    created_roles = []

    for app_role in applications:
        try:
            # Role 생성
            print(f"Creating role: {app_role}...")
            response = iam.create_role(
                RoleName=app_role,
                AssumeRolePolicyDocument=json.dumps(trust_policy),
                Description=f"Bedrock role for {app_role.replace('-BedrockRole', '')} application with multi-region support",
                Tags=[
                    {'Key': 'Purpose', 'Value': 'BedrockMultiRegion'},
                    {'Key': 'Application', 'Value': app_role}
                ]
            )

            role_arn = response['Role']['Arn']
            print(f"  ✅ Created: {role_arn}")

            # Inline policy 추가
            policy_name = f"{app_role}-MultiRegionPolicy"
            iam.put_role_policy(
                RoleName=app_role,
                PolicyName=policy_name,
                PolicyDocument=json.dumps(bedrock_policy)
            )
            print(f"  ✅ Added multi-region policy: {policy_name}")
            print(f"  🌍 Regions: {', '.join(regions)}")
            print(f"  📁 S3 Access: bedrock-analytics-{account_id}-*, bedrock-logs-*")

            created_roles.append({
                'name': app_role,
                'arn': role_arn
            })

        except iam.exceptions.EntityAlreadyExistsException:
            print(f"  ⚠️  Role already exists: {app_role}")
            # 기존 Role 업데이트
            try:
                policy_name = f"{app_role}-MultiRegionPolicy"
                iam.put_role_policy(
                    RoleName=app_role,
                    PolicyName=policy_name,
                    PolicyDocument=json.dumps(bedrock_policy)
                )
                print(f"  ✅ Updated policy: {policy_name}")
                
                role = iam.get_role(RoleName=app_role)
                created_roles.append({
                    'name': app_role,
                    'arn': role['Role']['Arn']
                })
            except Exception as e:
                print(f"  ❌ Error updating policy: {e}")

        except Exception as e:
            print(f"  ❌ Error creating role {app_role}: {e}")

    print("\n" + "=" * 80)
    print("📋 Summary")
    print("=" * 80)
    print(f"\nCreated/Updated {len(created_roles)} roles with multi-region support:\n")

    for role in created_roles:
        print(f"  • {role['name']}")
        print(f"    ARN: {role['arn']}")
        print(f"    Regions: {', '.join(regions)}")
        print(f"    S3 Access: bedrock-analytics-{account_id}-*, bedrock-logs-*\n")

    return created_roles


def cleanup_bedrock_roles():
    """Bedrock Role 삭제"""

    iam = boto3.client('iam', region_name='us-east-1')

    applications = [
        'AmazonQ-CLI-Role',  # Amazon Q CLI 전용
        'CustomerServiceApp-BedrockRole',
        'DataAnalysisApp-BedrockRole',
        'ChatbotApp-BedrockRole',
        'DocumentProcessorApp-BedrockRole'
    ]

    print("\n" + "=" * 80)
    print("🗑️  Cleaning up Bedrock IAM Roles")
    print("=" * 80)

    for app_role in applications:
        try:
            # Inline policies 삭제
            policies = iam.list_role_policies(RoleName=app_role)
            for policy_name in policies['PolicyNames']:
                iam.delete_role_policy(RoleName=app_role, PolicyName=policy_name)
                print(f"  Deleted policy: {policy_name} from {app_role}")

            # Role 삭제
            iam.delete_role(RoleName=app_role)
            print(f"  ✅ Deleted role: {app_role}")

        except iam.exceptions.NoSuchEntityException:
            print(f"  ⚠️  Role not found: {app_role}")
        except Exception as e:
            print(f"  ❌ Error deleting {app_role}: {e}")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == 'cleanup':
        cleanup_bedrock_roles()
    else:
        create_bedrock_roles()
        print("\n💡 To cleanup these roles later, run: python setup_bedrock_role.py cleanup")
