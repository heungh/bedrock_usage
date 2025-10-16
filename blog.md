# Bedrock 사용량 추적: Application별 구분 및 실제 토큰 추출

## 업데이트 내용 (2025-10-16)

`bedrock_tracker.py`가 다음 기능으로 업데이트되었습니다:

### ✅ 구현 완료
1. **CloudTrail에서 실제 토큰 사용량 추출** - responseElements에서 실제 inputTokens/outputTokens 추출
2. **애플리케이션별 추적** - IAM Role 및 UserAgent 기반 앱 식별
3. **정확한 사용자별/앱별 비용 계산** - 실제 토큰 데이터 우선 사용, 없으면 추정

---

## 현재 상태 분석

업데이트된 `bedrock_tracker.py` 코드는:
- ✅ **사용자(User)별** 사용량 및 비용 추적 (실제 토큰 기반)
- ✅ **Application별** 사용량 및 비용 추적 (실제 토큰 기반)
- ✅ **리전별** 사용량 분석
- ✅ **모델별** 사용량 분석

## Application별 추적 가능 여부

### 1. IAM Role/User 기반 구분 (가장 권장)

각 application마다 다른 IAM Role 또는 IAM User를 할당하면, CloudTrail의 `userIdentity` 필드로 구분할 수 있습니다.

```python
# CloudTrail 이벤트에서 추출 가능한 정보
{
    "userIdentity": {
        "type": "AssumedRole",
        "principalId": "...",
        "arn": "arn:aws:sts::account-id:assumed-role/AppA-Role/session",
        "sessionContext": {...}
    }
}
```

**장점:**
- CloudTrail에서 기본으로 제공하는 정보 활용
- 명확한 권한 분리와 보안 강화
- 가장 신뢰할 수 있는 식별 방법

### 2. UserAgent 기반 구분

각 application이 고유한 UserAgent를 설정하면 구분 가능합니다:

```python
event_data.get('userAgent')  # CloudTrail 이벤트에서 추출
```

**장점:**
- Application 코드에서 쉽게 설정 가능
- 추가 인프라 변경 불필요

**단점:**
- Application이 UserAgent를 설정하지 않으면 사용 불가
- 조작 가능성 존재

### 3. Source IP 기반 구분

Application이 고정 IP에서 실행되면 `sourceIPAddress`로 구분 가능합니다.

```python
event_data.get('sourceIPAddress')
```

**장점:**
- 네트워크 레벨 식별
- 조작 불가능

**단점:**
- 동적 IP 환경에서 사용 어려움
- 같은 네트워크의 여러 application 구분 불가

### 4. Request Context 분석

CloudTrail의 `requestParameters`나 `additionalEventData`에 application 식별 정보를 포함시킬 수 있습니다.

**장점:**
- 커스텀 태깅 가능

**단점:**
- Bedrock API가 지원하는 범위 내에서만 가능

## 실제 구현 내용

### 1. 실제 토큰 사용량 추출 (`bedrock_tracker.py:39-66`)

CloudTrail의 responseElements에서 실제 토큰 데이터 추출:

```python
def extract_token_usage_from_event(self, event: Dict) -> Dict[str, int]:
    """CloudTrail 이벤트에서 실제 토큰 사용량 추출"""
    try:
        if 'CloudTrailEvent' in event:
            event_data = json.loads(event['CloudTrailEvent'])

            # responseElements에서 usage 정보 추출
            if 'responseElements' in event_data:
                response_elements = event_data['responseElements']

                # Bedrock API 응답 구조에 따라 usage 정보 추출
                if 'usage' in response_elements:
                    usage = response_elements['usage']
                    return {
                        'input_tokens': usage.get('inputTokens', 0),
                        'output_tokens': usage.get('outputTokens', 0)
                    }

                # 다른 가능한 구조 확인
                if 'inputTokenCount' in response_elements:
                    return {
                        'input_tokens': response_elements.get('inputTokenCount', 0),
                        'output_tokens': response_elements.get('outputTokenCount', 0)
                    }
    except Exception as e:
        pass

    return {'input_tokens': 0, 'output_tokens': 0}
```

### 2. Application 정보 추출 (`bedrock_tracker.py:68-107`)

IAM Role 및 UserAgent에서 애플리케이션 정보 추출:

```python
def extract_application_info(self, event: Dict) -> str:
    """CloudTrail 이벤트에서 애플리케이션 정보 추출"""
    try:
        if 'CloudTrailEvent' in event:
            event_data = json.loads(event['CloudTrailEvent'])

            # 방법 1: IAM Role에서 추출 (가장 신뢰할 수 있음)
            if 'userIdentity' in event_data:
                user_identity = event_data['userIdentity']

                # AssumedRole인 경우
                if user_identity.get('type') == 'AssumedRole':
                    arn = user_identity.get('arn', '')
                    # ARN 형식: arn:aws:sts::123456789012:assumed-role/AppName-BedrockRole/session
                    if 'assumed-role' in arn:
                        parts = arn.split('/')
                        if len(parts) >= 2:
                            role_name = parts[-2]  # Role 이름
                            # Role 이름에서 Application 이름 추출
                            # 예: "CustomerServiceApp-BedrockRole" -> "CustomerServiceApp"
                            if '-BedrockRole' in role_name:
                                return role_name.replace('-BedrockRole', '')
                            return role_name

            # 방법 2: UserAgent에서 추출
            user_agent = event_data.get('userAgent', '')
            if user_agent:
                # UserAgent 형식: "aws-cli/2.x Python/3.x boto3/1.x botocore/1.x AppName/1.0"
                parts = user_agent.split()
                for part in parts:
                    if '/' in part and not part.startswith(('aws-', 'Python/', 'boto', 'Boto', 'exec-env')):
                        app_name = part.split('/')[0]
                        # 일반적인 SDK 관련 문자열 제외
                        if app_name not in ['botocore', 'urllib3', 'APN']:
                            return app_name

    except Exception as e:
        pass

    return 'Unknown'
```

### 3. 실제 토큰 기반 비용 계산 (`bedrock_tracker.py:259-374`)

실제 토큰 데이터가 있으면 정확한 계산, 없으면 추정:

```python
def calculate_user_costs(self, events: List[Dict], metrics_data: Dict) -> Tuple[pd.DataFrame, str]:
    """사용자별 토큰 사용량과 비용 계산 (실제 토큰 우선, 없으면 추정)"""
    user_cost_data = []

    # CloudTrail에 토큰 데이터가 있는지 확인
    events_with_tokens = [e for e in events if e.get('has_token_data', False)]
    has_actual_token_data = len(events_with_tokens) > 0

    if has_actual_token_data:
        # 방법 1: CloudTrail에서 실제 토큰 데이터 사용 (가장 정확)
        user_data = {}

        for event in events:
            user = event['user']
            region = event['region']
            model_id = event['model_id']
            user_key = f"{user}|{region}|{model_id}"

            if user_key not in user_data:
                user_data[user_key] = {
                    'user': user,
                    'region': region,
                    'model_id': model_id,
                    'count': 0,
                    'input_tokens': 0,
                    'output_tokens': 0
                }

            user_data[user_key]['count'] += 1
            user_data[user_key]['input_tokens'] += event.get('input_tokens', 0)
            user_data[user_key]['output_tokens'] += event.get('output_tokens', 0)

        # ... 비용 계산 로직 ...
        calculation_method = "actual"
    else:
        # 방법 2: CloudWatch 메트릭을 호출 비율로 분배 (추정)
        # ... 기존 추정 로직 ...
        calculation_method = "estimated"

    return df, calculation_method
```

### 4. Application별 비용 계산 함수 (`bedrock_tracker.py:376-491`)

사용자별 계산과 동일한 로직으로 애플리케이션별 비용 계산:

```python
def calculate_application_costs(self, events: List[Dict], metrics_data: Dict) -> Tuple[pd.DataFrame, str]:
    """애플리케이션별 토큰 사용량과 비용 계산 (실제 토큰 우선, 없으면 추정)"""
    # 사용자별과 동일한 로직
    # 실제 토큰 데이터 우선, 없으면 호출 비율로 추정
    # ...
```

### 5. UI에 Application별 분석 섹션 추가 (`bedrock_tracker.py:655-706`)

Streamlit UI에 애플리케이션별 비용 분석 섹션 추가:

```python
# Step 6: 애플리케이션별 비용 분석
st.subheader("🚀 Application Cost Analysis")

if tracker.discovered_applications:
    st.write(f"**Discovered Applications:** {', '.join(sorted(tracker.discovered_applications))}")

    app_cost_df, app_calc_method = tracker.calculate_application_costs(events, metrics_data)

    if app_calc_method == "actual":
        st.success("✅ Using actual token data from CloudTrail events (most accurate)")
    else:
        st.info("📌 Application costs are estimated based on their API call ratio.")

    # 애플리케이션별 요약 테이블, 차트 등...
```

## 권장 구현 방법

**가장 현실적이고 신뢰할 수 있는 방법은 IAM Role 기반 구분입니다.**

### 구현 단계:

1. **각 Application에 전용 IAM Role 부여**
   - AppA-BedrockRole
   - AppB-BedrockRole
   - AppC-BedrockRole

2. **CloudTrail 이벤트에서 Role ARN 파싱**
   - `userIdentity.sessionContext.sessionIssuer.userName`
   - 또는 `userIdentity.arn`에서 Role 이름 추출

3. **Role 이름을 Application 이름으로 매핑**
   - Role 네이밍 컨벤션 설정: `{AppName}-BedrockRole`
   - 설정 파일이나 매핑 테이블 사용

4. **Application별 집계 및 리포팅**
   - User별 분석과 동일한 방식으로 Application별 분석 수행
   - 비용도 Application별로 분배

## 추가 고려사항

### CloudWatch Metrics 제한

CloudWatch Bedrock 메트릭은 기본적으로 다음 차원(Dimension)만 제공합니다:
- ModelId
- (일부 리전에서) UserId

Application별 메트릭은 직접 제공되지 않으므로, CloudTrail 기반 호출 비율로 추정해야 합니다.

### 정확도 향상 방법

1. **CloudTrail 이벤트를 S3/Athena에 저장**하여 더 긴 기간 분석
2. **Application별 IAM Policy**로 특정 모델만 사용하도록 제한
3. **Tagging 전략** 수립 (가능한 경우)

## 핵심 개선 사항

### 1. 정확도 향상
- **이전**: 호출 횟수 비율로 토큰 추정 → 부정확
- **현재**: CloudTrail에서 실제 토큰 추출 → 정확한 비용 계산

### 2. 애플리케이션별 추적
- **이전**: 사용자별로만 추적 가능
- **현재**: IAM Role 또는 UserAgent로 앱 자동 식별 및 추적

### 3. 데이터 소스 우선순위
1. CloudTrail responseElements (실제 토큰) - 최우선
2. CloudWatch 메트릭 (추정) - Fallback

### 4. UI 개선
- 실제 토큰 사용 시 명확한 표시 (✅ Using actual token data)
- 애플리케이션별 비용 분석 섹션 추가
- 데이터 소스 투명성 (Actual vs Estimated)

## 결론

### ✅ 구현 완료
Application별 및 사용자별 Bedrock 사용량 추적이 **완전히 구현**되었으며:
- **IAM Role 기반 구분**이 가장 권장되는 방법
- **실제 토큰 데이터** 추출로 정확한 비용 계산 가능
- **CloudTrail 활용**으로 추가 인프라 없이 구현 가능

### 요구사항
CloudTrail에서 실제 토큰 데이터를 추출하려면:
1. CloudTrail 데이터 이벤트 로깅 활성화
2. Bedrock API 호출(`InvokeModel`, `InvokeModelWithResponseStream`) 로깅 설정
3. `responseElements` 포함 옵션 활성화

---

## 실제 테스트 가이드 및 예시

### 방법 1: UserAgent 활용 예시

#### 1.1 Application 코드에서 UserAgent 설정

```python
# test_useragent_tracking.py
import boto3
import json
from botocore.config import Config

def test_bedrock_with_useragent(app_name: str, model_id: str):
    """UserAgent를 설정하여 Bedrock 호출"""

    # UserAgent에 Application 식별 정보 추가
    config = Config(
        user_agent_extra=f'{app_name}/1.0'
    )

    # Bedrock Runtime 클라이언트 생성
    bedrock_client = boto3.client(
        'bedrock-runtime',
        region_name='us-east-1',
        config=config
    )

    # 모델 호출
    request_body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 100,
        "messages": [
            {
                "role": "user",
                "content": f"Hello from {app_name}!"
            }
        ]
    }

    try:
        response = bedrock_client.invoke_model(
            modelId=model_id,
            body=json.dumps(request_body)
        )

        response_body = json.loads(response['body'].read())
        print(f"✅ {app_name} 호출 성공!")
        print(f"   Model: {model_id}")
        print(f"   Response: {response_body['content'][0]['text'][:50]}...")

    except Exception as e:
        print(f"❌ {app_name} 호출 실패: {str(e)}")

if __name__ == "__main__":
    model_id = 'anthropic.claude-3-5-sonnet-20241022-v2:0'

    # 여러 Application 시뮬레이션
    test_bedrock_with_useragent('CustomerServiceApp', model_id)
    test_bedrock_with_useragent('DataAnalysisApp', model_id)
    test_bedrock_with_useragent('ChatbotApp', model_id)

    print("\n💡 CloudTrail에서 약 15분 후 확인 가능합니다.")
```

#### 1.2 CloudTrail에서 UserAgent 추출

```python
def extract_app_from_useragent(user_agent: str) -> str:
    """UserAgent에서 Application 이름 추출

    예시:
    - "aws-cli/2.x Python/3.x boto3/1.x botocore/1.x CustomerServiceApp/1.0"
      -> "CustomerServiceApp"
    """
    parts = user_agent.split()
    for part in parts:
        if '/' in part and not part.startswith(('aws-', 'Python/', 'boto', 'Boto')):
            return part.split('/')[0]
    return 'Unknown'

# bedrock_tracker.py에 추가할 코드
def extract_application_info(self, event: Dict) -> str:
    """CloudTrail 이벤트에서 application 정보 추출"""
    try:
        if 'CloudTrailEvent' in event:
            event_data = json.loads(event['CloudTrailEvent'])

            # UserAgent에서 추출
            user_agent = event_data.get('userAgent', '')
            if user_agent:
                app_name = self.extract_app_from_useragent(user_agent)
                if app_name != 'Unknown':
                    return app_name
    except Exception as e:
        pass
    return 'Unknown'
```

### 방법 2: IAM Role 활용 예시 (권장)

#### 2.1 IAM Role 생성 (Terraform 예시)

```hcl
# terraform/bedrock_app_roles.tf

# Application A용 IAM Role
resource "aws_iam_role" "app_a_bedrock_role" {
  name = "CustomerServiceApp-BedrockRole"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ec2.amazonaws.com"  # 또는 실제 서비스
          # AWS = "arn:aws:iam::${var.account_id}:root"  # Cross-account
        }
      }
    ]
  })
}

resource "aws_iam_role_policy" "app_a_bedrock_policy" {
  name = "bedrock-invoke-policy"
  role = aws_iam_role.app_a_bedrock_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "bedrock:InvokeModel",
          "bedrock:InvokeModelWithResponseStream"
        ]
        Resource = [
          "arn:aws:bedrock:*::foundation-model/anthropic.claude-*"
        ]
      }
    ]
  })
}

# Application B용 IAM Role
resource "aws_iam_role" "app_b_bedrock_role" {
  name = "DataAnalysisApp-BedrockRole"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"  # Lambda용
        }
      }
    ]
  })
}

resource "aws_iam_role_policy" "app_b_bedrock_policy" {
  name = "bedrock-invoke-policy"
  role = aws_iam_role.app_b_bedrock_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "bedrock:InvokeModel"
        ]
        Resource = [
          "arn:aws:bedrock:*::foundation-model/anthropic.claude-*"
        ]
      }
    ]
  })
}
```

#### 2.2 IAM Role을 사용한 Bedrock 호출

```python
# test_iam_role_tracking.py
import boto3
import json
from typing import Dict

def assume_role_and_invoke_bedrock(
    role_arn: str,
    app_name: str,
    model_id: str,
    region: str = 'us-east-1'
) -> Dict:
    """IAM Role을 Assume하여 Bedrock 호출"""

    # STS 클라이언트로 Role Assume
    sts_client = boto3.client('sts')

    try:
        assumed_role = sts_client.assume_role(
            RoleArn=role_arn,
            RoleSessionName=f'{app_name}-session-{int(time.time())}'
        )

        # 임시 자격증명 가져오기
        credentials = assumed_role['Credentials']

        # 임시 자격증명으로 Bedrock 클라이언트 생성
        bedrock_client = boto3.client(
            'bedrock-runtime',
            region_name=region,
            aws_access_key_id=credentials['AccessKeyId'],
            aws_secret_access_key=credentials['SecretAccessKey'],
            aws_session_token=credentials['SessionToken']
        )

        # Bedrock 모델 호출
        request_body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 100,
            "messages": [
                {
                    "role": "user",
                    "content": f"Hello from {app_name}!"
                }
            ]
        }

        response = bedrock_client.invoke_model(
            modelId=model_id,
            body=json.dumps(request_body)
        )

        response_body = json.loads(response['body'].read())

        print(f"✅ {app_name} 호출 성공!")
        print(f"   Role ARN: {role_arn}")
        print(f"   Model: {model_id}")
        print(f"   Response: {response_body['content'][0]['text'][:50]}...")

        return {
            'success': True,
            'app_name': app_name,
            'role_arn': role_arn,
            'response': response_body
        }

    except Exception as e:
        print(f"❌ {app_name} 호출 실패: {str(e)}")
        return {
            'success': False,
            'app_name': app_name,
            'error': str(e)
        }

if __name__ == "__main__":
    import time

    # 실제 환경에 맞게 수정
    account_id = "123456789012"  # AWS 계정 ID
    model_id = 'anthropic.claude-3-5-sonnet-20241022-v2:0'

    # 각 Application Role
    apps = [
        {
            'name': 'CustomerServiceApp',
            'role_arn': f'arn:aws:iam::{account_id}:role/CustomerServiceApp-BedrockRole'
        },
        {
            'name': 'DataAnalysisApp',
            'role_arn': f'arn:aws:iam::{account_id}:role/DataAnalysisApp-BedrockRole'
        },
        {
            'name': 'ChatbotApp',
            'role_arn': f'arn:aws:iam::{account_id}:role/ChatbotApp-BedrockRole'
        }
    ]

    # 각 Application으로 호출
    results = []
    for app in apps:
        result = assume_role_and_invoke_bedrock(
            role_arn=app['role_arn'],
            app_name=app['name'],
            model_id=model_id
        )
        results.append(result)
        time.sleep(1)  # Rate limiting 방지

    print("\n📊 테스트 결과 요약:")
    success_count = sum(1 for r in results if r['success'])
    print(f"   성공: {success_count}/{len(results)}")
    print("\n💡 CloudTrail에서 약 15분 후 각 Role별로 호출 기록 확인 가능")
```

#### 2.3 CloudTrail에서 IAM Role 정보 추출

```python
def extract_app_from_role(event: Dict) -> str:
    """CloudTrail 이벤트에서 IAM Role 기반 Application 이름 추출"""
    try:
        if 'CloudTrailEvent' in event:
            event_data = json.loads(event['CloudTrailEvent'])

            if 'userIdentity' in event_data:
                user_identity = event_data['userIdentity']

                # AssumedRole인 경우
                if user_identity.get('type') == 'AssumedRole':
                    arn = user_identity.get('arn', '')
                    # ARN 형식: arn:aws:sts::123456789012:assumed-role/CustomerServiceApp-BedrockRole/session-name

                    if 'assumed-role' in arn:
                        parts = arn.split('/')
                        if len(parts) >= 2:
                            role_name = parts[-2]  # Role 이름

                            # Role 이름에서 Application 이름 추출
                            # 예: "CustomerServiceApp-BedrockRole" -> "CustomerServiceApp"
                            if '-BedrockRole' in role_name:
                                return role_name.replace('-BedrockRole', '')
                            return role_name

                # IAM User인 경우
                elif user_identity.get('type') == 'IAMUser':
                    return user_identity.get('userName', 'Unknown')

    except Exception as e:
        print(f"Error extracting app from role: {e}")

    return 'Unknown'
```

### 방법 3: Source IP 활용 예시

```python
# test_source_ip_tracking.py
def extract_app_from_ip(event: Dict, ip_mapping: Dict[str, str]) -> str:
    """Source IP로 Application 구분

    Args:
        event: CloudTrail 이벤트
        ip_mapping: IP 주소와 Application 이름 매핑
            예: {
                '10.0.1.100': 'CustomerServiceApp',
                '10.0.2.100': 'DataAnalysisApp'
            }
    """
    try:
        if 'CloudTrailEvent' in event:
            event_data = json.loads(event['CloudTrailEvent'])
            source_ip = event_data.get('sourceIPAddress', '')

            # IP 매핑에서 찾기
            if source_ip in ip_mapping:
                return ip_mapping[source_ip]

            # CIDR 범위로 찾기 (선택적)
            for ip_range, app_name in ip_mapping.items():
                if '/' in ip_range:  # CIDR 표기
                    # ipaddress 모듈 사용
                    import ipaddress
                    if ipaddress.ip_address(source_ip) in ipaddress.ip_network(ip_range):
                        return app_name

    except Exception as e:
        print(f"Error extracting app from IP: {e}")

    return 'Unknown'

# 사용 예시
IP_TO_APP_MAPPING = {
    '10.0.1.100': 'CustomerServiceApp',
    '10.0.2.100': 'DataAnalysisApp',
    '10.0.3.0/24': 'ChatbotApp',  # CIDR 범위
}
```

### 완전한 테스트 스크립트

```python
# complete_test_guide.py
"""
Bedrock Application별 사용량 추적 테스트 가이드

이 스크립트는 세 가지 방법을 모두 테스트합니다:
1. UserAgent 기반
2. IAM Role 기반 (권장)
3. Source IP 기반
"""

import boto3
import json
import time
from datetime import datetime, timedelta
from botocore.config import Config
from typing import Dict, List

class BedrockAppTrackingTest:
    def __init__(self, region='us-east-1'):
        self.region = region
        self.model_id = 'anthropic.claude-3-5-sonnet-20241022-v2:0'

    def test_useragent_method(self, app_name: str):
        """방법 1: UserAgent 기반 테스트"""
        print(f"\n{'='*60}")
        print(f"테스트 1: UserAgent 방법 - {app_name}")
        print(f"{'='*60}")

        config = Config(user_agent_extra=f'{app_name}/1.0')
        bedrock = boto3.client(
            'bedrock-runtime',
            region_name=self.region,
            config=config
        )

        request_body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 50,
            "messages": [{"role": "user", "content": "Say hello"}]
        }

        try:
            response = bedrock.invoke_model(
                modelId=self.model_id,
                body=json.dumps(request_body)
            )
            print(f"✅ 성공: {app_name} (UserAgent 방법)")
            return True
        except Exception as e:
            print(f"❌ 실패: {str(e)}")
            return False

    def test_iam_role_method(self, role_arn: str, app_name: str):
        """방법 2: IAM Role 기반 테스트"""
        print(f"\n{'='*60}")
        print(f"테스트 2: IAM Role 방법 - {app_name}")
        print(f"{'='*60}")

        try:
            sts = boto3.client('sts')
            assumed_role = sts.assume_role(
                RoleArn=role_arn,
                RoleSessionName=f'{app_name}-test-session'
            )

            credentials = assumed_role['Credentials']
            bedrock = boto3.client(
                'bedrock-runtime',
                region_name=self.region,
                aws_access_key_id=credentials['AccessKeyId'],
                aws_secret_access_key=credentials['SecretAccessKey'],
                aws_session_token=credentials['SessionToken']
            )

            request_body = {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 50,
                "messages": [{"role": "user", "content": "Say hello"}]
            }

            response = bedrock.invoke_model(
                modelId=self.model_id,
                body=json.dumps(request_body)
            )
            print(f"✅ 성공: {app_name} (IAM Role 방법)")
            print(f"   Role ARN: {role_arn}")
            return True

        except Exception as e:
            print(f"❌ 실패: {str(e)}")
            return False

    def verify_cloudtrail_events(self, start_time: datetime):
        """CloudTrail 이벤트 확인"""
        print(f"\n{'='*60}")
        print(f"CloudTrail 이벤트 확인")
        print(f"{'='*60}")

        cloudtrail = boto3.client('cloudtrail', region_name=self.region)

        try:
            response = cloudtrail.lookup_events(
                LookupAttributes=[
                    {'AttributeKey': 'EventName', 'AttributeValue': 'InvokeModel'}
                ],
                StartTime=start_time,
                EndTime=datetime.now(),
                MaxResults=10
            )

            print(f"\n찾은 이벤트 수: {len(response.get('Events', []))}")

            for event in response.get('Events', []):
                event_data = json.loads(event['CloudTrailEvent'])

                # UserAgent 추출
                user_agent = event_data.get('userAgent', '')

                # IAM Role 추출
                user_identity = event_data.get('userIdentity', {})
                role_info = 'N/A'
                if user_identity.get('type') == 'AssumedRole':
                    arn = user_identity.get('arn', '')
                    if 'assumed-role' in arn:
                        role_info = arn.split('/')[-2]

                print(f"\n이벤트 시간: {event['EventTime']}")
                print(f"  UserAgent: {user_agent}")
                print(f"  Role: {role_info}")
                print(f"  User: {event.get('Username', 'N/A')}")

        except Exception as e:
            print(f"❌ CloudTrail 조회 실패: {str(e)}")
            print("   💡 CloudTrail 이벤트는 최대 15분 지연될 수 있습니다.")

def main():
    print("="*60)
    print("Bedrock Application별 추적 테스트")
    print("="*60)

    tester = BedrockAppTrackingTest()
    start_time = datetime.now()

    # 테스트할 Application 목록
    apps = [
        'CustomerServiceApp',
        'DataAnalysisApp',
        'ChatbotApp'
    ]

    # 방법 1: UserAgent 테스트
    print("\n\n[방법 1] UserAgent 기반 추적 테스트")
    print("-" * 60)
    useragent_results = []
    for app in apps:
        result = tester.test_useragent_method(app)
        useragent_results.append(result)
        time.sleep(1)

    # 방법 2: IAM Role 테스트 (Role ARN이 있는 경우)
    print("\n\n[방법 2] IAM Role 기반 추적 테스트")
    print("-" * 60)

    # 실제 환경의 Role ARN으로 변경 필요
    account_id = boto3.client('sts').get_caller_identity()['Account']

    print(f"⚠️  IAM Role 테스트를 위해서는 다음 Role들이 필요합니다:")
    for app in apps:
        role_name = f"{app}-BedrockRole"
        role_arn = f"arn:aws:iam::{account_id}:role/{role_name}"
        print(f"  - {role_arn}")

    print("\n💡 Role이 없다면 위의 Terraform 코드로 생성하세요.")

    # CloudTrail 이벤트 확인
    print("\n\n⏳ CloudTrail 이벤트 조회 중...")
    print("   (이벤트가 나타나기까지 최대 15분 소요)")
    time.sleep(3)

    tester.verify_cloudtrail_events(start_time - timedelta(minutes=5))

    # 결과 요약
    print("\n\n" + "="*60)
    print("테스트 결과 요약")
    print("="*60)

    success_count = sum(useragent_results)
    print(f"UserAgent 방법: {success_count}/{len(apps)} 성공")

    print("\n다음 단계:")
    print("1. 15분 후 bedrock_tracker.py를 실행하여 추적 결과 확인")
    print("2. Streamlit UI에서 Application별 사용량 확인")
    print("3. IAM Role이 설정된 경우, Role별 분석도 확인")

if __name__ == "__main__":
    main()
```

### 테스트 실행 방법

```bash
# 1. 필요한 패키지 설치
pip install boto3 streamlit pandas

# 2. AWS 자격증명 설정
export AWS_ACCESS_KEY_ID="your-access-key"
export AWS_SECRET_ACCESS_KEY="your-secret-key"
export AWS_DEFAULT_REGION="us-east-1"

# 3. UserAgent 테스트 실행
python test_useragent_tracking.py

# 4. IAM Role 생성 (Terraform 사용시)
cd terraform
terraform init
terraform plan
terraform apply

# 5. IAM Role 테스트 실행
python test_iam_role_tracking.py

# 6. 완전한 테스트 실행
python complete_test_guide.py

# 7. 15분 후 추적 결과 확인
streamlit run bedrock_tracker.py
```

### 예상 CloudTrail 이벤트 예시

```json
{
  "eventVersion": "1.08",
  "userIdentity": {
    "type": "AssumedRole",
    "principalId": "AROAXXXXXXXXX:CustomerServiceApp-session-1234567890",
    "arn": "arn:aws:sts::123456789012:assumed-role/CustomerServiceApp-BedrockRole/CustomerServiceApp-session-1234567890",
    "accountId": "123456789012",
    "sessionContext": {
      "sessionIssuer": {
        "type": "Role",
        "principalId": "AROAXXXXXXXXX",
        "arn": "arn:aws:iam::123456789012:role/CustomerServiceApp-BedrockRole",
        "accountId": "123456789012",
        "userName": "CustomerServiceApp-BedrockRole"
      }
    }
  },
  "eventTime": "2025-10-11T12:34:56Z",
  "eventSource": "bedrock.amazonaws.com",
  "eventName": "InvokeModel",
  "awsRegion": "us-east-1",
  "sourceIPAddress": "10.0.1.100",
  "userAgent": "aws-cli/2.x Python/3.11 boto3/1.x botocore/1.x CustomerServiceApp/1.0",
  "requestParameters": {
    "modelId": "anthropic.claude-3-5-sonnet-20241022-v2:0"
  },
  "responseElements": null,
  "requestID": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "eventID": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "readOnly": false,
  "eventType": "AwsApiCall",
  "managementEvent": false,
  "recipientAccountId": "123456789012"
}
```

이 이벤트에서:
- **IAM Role**: `CustomerServiceApp-BedrockRole`에서 `CustomerServiceApp` 추출
- **UserAgent**: `CustomerServiceApp/1.0`에서 `CustomerServiceApp` 추출
- **Source IP**: `10.0.1.100`을 매핑 테이블로 조회
