#!/usr/bin/env python3
"""
애플리케이션별 CloudWatch 커스텀 메트릭 전송 예시
"""

import boto3
import json
from datetime import datetime

class BedrockWithMetrics:
    """
    Bedrock API 호출 시 자동으로 CloudWatch 커스텀 메트릭을 전송하는 래퍼 클래스
    """

    def __init__(self, application_name: str, region_name: str = 'us-east-1'):
        """
        Args:
            application_name: 애플리케이션 이름 (예: "CustomerServiceApp", "ChatbotApp")
            region_name: AWS 리전
        """
        self.application_name = application_name
        self.region_name = region_name
        self.bedrock = boto3.client('bedrock-runtime', region_name=region_name)
        self.cloudwatch = boto3.client('cloudwatch', region_name=region_name)

    def invoke_model(self, model_id: str, messages: list, max_tokens: int = 200):
        """
        Bedrock 모델 호출 + CloudWatch 커스텀 메트릭 전송

        Args:
            model_id: 모델 ID
            messages: 메시지 리스트
            max_tokens: 최대 토큰 수

        Returns:
            response: Bedrock API 응답
        """
        # 1. Bedrock API 호출
        response = self.bedrock.invoke_model(
            modelId=model_id,
            body=json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": max_tokens,
                "messages": messages
            })
        )

        # 2. 응답에서 토큰 사용량 추출
        response_body = json.loads(response['body'].read())
        usage = response_body.get('usage', {})
        input_tokens = usage.get('input_tokens', 0)
        output_tokens = usage.get('output_tokens', 0)

        # 3. CloudWatch에 커스텀 메트릭 전송
        self._send_custom_metrics(model_id, input_tokens, output_tokens)

        return response_body, usage

    def _send_custom_metrics(self, model_id: str, input_tokens: int, output_tokens: int):
        """CloudWatch에 커스텀 메트릭 전송"""
        try:
            timestamp = datetime.utcnow()

            # 애플리케이션별 메트릭 전송
            self.cloudwatch.put_metric_data(
                Namespace='Custom/BedrockUsage',  # 커스텀 네임스페이스
                MetricData=[
                    {
                        'MetricName': 'InputTokenCount',
                        'Dimensions': [
                            {'Name': 'Application', 'Value': self.application_name},  # 애플리케이션 차원 추가!
                            {'Name': 'ModelId', 'Value': model_id},
                            {'Name': 'Region', 'Value': self.region_name}
                        ],
                        'Value': input_tokens,
                        'Unit': 'Count',
                        'Timestamp': timestamp
                    },
                    {
                        'MetricName': 'OutputTokenCount',
                        'Dimensions': [
                            {'Name': 'Application', 'Value': self.application_name},
                            {'Name': 'ModelId', 'Value': model_id},
                            {'Name': 'Region', 'Value': self.region_name}
                        ],
                        'Value': output_tokens,
                        'Unit': 'Count',
                        'Timestamp': timestamp
                    },
                    {
                        'MetricName': 'APICallCount',
                        'Dimensions': [
                            {'Name': 'Application', 'Value': self.application_name},
                            {'Name': 'ModelId', 'Value': model_id}
                        ],
                        'Value': 1,
                        'Unit': 'Count',
                        'Timestamp': timestamp
                    }
                ]
            )
            print(f"✅ Metrics sent to CloudWatch for {self.application_name}")
        except Exception as e:
            print(f"⚠️  Failed to send metrics: {e}")


# ============================================================================
# 사용 예시
# ============================================================================

def example_customer_service_app():
    """고객 서비스 앱 예시"""
    print("=" * 80)
    print("Example: Customer Service App")
    print("=" * 80)

    # 1. BedrockWithMetrics 인스턴스 생성 (애플리케이션 이름 지정)
    bedrock_client = BedrockWithMetrics(
        application_name='CustomerServiceApp',
        region_name='us-east-1'
    )

    # 2. 모델 호출 (자동으로 CloudWatch에 메트릭 전송됨)
    response, usage = bedrock_client.invoke_model(
        model_id='us.anthropic.claude-3-haiku-20240307-v1:0',
        messages=[
            {"role": "user", "content": "고객 문의에 답변해주세요: 배송이 지연되고 있습니다."}
        ]
    )

    print(f"\n📊 Usage:")
    print(f"  Input tokens: {usage['input_tokens']}")
    print(f"  Output tokens: {usage['output_tokens']}")
    print(f"\n💬 Response: {response['content'][0]['text'][:100]}...")


def example_chatbot_app():
    """챗봇 앱 예시"""
    print("\n" + "=" * 80)
    print("Example: Chatbot App")
    print("=" * 80)

    # 다른 애플리케이션 이름으로 인스턴스 생성
    bedrock_client = BedrockWithMetrics(
        application_name='ChatbotApp',
        region_name='us-east-1'
    )

    response, usage = bedrock_client.invoke_model(
        model_id='us.anthropic.claude-3-haiku-20240307-v1:0',
        messages=[
            {"role": "user", "content": "안녕하세요!"}
        ]
    )

    print(f"\n📊 Usage:")
    print(f"  Input tokens: {usage['input_tokens']}")
    print(f"  Output tokens: {usage['output_tokens']}")
    print(f"\n💬 Response: {response['content'][0]['text'][:100]}...")


def query_custom_metrics():
    """CloudWatch에서 커스텀 메트릭 조회"""
    print("\n" + "=" * 80)
    print("Querying Custom Metrics from CloudWatch")
    print("=" * 80)

    cloudwatch = boto3.client('cloudwatch', region_name='us-east-1')

    # 애플리케이션별 토큰 사용량 조회
    applications = ['CustomerServiceApp', 'ChatbotApp']

    for app in applications:
        try:
            # Input 토큰 조회
            response = cloudwatch.get_metric_statistics(
                Namespace='Custom/BedrockUsage',
                MetricName='InputTokenCount',
                Dimensions=[
                    {'Name': 'Application', 'Value': app}
                ],
                StartTime=datetime.utcnow().replace(hour=0, minute=0, second=0),
                EndTime=datetime.utcnow(),
                Period=3600,
                Statistics=['Sum']
            )

            input_sum = sum([point['Sum'] for point in response['Datapoints']])

            # Output 토큰 조회
            response = cloudwatch.get_metric_statistics(
                Namespace='Custom/BedrockUsage',
                MetricName='OutputTokenCount',
                Dimensions=[
                    {'Name': 'Application', 'Value': app}
                ],
                StartTime=datetime.utcnow().replace(hour=0, minute=0, second=0),
                EndTime=datetime.utcnow(),
                Period=3600,
                Statistics=['Sum']
            )

            output_sum = sum([point['Sum'] for point in response['Datapoints']])

            print(f"\n📊 {app}:")
            print(f"  Input tokens: {int(input_sum):,}")
            print(f"  Output tokens: {int(output_sum):,}")

        except Exception as e:
            print(f"⚠️  Error querying {app}: {e}")


if __name__ == "__main__":
    print("=" * 80)
    print("🎯 Bedrock with CloudWatch Custom Metrics Example")
    print("=" * 80)
    print("\n이 예시는 애플리케이션별로 CloudWatch 커스텀 메트릭을 전송합니다.")
    print("CloudWatch 콘솔에서 'Custom/BedrockUsage' 네임스페이스를 확인하세요.\n")

    # 1. 여러 애플리케이션에서 API 호출
    example_customer_service_app()
    example_chatbot_app()

    # 2. 메트릭이 CloudWatch에 도착할 때까지 대기
    print("\n" + "=" * 80)
    print("⏳ Waiting for metrics to be available in CloudWatch (10 seconds)...")
    print("=" * 80)
    import time
    time.sleep(10)

    # 3. CloudWatch에서 애플리케이션별 메트릭 조회
    query_custom_metrics()

    print("\n" + "=" * 80)
    print("💡 Next Steps")
    print("=" * 80)
    print("\n1. CloudWatch 콘솔 접속:")
    print("   https://console.aws.amazon.com/cloudwatch/")
    print("\n2. 'Metrics' → 'All metrics' → 'Custom/BedrockUsage' 선택")
    print("\n3. 'Application' Dimension으로 필터링하여 애플리케이션별 사용량 확인")
    print("\n4. 대시보드를 만들어 시각화 가능")
    print("=" * 80)
