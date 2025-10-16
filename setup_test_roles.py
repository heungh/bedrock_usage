#!/usr/bin/env python3
"""테스트용 IAM Role 생성 스크립트"""

import boto3
import json

def create_test_roles():
    """테스트용 애플리케이션 IAM Role 생성"""

    iam = boto3.client('iam', region_name='us-east-1')
    sts = boto3.client('sts', region_name='us-east-1')

    # 현재 계정 ID 가져오기
    account_id = sts.get_caller_identity()['Account']

    # 테스트용 애플리케이션 목록
    applications = [
        'CustomerServiceApp-BedrockRole',
        'DataAnalysisApp-BedrockRole',
        'ChatbotApp-BedrockRole',
        'DocumentProcessorApp-BedrockRole'
    ]

    # Trust Policy - 현재 계정의 모든 principal이 assume 가능
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

    # Bedrock 사용 권한 정책
    bedrock_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": [
                    "bedrock:InvokeModel",
                    "bedrock:InvokeModelWithResponseStream"
                ],
                "Resource": "*"
            }
        ]
    }

    print("=" * 80)
    print("🔧 Creating Test IAM Roles for Bedrock Applications")
    print("=" * 80)
    print(f"\n📝 Account ID: {account_id}\n")

    created_roles = []

    for app_role in applications:
        try:
            # Role 생성
            print(f"Creating role: {app_role}...")
            response = iam.create_role(
                RoleName=app_role,
                AssumeRolePolicyDocument=json.dumps(trust_policy),
                Description=f"Test role for {app_role.replace('-BedrockRole', '')} application",
                Tags=[
                    {'Key': 'Purpose', 'Value': 'BedrockUsageTest'},
                    {'Key': 'Application', 'Value': app_role}
                ]
            )

            role_arn = response['Role']['Arn']
            print(f"  ✅ Created: {role_arn}")

            # Inline policy 추가
            policy_name = f"{app_role}-BedrockPolicy"
            iam.put_role_policy(
                RoleName=app_role,
                PolicyName=policy_name,
                PolicyDocument=json.dumps(bedrock_policy)
            )
            print(f"  ✅ Added Bedrock policy: {policy_name}")

            created_roles.append({
                'name': app_role,
                'arn': role_arn
            })

        except iam.exceptions.EntityAlreadyExistsException:
            print(f"  ⚠️  Role already exists: {app_role}")
            # 기존 Role의 ARN 가져오기
            role = iam.get_role(RoleName=app_role)
            created_roles.append({
                'name': app_role,
                'arn': role['Role']['Arn']
            })

        except Exception as e:
            print(f"  ❌ Error creating role {app_role}: {e}")

    print("\n" + "=" * 80)
    print("📋 Summary")
    print("=" * 80)
    print(f"\nCreated/Verified {len(created_roles)} roles:\n")

    for role in created_roles:
        print(f"  • {role['name']}")
        print(f"    ARN: {role['arn']}\n")

    return created_roles


def cleanup_test_roles():
    """테스트용 Role 삭제"""

    iam = boto3.client('iam', region_name='us-east-1')

    applications = [
        'CustomerServiceApp-BedrockRole',
        'DataAnalysisApp-BedrockRole',
        'ChatbotApp-BedrockRole',
        'DocumentProcessorApp-BedrockRole'
    ]

    print("\n" + "=" * 80)
    print("🗑️  Cleaning up Test IAM Roles")
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
        cleanup_test_roles()
    else:
        create_test_roles()
        print("\n💡 To cleanup these roles later, run: python setup_test_roles.py cleanup")
