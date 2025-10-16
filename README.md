# Bedrock Usage Tracker

Amazon Bedrock 사용량을 추적하고 비용을 계산하는 애플리케이션입니다. Web UI(Streamlit)와 CLI 두 가지 방식으로 사용 가능합니다.

## 목차
- [기능](#기능)
- [설치 및 설정](#설치-및-설정)
- [테스트 환경 구축](#테스트-환경-구축)
- [실행 방법](#실행-방법)
- [사용법](#사용법)
- [애플리케이션별 추적](#애플리케이션별-추적)
- [데이터 정확도](#데이터-정확도)
- [필수 요구사항](#필수-요구사항)

## 기능

### 핵심 기능
- **CloudTrail 이벤트 추적**: Bedrock 모델 호출 이벤트 추적
- **실제 토큰 사용량 추출**: CloudTrail responseElements에서 실제 토큰 데이터 추출 (가장 정확)
- **CloudWatch 메트릭**: 토큰 사용량 모니터링 (fallback)
- **비용 계산**: 리전별 요금에 따른 정확한 비용 계산
- **다중 선택**: 여러 리전과 모델 동시 선택
- **시각화**: 차트를 통한 사용량 및 비용 분석 (Streamlit UI)

### 추적 가능한 항목
- **사용자별 분석**: IAM User/Role별 사용량 및 비용
- **애플리케이션별 분석**: IAM Role 또는 UserAgent 기반 앱별 사용량 및 비용
- **리전별 분석**: AWS 리전별 사용 패턴
- **모델별 분석**: Claude 모델별 사용 통계

### 제공되는 인터페이스
- **Streamlit Web UI** (`bedrock_tracker.py`): 대시보드 형태의 웹 인터페이스
- **CLI** (`bedrock_tracker_cli.py`): 터미널에서 직접 실행하는 커맨드라인 인터페이스

## 설치 및 설정

### 1. 의존성 설치

```bash
pip install -r requirements.txt
```

### 2. AWS 자격 증명 설정

```bash
aws configure
```

필요한 정보:
- AWS Access Key ID
- AWS Secret Access Key
- Default region name (예: us-east-1)
- Default output format (예: json)

### 3. AWS 권한 설정

사용자 또는 Role에 다음 권한이 필요합니다:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "cloudtrail:LookupEvents",
        "cloudwatch:GetMetricStatistics",
        "bedrock:ListFoundationModels",
        "sts:AssumeRole"
      ],
      "Resource": "*"
    }
  ]
}
```

### 4. CloudTrail 설정

실제 토큰 데이터를 추출하려면 CloudTrail에서 다음을 설정해야 합니다:

1. **데이터 이벤트** 로깅 활성화
2. Bedrock API 호출 로깅 설정:
   - `InvokeModel`
   - `InvokeModelWithResponseStream`
3. `responseElements` 포함 옵션 활성화

> **참고**: CloudTrail에 토큰 데이터가 없어도 CloudWatch 메트릭을 fallback으로 사용하여 추정 비용을 계산할 수 있습니다.

## 테스트 환경 구축

애플리케이션별 추적 기능을 테스트하기 위한 환경을 구축할 수 있습니다.

### Step 1: 테스트용 IAM Role 생성

여러 애플리케이션을 시뮬레이션하기 위한 IAM Role을 생성합니다:

```bash
python setup_test_roles.py
```

생성되는 Role:
- `CustomerServiceApp-BedrockRole`
- `DataAnalysisApp-BedrockRole`
- `ChatbotApp-BedrockRole`
- `DocumentProcessorApp-BedrockRole`

각 Role은 Bedrock API 호출 권한을 가지며, CloudTrail에서 애플리케이션을 구분하는 데 사용됩니다.

### Step 2: 테스트 데이터 생성

생성된 IAM Role을 사용하여 실제 Bedrock API를 호출합니다:

```bash
python generate_test_data.py
```

이 스크립트는:
- 각 애플리케이션 Role로 Bedrock API를 호출
- 다양한 모델(Haiku, Sonnet 4.5)을 사용
- 여러 리전(us-east-1, us-west-2)에서 호출
- UserAgent 기반 애플리케이션도 시뮬레이션

**실행 결과 예시**:
```
✅ Successful Scenarios: 7/7
✅ Successful API Calls: 21/21
```

### Step 3: CloudTrail 이벤트 대기

API 호출 후 CloudTrail 이벤트가 인덱싱될 때까지 2-3분 정도 기다립니다.

```bash
# 2분 대기
sleep 120
```

### Step 4: 결과 확인

이제 tracker를 실행하여 애플리케이션별 비용 분석을 확인할 수 있습니다:

```bash
# CLI로 확인
python bedrock_tracker_cli.py

# 또는 Streamlit UI로 확인
streamlit run bedrock_tracker.py
```

### Step 5: 테스트 환경 정리 (선택사항)

테스트가 끝나면 생성한 IAM Role을 삭제할 수 있습니다:

```bash
python setup_test_roles.py cleanup
```

## 실행 방법

### 방법 1: Streamlit Web UI (권장)

대시보드 형태의 웹 인터페이스로 시각화와 함께 데이터를 확인할 수 있습니다.

```bash
streamlit run bedrock_tracker.py
```

브라우저에서 자동으로 열리며, 일반적으로 `http://localhost:8501`에서 접근 가능합니다.

**기능**:
- 사이드바에서 리전, 날짜 범위 선택
- 차트와 테이블로 시각화
- 인터랙티브한 데이터 탐색

### 방법 2: CLI (커맨드라인)

터미널에서 직접 실행하여 빠르게 결과를 확인할 수 있습니다.

```bash
python bedrock_tracker_cli.py
```

**특징**:
- Web UI와 동일한 분석 기능
- 터미널에서 즉시 실행
- 자동화 스크립트에 통합 가능
- 기본 설정: 10월 1일 ~ 현재, us-east-1 & us-west-2

**CLI 파라미터 수정** (필요시):
```python
# bedrock_tracker_cli.py 파일 수정
start_time = datetime(2025, 10, 1)  # 시작 날짜
end_time = datetime.now()           # 종료 날짜
regions = ['us-east-1', 'us-west-2']  # 조회할 리전
```

## 사용법

### Streamlit UI 사용법

1. 애플리케이션 실행:
   ```bash
   streamlit run bedrock_tracker.py
   ```

2. **사이드바 설정**:
   - 리전 선택 (다중 선택 가능)
   - 날짜 범위 설정
   - "Refresh Data" 버튼 클릭

3. **메인 화면 확인**:
   - **Discovered Models**: 발견된 모델 ID 목록
   - **User Activity Analysis**: 사용자별 API 호출 횟수
   - **User Cost Analysis**:
     - 사용자별 비용 (실제 토큰 기반 또는 추정)
     - 상세 breakdown (리전, 모델별)
   - **Application Cost Analysis**:
     - 애플리케이션별 비용
     - 앱별 리전, 모델 사용 패턴

### CLI 사용법

```bash
python bedrock_tracker_cli.py
```

출력 결과:
```
================================================================================
💰 USER COST ANALYSIS
================================================================================
User: CustomerServiceApp        $0.0084 (3 calls)
User: DataAnalysisApp           $0.0543 (2 calls)
...

================================================================================
🚀 APPLICATION COST ANALYSIS
================================================================================
Application: CustomerServiceApp  $0.0084 (3 calls, Haiku)
Application: DataAnalysisApp     $0.0543 (2 calls, Sonnet 4.5)
...
```

## 애플리케이션별 추적

애플리케이션별로 Bedrock 사용량과 비용을 추적하는 두 가지 방법이 있습니다.

### 방법 1: IAM Role 사용 (권장)

각 애플리케이션에 전용 IAM Role을 부여하고 `-BedrockRole` 네이밍 컨벤션을 사용합니다.

**Role 이름 예시**:
```
CustomerServiceApp-BedrockRole
DataAnalysisApp-BedrockRole
ChatbotApp-BedrockRole
DocumentProcessorApp-BedrockRole
```

**애플리케이션 코드에서 사용**:

```python
import boto3
import json

# 1. STS로 Role Assume
sts = boto3.client('sts')
assumed_role = sts.assume_role(
    RoleArn='arn:aws:iam::YOUR_ACCOUNT_ID:role/CustomerServiceApp-BedrockRole',
    RoleSessionName='CustomerServiceApp-session'
)

# 2. Assumed role credentials로 Bedrock 클라이언트 생성
bedrock = boto3.client(
    'bedrock-runtime',
    region_name='us-east-1',
    aws_access_key_id=assumed_role['Credentials']['AccessKeyId'],
    aws_secret_access_key=assumed_role['Credentials']['SecretAccessKey'],
    aws_session_token=assumed_role['Credentials']['SessionToken']
)

# 3. Bedrock API 호출
response = bedrock.invoke_model(
    modelId='us.anthropic.claude-3-haiku-20240307-v1:0',
    body=json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 200,
        "messages": [{"role": "user", "content": "Hello"}]
    })
)
```

**장점**:
- 가장 정확한 애플리케이션 식별
- CloudTrail에서 명확하게 구분됨
- IAM 정책으로 세밀한 권한 제어 가능

### 방법 2: UserAgent 사용

애플리케이션 코드에서 UserAgent를 설정합니다.

```python
from botocore.config import Config
import boto3

# UserAgent에 앱 이름 추가
config = Config(user_agent_extra='CustomerServiceApp/1.0')

bedrock = boto3.client(
    'bedrock-runtime',
    region_name='us-east-1',
    config=config
)

# Bedrock API 호출
response = bedrock.invoke_model(
    modelId='us.anthropic.claude-3-haiku-20240307-v1:0',
    body=json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 200,
        "messages": [{"role": "user", "content": "Hello"}]
    })
)
```

**장점**:
- 구현이 간단함
- 기존 Role 변경 불필요

**단점**:
- IAM Role 방식보다 덜 명확함
- UserAgent 파싱에 의존

### 애플리케이션 식별 로직

Tracker는 다음 순서로 애플리케이션을 식별합니다:

1. **IAM Role ARN에서 추출** (우선순위 높음):
   ```
   arn:aws:sts::123456789012:assumed-role/CustomerServiceApp-BedrockRole/session
   → Application: CustomerServiceApp
   ```

2. **UserAgent에서 추출** (fallback):
   ```
   Boto3/1.34.0 Python/3.11 CustomerServiceApp/1.0
   → Application: CustomerServiceApp
   ```

3. **식별 불가능한 경우**:
   - "Unknown"으로 표시

## 데이터 정확도

### 실제 토큰 데이터 (최고 정확도)

CloudTrail의 `responseElements`에 토큰 정보가 포함된 경우:

✅ **장점**:
- 사용자별 실제 토큰 사용량
- 애플리케이션별 실제 토큰 사용량
- 정확한 비용 계산

**CloudTrail 이벤트 구조**:
```json
{
  "responseElements": {
    "usage": {
      "inputTokens": 1234,
      "outputTokens": 567
    }
  }
}
```

### 추정 토큰 데이터 (추정치)

CloudTrail에 토큰 정보가 없는 경우, CloudWatch 메트릭을 사용합니다:

⚠️ **한계**:
- CloudWatch는 리전별, 모델별 총합만 제공
- API 호출 횟수 비율로 토큰 분배
- 각 호출의 토큰 사용량이 다를 수 있어 부정확할 수 있음

**추정 방식**:
```
사용자 A의 추정 토큰 = 모델 총 토큰 × (사용자 A의 호출 횟수 / 전체 호출 횟수)
```

**예시**:
```
모델: Claude Sonnet 4.5 (us-east-1)
총 토큰: 10,000 input, 2,000 output

사용자 A: 8회 호출 (80%)
사용자 B: 2회 호출 (20%)

→ 사용자 A 추정: 8,000 input, 1,600 output
→ 사용자 B 추정: 2,000 input, 400 output
```

### 데이터 소스 표시

Tracker는 항상 사용된 데이터 소스를 명시합니다:

- **"Actual Tokens from CloudTrail"**: 실제 토큰 데이터 사용
- **"CloudWatch (Estimated)"**: CloudWatch 메트릭 기반 추정

## 필수 요구사항

### Python 버전
- Python 3.8 이상

### Python 패키지
```
boto3
streamlit
pandas
plotly
```

설치:
```bash
pip install -r requirements.txt
```

### AWS 권한

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "cloudtrail:LookupEvents",
        "cloudwatch:GetMetricStatistics",
        "bedrock:ListFoundationModels",
        "sts:AssumeRole"
      ],
      "Resource": "*"
    }
  ]
}
```

### CloudTrail 설정

실제 토큰 데이터를 추출하려면:
1. CloudTrail에서 **데이터 이벤트** 로깅 활성화
2. Bedrock API 호출(`InvokeModel`, `InvokeModelWithResponseStream`) 로깅 설정
3. `responseElements` 포함 옵션 활성화

## 주의사항

### 일반 사항
- CloudTrail과 CloudWatch에 대한 적절한 IAM 권한이 필요합니다
- 대량의 데이터 조회 시 시간이 소요될 수 있습니다
- 리전별 요금은 2024년 기준이며 실제 요금과 다를 수 있습니다

### CloudTrail 관련
- CloudTrail 이벤트는 최대 15분 지연될 수 있습니다
- CloudTrail의 `lookup_events`는 기본적으로 90일간의 데이터만 조회 가능합니다
- 대량의 이벤트 조회 시 API throttling이 발생할 수 있습니다

### 비용 추정 정확도
- CloudTrail에 토큰 데이터가 없는 경우, 추정치는 **참고용**으로만 사용하세요
- 정확한 비용 계산을 위해서는 CloudTrail에서 `responseElements` 로깅을 활성화하는 것을 강력히 권장합니다
- 각 API 호출의 토큰 사용량이 크게 다른 경우, 추정 오차가 클 수 있습니다

## 파일 구조

```
bedrock_usage/
├── bedrock_tracker.py          # Streamlit Web UI
├── bedrock_tracker_cli.py      # CLI 버전
├── setup_test_roles.py         # 테스트 IAM Role 생성/삭제
├── generate_test_data.py       # 테스트 데이터 생성
├── inspect_cloudtrail.py       # CloudTrail 이벤트 상세 조사 도구
├── requirements.txt            # Python 의존성
├── README.md                   # 본 문서
└── blog.md                     # 기술 블로그 포스트
```

## 트러블슈팅

### 토큰 데이터가 표시되지 않음

**증상**: "Events with token data: 0 / X"

**해결방법**:
1. CloudTrail에서 데이터 이벤트 로깅이 활성화되어 있는지 확인
2. `responseElements` 포함 옵션이 활성화되어 있는지 확인
3. CloudWatch 메트릭을 fallback으로 사용 (자동)

### 애플리케이션이 "Unknown"으로 표시됨

**원인**:
- IAM Role 이름에 `-BedrockRole` 패턴이 없음
- UserAgent에 애플리케이션 식별자가 없음

**해결방법**:
- IAM Role 이름을 `AppName-BedrockRole` 형식으로 변경
- 또는 UserAgent에 애플리케이션 이름 추가

### CloudTrail 이벤트가 표시되지 않음

**원인**:
- CloudTrail 이벤트 인덱싱 지연 (최대 15분)
- 잘못된 리전 선택
- 권한 부족

**해결방법**:
1. 2-3분 후 다시 시도
2. Bedrock API를 호출한 리전이 선택되어 있는지 확인
3. IAM 권한에 `cloudtrail:LookupEvents` 포함 확인

## 라이선스

MIT License

## 기여

이슈 및 PR을 환영합니다!
