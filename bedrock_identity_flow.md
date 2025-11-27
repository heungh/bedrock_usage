# Amazon Bedrock Identity & Logging Flow

이 다이어그램은 애플리케이션 코드 수정 없이 IAM Role(Instance Profile/Task Role)을 사용하여 Amazon Bedrock을 호출하고, 해당 신원이 로그에 어떻게 기록되는지를 보여줍니다.

```mermaid
graph TD
    %% 스타일 정의
    classDef container fill:#f9f9f9,stroke:#333,stroke-width:2px,color:#333;
    classDef role fill:#fff3cd,stroke:#ffc107,stroke-width:2px,color:#333;
    classDef code fill:#e3f2fd,stroke:#2196f3,stroke-width:2px,color:#333;
    classDef log fill:#e8f5e9,stroke:#4caf50,stroke-width:2px,color:#333;
    classDef record fill:#fff,stroke:#333,stroke-dasharray: 5 5,color:#555;

    %% 컴퓨팅 환경 서브그래프
    subgraph Compute["🖥️ EC2 / ECS Instance (Application Running)"]
        direction TB
        
        Role["🔑 IAM Instance Profile / Task Role<br/><b>arn:aws:iam::123456789012:role/App-A-BedrockRole</b><br/>(또는 App-B 등)"]
        
        Code["💻 Application Code (변경 없음)<br/><pre>bedrock_client = boto3.client('bedrock-runtime')<br/>bedrock_client.invoke_model(...)</pre>"]
        
        Role -.->|Credential 자동 주입| Code
    end

    %% 로그 및 결과
    Logs[("📄 Amazon Bedrock Invocation Log")]
    
    LogRecord["📝 Log Record Details<br/><b>identity.arn</b>: <br/>arn:aws:iam::123456789012:role/App-A-BedrockRole"]

    %% 흐름 연결
    Code ==>|자동으로 Role 사용하여 호출| Logs
    Logs --- LogRecord

    %% 클래스 적용
    class Compute container;
    class Role role;
    class Code code;
    class Logs log;
    class LogRecord record;
```

### 핵심 포인트
1. **코드 수정 불필요**: `boto3`는 실행 환경(EC2/ECS)에 할당된 IAM Role을 자동으로 감지합니다.
2. **명확한 추적**: CloudTrail 및 Bedrock 로그에 실제 애플리케이션에 할당된 Role ARN이 `identity.arn`으로 기록됩니다.
3. **보안 모범 사례**: 소스 코드에 장기 자격 증명(Access Key)이나 Role ARN을 하드코딩하지 않습니다.
