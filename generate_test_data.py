#!/usr/bin/env python3
"""테스트 데이터 생성 - 여러 애플리케이션으로 Bedrock API 호출"""

import boto3
import json
import time
from botocore.config import Config
from datetime import datetime

# 계정 ID
ACCOUNT_ID = "181136804328"

# 테스트 시나리오 정의
TEST_SCENARIOS = [
    # IAM Role 기반 애플리케이션들
    {
        'type': 'role',
        'name': 'CustomerServiceApp-BedrockRole',
        'role_arn': f'arn:aws:iam::{ACCOUNT_ID}:role/CustomerServiceApp-BedrockRole',
        'region': 'us-east-1',
        'model': 'us.anthropic.claude-3-haiku-20240307-v1:0',
        'calls': 3,
        'prompt': '고객 문의에 대한 답변을 작성해주세요: 배송이 지연되고 있습니다.'
    },
    {
        'type': 'role',
        'name': 'DataAnalysisApp-BedrockRole',
        'role_arn': f'arn:aws:iam::{ACCOUNT_ID}:role/DataAnalysisApp-BedrockRole',
        'region': 'us-east-1',
        'model': 'us.anthropic.claude-sonnet-4-5-20250929-v1:0',
        'calls': 2,
        'prompt': '다음 데이터를 분석하고 인사이트를 제공해주세요: [1,2,3,4,5]'
    },
    {
        'type': 'role',
        'name': 'ChatbotApp-BedrockRole',
        'role_arn': f'arn:aws:iam::{ACCOUNT_ID}:role/ChatbotApp-BedrockRole',
        'region': 'us-east-1',
        'model': 'us.anthropic.claude-3-haiku-20240307-v1:0',
        'calls': 5,
        'prompt': '안녕하세요! 오늘 날씨가 어떤가요?'
    },
    {
        'type': 'role',
        'name': 'DocumentProcessorApp-BedrockRole',
        'role_arn': f'arn:aws:iam::{ACCOUNT_ID}:role/DocumentProcessorApp-BedrockRole',
        'region': 'us-west-2',
        'model': 'us.anthropic.claude-sonnet-4-5-20250929-v1:0',
        'calls': 2,
        'prompt': '이 문서를 요약해주세요: AWS는 클라우드 컴퓨팅 서비스를 제공합니다.'
    },

    # UserAgent 기반 애플리케이션들
    {
        'type': 'useragent',
        'name': 'MobileApp',
        'user_agent': 'MobileApp/2.1.0',
        'region': 'us-east-1',
        'model': 'us.anthropic.claude-3-haiku-20240307-v1:0',
        'calls': 4,
        'prompt': '모바일 앱에서 질문합니다: 계정 설정은 어디에 있나요?'
    },
    {
        'type': 'useragent',
        'name': 'WebPortal',
        'user_agent': 'WebPortal/1.5.3',
        'region': 'us-east-1',
        'model': 'us.anthropic.claude-sonnet-4-5-20250929-v1:0',
        'calls': 3,
        'prompt': '웹 포털에서 질문합니다: 대시보드를 어떻게 사용하나요?'
    },
    {
        'type': 'useragent',
        'name': 'BackendAPI',
        'user_agent': 'BackendAPI/3.0.0',
        'region': 'us-west-2',
        'model': 'us.anthropic.claude-3-haiku-20240307-v1:0',
        'calls': 2,
        'prompt': 'API 백엔드에서 호출: 사용자 데이터를 처리하는 방법은?'
    }
]


def call_bedrock_with_role(scenario):
    """IAM Role을 assume하고 Bedrock API 호출"""

    print(f"\n🔐 Testing: {scenario['name']} (IAM Role)")
    print(f"   Role ARN: {scenario['role_arn']}")
    print(f"   Region: {scenario['region']}")
    print(f"   Model: {scenario['model']}")
    print(f"   Calls: {scenario['calls']}")

    try:
        # STS로 Role assume
        sts_client = boto3.client('sts', region_name='us-east-1')
        assumed_role = sts_client.assume_role(
            RoleArn=scenario['role_arn'],
            RoleSessionName=f"{scenario['name']}-test-session"
        )

        # Assumed role credentials로 Bedrock 클라이언트 생성
        bedrock = boto3.client(
            'bedrock-runtime',
            region_name=scenario['region'],
            aws_access_key_id=assumed_role['Credentials']['AccessKeyId'],
            aws_secret_access_key=assumed_role['Credentials']['SecretAccessKey'],
            aws_session_token=assumed_role['Credentials']['SessionToken']
        )

        success_count = 0
        for i in range(scenario['calls']):
            try:
                # Bedrock API 호출
                response = bedrock.invoke_model(
                    modelId=scenario['model'],
                    body=json.dumps({
                        "anthropic_version": "bedrock-2023-05-31",
                        "max_tokens": 200,
                        "messages": [
                            {
                                "role": "user",
                                "content": scenario['prompt']
                            }
                        ]
                    })
                )

                success_count += 1
                print(f"   ✅ Call {i+1}/{scenario['calls']} succeeded")

                # API rate limit을 고려한 짧은 대기
                time.sleep(0.5)

            except Exception as e:
                print(f"   ❌ Call {i+1}/{scenario['calls']} failed: {e}")

        print(f"   📊 Result: {success_count}/{scenario['calls']} calls succeeded")
        return success_count

    except Exception as e:
        print(f"   ❌ Error: {e}")
        return 0


def call_bedrock_with_useragent(scenario):
    """UserAgent를 설정하고 Bedrock API 호출"""

    print(f"\n🌐 Testing: {scenario['name']} (UserAgent)")
    print(f"   User Agent: {scenario['user_agent']}")
    print(f"   Region: {scenario['region']}")
    print(f"   Model: {scenario['model']}")
    print(f"   Calls: {scenario['calls']}")

    try:
        # UserAgent 설정
        config = Config(
            user_agent_extra=scenario['user_agent']
        )

        bedrock = boto3.client(
            'bedrock-runtime',
            region_name=scenario['region'],
            config=config
        )

        success_count = 0
        for i in range(scenario['calls']):
            try:
                # Bedrock API 호출
                response = bedrock.invoke_model(
                    modelId=scenario['model'],
                    body=json.dumps({
                        "anthropic_version": "bedrock-2023-05-31",
                        "max_tokens": 200,
                        "messages": [
                            {
                                "role": "user",
                                "content": scenario['prompt']
                            }
                        ]
                    })
                )

                success_count += 1
                print(f"   ✅ Call {i+1}/{scenario['calls']} succeeded")

                # API rate limit을 고려한 짧은 대기
                time.sleep(0.5)

            except Exception as e:
                print(f"   ❌ Call {i+1}/{scenario['calls']} failed: {e}")

        print(f"   📊 Result: {success_count}/{scenario['calls']} calls succeeded")
        return success_count

    except Exception as e:
        print(f"   ❌ Error: {e}")
        return 0


def main():
    print("=" * 80)
    print("🧪 Bedrock Application Test Data Generator")
    print("=" * 80)
    print(f"\n⏰ Start Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"📝 Total Scenarios: {len(TEST_SCENARIOS)}")

    role_scenarios = [s for s in TEST_SCENARIOS if s['type'] == 'role']
    ua_scenarios = [s for s in TEST_SCENARIOS if s['type'] == 'useragent']

    print(f"   • IAM Role-based: {len(role_scenarios)}")
    print(f"   • UserAgent-based: {len(ua_scenarios)}")

    results = {
        'total_scenarios': len(TEST_SCENARIOS),
        'successful_scenarios': 0,
        'total_calls': sum(s['calls'] for s in TEST_SCENARIOS),
        'successful_calls': 0
    }

    # IAM Role 기반 테스트
    print("\n" + "=" * 80)
    print("Part 1: IAM Role-based Applications")
    print("=" * 80)

    for scenario in role_scenarios:
        success_count = call_bedrock_with_role(scenario)
        if success_count > 0:
            results['successful_scenarios'] += 1
            results['successful_calls'] += success_count

    # UserAgent 기반 테스트
    print("\n" + "=" * 80)
    print("Part 2: UserAgent-based Applications")
    print("=" * 80)

    for scenario in ua_scenarios:
        success_count = call_bedrock_with_useragent(scenario)
        if success_count > 0:
            results['successful_scenarios'] += 1
            results['successful_calls'] += success_count

    # 결과 요약
    print("\n" + "=" * 80)
    print("📊 Test Summary")
    print("=" * 80)
    print(f"\n✅ Successful Scenarios: {results['successful_scenarios']}/{results['total_scenarios']}")
    print(f"✅ Successful API Calls: {results['successful_calls']}/{results['total_calls']}")
    print(f"\n⏰ End Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    print("\n" + "=" * 80)
    print("💡 Next Steps")
    print("=" * 80)
    print("\n1. Wait 2-3 minutes for CloudTrail events to be indexed")
    print("2. Run the tracker to verify application-level cost analysis:")
    print("   python test_tracker_cli.py")
    print("\n3. Or use Streamlit UI:")
    print("   streamlit run bedrock_tracker.py")
    print("\n4. Check the 'Application Cost Analysis' section")
    print("\n" + "=" * 80)


if __name__ == "__main__":
    main()
