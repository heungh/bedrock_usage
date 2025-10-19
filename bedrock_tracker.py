import streamlit as st
import boto3
import pandas as pd
from datetime import datetime, timedelta
import time
from typing import Dict, List
import logging
import os
from pathlib import Path


# 로깅 설정
def setup_logger():
    """디버깅용 로거 설정"""
    log_dir = Path(__file__).parent / "log"
    log_dir.mkdir(exist_ok=True)

    log_filename = (
        log_dir / f"bedrock_tracker_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    )

    logger = logging.getLogger("BedrockTracker")
    logger.setLevel(logging.DEBUG)

    # 파일 핸들러
    file_handler = logging.FileHandler(log_filename, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)

    # 포맷 설정
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s"
    )
    file_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.info(f"Logger initialized. Log file: {log_filename}")

    return logger


# 글로벌 로거
logger = setup_logger()

# AWS Bedrock 모델 가격 테이블 (리전별)
# 참고: 최신 가격은 https://aws.amazon.com/bedrock/pricing/ 에서 확인하세요
# 가격은 USD 기준이며, 1000 토큰당 가격입니다
MODEL_PRICING = {
    # 기본 가격 (대부분의 리전에 적용)
    "default": {
        # Claude 3 모델
        "claude-3-haiku-20240307": {"input": 0.00025, "output": 0.00125},
        "claude-3-sonnet-20240229": {"input": 0.003, "output": 0.015},
        "claude-3-opus-20240229": {"input": 0.015, "output": 0.075},
        # Claude 3.5 모델
        "claude-3-5-haiku-20241022": {"input": 0.0008, "output": 0.004},
        "claude-3-5-sonnet-20240620": {"input": 0.003, "output": 0.015},
        "claude-3-5-sonnet-20241022": {"input": 0.003, "output": 0.015},
        # Claude 3.7 모델
        "claude-3-7-sonnet-20250219": {"input": 0.003, "output": 0.015},
        # Claude 4 모델
        "claude-sonnet-4-20250514": {"input": 0.003, "output": 0.015},
        "claude-sonnet-4-5-20250929": {"input": 0.003, "output": 0.015},
        "claude-opus-4-20250514": {"input": 0.015, "output": 0.075},
        "claude-opus-4-1-20250808": {"input": 0.015, "output": 0.075},
    },
    # US East (N. Virginia) - us-east-1
    "us-east-1": {
        "claude-3-haiku-20240307": {"input": 0.00025, "output": 0.00125},
        "claude-3-sonnet-20240229": {"input": 0.003, "output": 0.015},
        "claude-3-opus-20240229": {"input": 0.015, "output": 0.075},
        "claude-3-5-haiku-20241022": {"input": 0.0008, "output": 0.004},
        "claude-3-5-sonnet-20240620": {"input": 0.003, "output": 0.015},
        "claude-3-5-sonnet-20241022": {"input": 0.003, "output": 0.015},
        "claude-3-7-sonnet-20250219": {"input": 0.003, "output": 0.015},
        "claude-sonnet-4-20250514": {"input": 0.003, "output": 0.015},
        "claude-sonnet-4-5-20250929": {"input": 0.003, "output": 0.015},
        "claude-opus-4-20250514": {"input": 0.015, "output": 0.075},
        "claude-opus-4-1-20250808": {"input": 0.015, "output": 0.075},
    },
    # US West (Oregon) - us-west-2
    "us-west-2": {
        "claude-3-haiku-20240307": {"input": 0.00025, "output": 0.00125},
        "claude-3-sonnet-20240229": {"input": 0.003, "output": 0.015},
        "claude-3-opus-20240229": {"input": 0.015, "output": 0.075},
        "claude-3-5-haiku-20241022": {"input": 0.0008, "output": 0.004},
        "claude-3-5-sonnet-20240620": {"input": 0.003, "output": 0.015},
        "claude-3-5-sonnet-20241022": {"input": 0.003, "output": 0.015},
        "claude-3-7-sonnet-20250219": {"input": 0.003, "output": 0.015},
        "claude-sonnet-4-20250514": {"input": 0.003, "output": 0.015},
        "claude-sonnet-4-5-20250929": {"input": 0.003, "output": 0.015},
        "claude-opus-4-20250514": {"input": 0.015, "output": 0.075},
        "claude-opus-4-1-20250808": {"input": 0.015, "output": 0.075},
    },
    # Europe (Frankfurt) - eu-central-1
    "eu-central-1": {
        "claude-3-haiku-20240307": {"input": 0.00025, "output": 0.00125},
        "claude-3-sonnet-20240229": {"input": 0.003, "output": 0.015},
        "claude-3-opus-20240229": {"input": 0.015, "output": 0.075},
        "claude-3-5-haiku-20241022": {"input": 0.0008, "output": 0.004},
        "claude-3-5-sonnet-20240620": {"input": 0.003, "output": 0.015},
        "claude-3-5-sonnet-20241022": {"input": 0.003, "output": 0.015},
        "claude-3-7-sonnet-20250219": {"input": 0.003, "output": 0.015},
        "claude-sonnet-4-20250514": {"input": 0.003, "output": 0.015},
        "claude-sonnet-4-5-20250929": {"input": 0.003, "output": 0.015},
        "claude-opus-4-20250514": {"input": 0.015, "output": 0.075},
        "claude-opus-4-1-20250808": {"input": 0.015, "output": 0.075},
    },
    # Asia Pacific (Tokyo) - ap-northeast-1
    "ap-northeast-1": {
        "claude-3-haiku-20240307": {"input": 0.00025, "output": 0.00125},
        "claude-3-sonnet-20240229": {"input": 0.003, "output": 0.015},
        "claude-3-opus-20240229": {"input": 0.015, "output": 0.075},
        "claude-3-5-haiku-20241022": {"input": 0.0008, "output": 0.004},
        "claude-3-5-sonnet-20240620": {"input": 0.003, "output": 0.015},
        "claude-3-5-sonnet-20241022": {"input": 0.003, "output": 0.015},
        "claude-3-7-sonnet-20250219": {"input": 0.003, "output": 0.015},
        "claude-sonnet-4-20250514": {"input": 0.003, "output": 0.015},
        "claude-sonnet-4-5-20250929": {"input": 0.003, "output": 0.015},
        "claude-opus-4-20250514": {"input": 0.015, "output": 0.075},
        "claude-opus-4-1-20250808": {"input": 0.015, "output": 0.075},
    },
    # Asia Pacific (Seoul) - ap-northeast-2
    "ap-northeast-2": {
        "claude-3-haiku-20240307": {"input": 0.00025, "output": 0.00125},
        "claude-3-sonnet-20240229": {"input": 0.003, "output": 0.015},
        "claude-3-opus-20240229": {"input": 0.015, "output": 0.075},
        "claude-3-5-haiku-20241022": {"input": 0.0008, "output": 0.004},
        "claude-3-5-sonnet-20240620": {"input": 0.003, "output": 0.015},
        "claude-3-5-sonnet-20241022": {"input": 0.003, "output": 0.015},
        "claude-3-7-sonnet-20250219": {"input": 0.003, "output": 0.015},
        "claude-sonnet-4-20250514": {"input": 0.003, "output": 0.015},
        "claude-sonnet-4-5-20250929": {"input": 0.003, "output": 0.015},
        "claude-opus-4-20250514": {"input": 0.015, "output": 0.075},
        "claude-opus-4-1-20250808": {"input": 0.015, "output": 0.075},
    },
    # Asia Pacific (Singapore) - ap-southeast-1
    "ap-southeast-1": {
        "claude-3-haiku-20240307": {"input": 0.00025, "output": 0.00125},
        "claude-3-sonnet-20240229": {"input": 0.003, "output": 0.015},
        "claude-3-opus-20240229": {"input": 0.015, "output": 0.075},
        "claude-3-5-haiku-20241022": {"input": 0.0008, "output": 0.004},
        "claude-3-5-sonnet-20240620": {"input": 0.003, "output": 0.015},
        "claude-3-5-sonnet-20241022": {"input": 0.003, "output": 0.015},
        "claude-3-7-sonnet-20250219": {"input": 0.003, "output": 0.015},
        "claude-sonnet-4-20250514": {"input": 0.003, "output": 0.015},
        "claude-sonnet-4-5-20250929": {"input": 0.003, "output": 0.015},
        "claude-opus-4-20250514": {"input": 0.015, "output": 0.075},
        "claude-opus-4-1-20250808": {"input": 0.015, "output": 0.075},
    },
}

# 리전 설정
REGIONS = {
    "us-east-1": "US East (N. Virginia)",
    "us-west-2": "US West (Oregon)",
    "eu-central-1": "Europe (Frankfurt)",
    "ap-northeast-1": "Asia Pacific (Tokyo)",
    "ap-northeast-2": "Asia Pacific (Seoul)",
    "ap-southeast-1": "Asia Pacific (Singapore)",
}

default_region = "us-east-1"


def get_model_cost(model_id: str, input_tokens: int, output_tokens: int, region: str = "default") -> float:
    """모델별 비용 계산 (리전별 가격 반영)

    Args:
        model_id: Bedrock 모델 ID (예: us.anthropic.claude-3-haiku-20240307-v1:0)
        input_tokens: 입력 토큰 수
        output_tokens: 출력 토큰 수
        region: AWS 리전 (예: us-east-1, ap-northeast-2)

    Returns:
        float: 계산된 비용 (USD)
    """
    logger.debug(
        f"Calculating cost for model: {model_id}, input: {input_tokens}, output: {output_tokens}, region: {region}"
    )

    # 모델 ID에서 모델명 추출 (예: us.anthropic.claude-3-haiku-20240307-v1:0 -> claude-3-haiku-20240307)
    model_name = model_id.split(".")[-1].split("-v")[0] if "." in model_id else model_id

    # 리전별 가격 테이블 선택 (해당 리전이 없으면 default 사용)
    region_pricing = MODEL_PRICING.get(region, MODEL_PRICING["default"])

    # 가격 테이블에서 모델 찾기
    for key, pricing in region_pricing.items():
        if key in model_name:
            # 가격은 1000 토큰당 가격이므로 1000으로 나눔
            cost = (input_tokens * pricing["input"] / 1000) + (
                output_tokens * pricing["output"] / 1000
            )
            logger.debug(f"Model: {key}, Region: {region}, Cost: ${cost:.6f}")
            return cost

    # 기본 가격 (Claude 3 Haiku)
    logger.warning(f"Unknown model: {model_id}, using default pricing (Claude 3 Haiku)")
    default_pricing = MODEL_PRICING["default"]["claude-3-haiku-20240307"]
    default_cost = (input_tokens * default_pricing["input"] / 1000) + (
        output_tokens * default_pricing["output"] / 1000
    )
    return default_cost


class BedrockAthenaTracker:
    def __init__(self, region=default_region):
        logger.info(f"Initializing BedrockAthenaTracker with region: {region}")
        self.region = region
        self.athena = boto3.client("athena", region_name=region)
        # STS 클라이언트도 region을 지정하여 생성
        sts_client = boto3.client("sts", region_name=region)
        self.account_id = sts_client.get_caller_identity()["Account"]
        # 리전별 Athena 결과 저장용 버킷
        self.results_bucket = f"bedrock-analytics-{self.account_id}-{self.region}"
        logger.info(
            f"Account ID: {self.account_id}, Results bucket: {self.results_bucket}"
        )

    def get_current_logging_config(self) -> Dict:
        """현재 설정된 Model Invocation Logging 정보 조회"""
        logger.info("Getting current logging configuration")
        try:
            bedrock = boto3.client("bedrock", region_name=self.region)
            response = bedrock.get_model_invocation_logging_configuration()

            if "loggingConfig" in response:
                config = response["loggingConfig"]

                if "s3Config" in config:
                    result = {
                        "type": "s3",
                        "bucket": config["s3Config"].get("bucketName", ""),
                        "prefix": config["s3Config"].get("keyPrefix", ""),
                        "status": "enabled",
                    }
                    logger.info(f"Logging config: {result}")
                    return result

            logger.warning("Logging is disabled")
            return {"status": "disabled"}

        except Exception as e:
            logger.error(f"Error getting logging config: {str(e)}")
            return {"status": "error", "error": str(e)}

    def set_results_bucket(self, bucket_name: str):
        """Athena 결과 저장용 버킷 설정"""
        self.results_bucket = bucket_name
        logger.info(f"Results bucket set to: {self.results_bucket}")

    def execute_athena_query(
        self, query: str, database: str = "bedrock_analytics"
    ) -> pd.DataFrame:
        """Athena 쿼리 실행 및 결과 반환"""
        logger.info(f"Executing Athena query on database: {database}")
        logger.debug(f"Query: {query}")

        try:
            # 쿼리 실행
            response = self.athena.start_query_execution(
                QueryString=query,
                QueryExecutionContext={"Database": database},
                ResultConfiguration={
                    "OutputLocation": f"s3://{self.results_bucket}/query-results/"
                },
            )

            query_id = response["QueryExecutionId"]
            logger.info(f"Query execution started: {query_id}")

            # 쿼리 완료 대기
            max_wait = 60
            for i in range(max_wait):
                result = self.athena.get_query_execution(QueryExecutionId=query_id)
                status = result["QueryExecution"]["Status"]["State"]

                if status == "SUCCEEDED":
                    logger.info(f"Query succeeded in {i+1} seconds")
                    break
                elif status in ["FAILED", "CANCELLED"]:
                    error = result["QueryExecution"]["Status"].get(
                        "StateChangeReason", "Unknown error"
                    )
                    logger.error(f"Query failed: {error}")
                    raise Exception(f"Query failed: {error}")

                time.sleep(1)
            else:
                logger.error("Query timeout")
                raise Exception("Query timeout")

            # 결과 조회
            result_response = self.athena.get_query_results(QueryExecutionId=query_id)

            # DataFrame으로 변환
            columns = [
                col["Label"]
                for col in result_response["ResultSet"]["ResultSetMetadata"][
                    "ColumnInfo"
                ]
            ]
            rows = []

            for row in result_response["ResultSet"]["Rows"][1:]:  # 헤더 제외
                row_data = [field.get("VarCharValue", "") for field in row["Data"]]
                rows.append(row_data)

            df = pd.DataFrame(rows, columns=columns)
            logger.info(f"Query returned {len(df)} rows")
            return df

        except Exception as e:
            logger.error(f"Athena query execution failed: {str(e)}")
            st.error(f"Athena 쿼리 실행 실패: {str(e)}")
            return pd.DataFrame()

    def get_user_cost_analysis(
        self, start_date: datetime, end_date: datetime, arn_pattern: str = None
    ) -> pd.DataFrame:
        """사용자별 비용 분석"""
        logger.info(f"Getting user cost analysis from {start_date} to {end_date}, arn_pattern={arn_pattern}")

        arn_filter = f"AND identity.arn LIKE '%{arn_pattern}%'" if arn_pattern else ""

        query = f"""
        SELECT
            CASE
                WHEN identity.arn LIKE '%assumed-role%' THEN
                    regexp_extract(identity.arn, 'assumed-role/([^/]+)')
                WHEN identity.arn LIKE '%user%' THEN
                    regexp_extract(identity.arn, 'user/([^/]+)')
                ELSE 'Unknown'
            END as user_or_app,
            COUNT(*) as call_count,
            SUM(CAST(input.inputTokenCount AS BIGINT)) as total_input_tokens,
            SUM(CAST(output.outputTokenCount AS BIGINT)) as total_output_tokens
        FROM bedrock_invocation_logs
        WHERE CAST(CONCAT(year, '-', LPAD(month, 2, '0'), '-', LPAD(day, 2, '0')) AS DATE)
            BETWEEN DATE '{start_date.strftime('%Y-%m-%d')}' AND DATE '{end_date.strftime('%Y-%m-%d')}'
            {arn_filter}
        GROUP BY identity.arn
        ORDER BY call_count DESC
        """

        return self.execute_athena_query(query)

    def get_user_app_detail_analysis(
        self, start_date: datetime, end_date: datetime, arn_pattern: str = None
    ) -> pd.DataFrame:
        """유저별 애플리케이션별 상세 분석"""
        logger.info(f"Getting user-app detail analysis from {start_date} to {end_date}, arn_pattern={arn_pattern}")

        arn_filter = f"AND identity.arn LIKE '%{arn_pattern}%'" if arn_pattern else ""

        query = f"""
        SELECT
            CASE
                WHEN identity.arn LIKE '%assumed-role%' THEN
                    regexp_extract(identity.arn, 'assumed-role/([^/]+)')
                WHEN identity.arn LIKE '%user%' THEN
                    regexp_extract(identity.arn, 'user/([^/]+)')
                ELSE 'Unknown'
            END as user_or_app,
            regexp_extract(modelId, '([^/]+)$') as model_name,
            COUNT(*) as call_count,
            SUM(CAST(input.inputTokenCount AS BIGINT)) as total_input_tokens,
            SUM(CAST(output.outputTokenCount AS BIGINT)) as total_output_tokens
        FROM bedrock_invocation_logs
        WHERE CAST(CONCAT(year, '-', LPAD(month, 2, '0'), '-', LPAD(day, 2, '0')) AS DATE)
            BETWEEN DATE '{start_date.strftime('%Y-%m-%d')}' AND DATE '{end_date.strftime('%Y-%m-%d')}'
            {arn_filter}
        GROUP BY identity.arn, modelId
        ORDER BY user_or_app, call_count DESC
        """

        return self.execute_athena_query(query)

    def get_hourly_usage_pattern(
        self, start_date: datetime, end_date: datetime, arn_pattern: str = None
    ) -> pd.DataFrame:
        """시간별 사용 패턴 - timestamp에서 hour 추출"""
        logger.info(f"Getting hourly usage pattern from {start_date} to {end_date}, arn_pattern={arn_pattern}")

        arn_filter = f"AND identity.arn LIKE '%{arn_pattern}%'" if arn_pattern else ""

        query = f"""
        SELECT
            year,
            month,
            day,
            date_format(from_iso8601_timestamp(timestamp), '%H') as hour,
            COUNT(*) as call_count,
            SUM(CAST(input.inputTokenCount AS BIGINT)) as total_input_tokens,
            SUM(CAST(output.outputTokenCount AS BIGINT)) as total_output_tokens
        FROM bedrock_invocation_logs
        WHERE CAST(CONCAT(year, '-', LPAD(month, 2, '0'), '-', LPAD(day, 2, '0')) AS DATE)
            BETWEEN DATE '{start_date.strftime('%Y-%m-%d')}' AND DATE '{end_date.strftime('%Y-%m-%d')}'
            {arn_filter}
        GROUP BY year, month, day, date_format(from_iso8601_timestamp(timestamp), '%H')
        ORDER BY year, month, day, date_format(from_iso8601_timestamp(timestamp), '%H')
        """

        return self.execute_athena_query(query)

    def get_daily_usage_pattern(
        self, start_date: datetime, end_date: datetime, arn_pattern: str = None
    ) -> pd.DataFrame:
        """일별 사용 패턴"""
        logger.info(f"Getting daily usage pattern from {start_date} to {end_date}, arn_pattern={arn_pattern}")

        arn_filter = f"AND identity.arn LIKE '%{arn_pattern}%'" if arn_pattern else ""

        query = f"""
        SELECT
            year, month, day,
            COUNT(*) as call_count,
            SUM(CAST(input.inputTokenCount AS BIGINT)) as total_input_tokens,
            SUM(CAST(output.outputTokenCount AS BIGINT)) as total_output_tokens
        FROM bedrock_invocation_logs
        WHERE CAST(CONCAT(year, '-', LPAD(month, 2, '0'), '-', LPAD(day, 2, '0')) AS DATE)
            BETWEEN DATE '{start_date.strftime('%Y-%m-%d')}' AND DATE '{end_date.strftime('%Y-%m-%d')}'
            {arn_filter}
        GROUP BY year, month, day
        ORDER BY year, month, day
        """

        return self.execute_athena_query(query)

    def get_model_usage_stats(
        self, start_date: datetime, end_date: datetime, arn_pattern: str = None
    ) -> pd.DataFrame:
        """모델별 사용 통계"""
        logger.info(f"Getting model usage stats from {start_date} to {end_date}, arn_pattern={arn_pattern}")

        arn_filter = f"AND identity.arn LIKE '%{arn_pattern}%'" if arn_pattern else ""

        query = f"""
        SELECT
            regexp_extract(modelId, '([^/]+)$') as model_name,
            COUNT(*) as call_count,
            AVG(CAST(input.inputTokenCount AS DOUBLE)) as avg_input_tokens,
            AVG(CAST(output.outputTokenCount AS DOUBLE)) as avg_output_tokens,
            SUM(CAST(input.inputTokenCount AS BIGINT)) as total_input_tokens,
            SUM(CAST(output.outputTokenCount AS BIGINT)) as total_output_tokens
        FROM bedrock_invocation_logs
        WHERE CAST(CONCAT(year, '-', LPAD(month, 2, '0'), '-', LPAD(day, 2, '0')) AS DATE)
            BETWEEN DATE '{start_date.strftime('%Y-%m-%d')}' AND DATE '{end_date.strftime('%Y-%m-%d')}'
            {arn_filter}
        GROUP BY modelId
        ORDER BY call_count DESC
        """

        return self.execute_athena_query(query)

    def get_total_summary(self, start_date: datetime, end_date: datetime, arn_pattern: str = None) -> Dict:
        """전체 요약 통계"""
        logger.info(f"Getting total summary from {start_date} to {end_date}, arn_pattern={arn_pattern}")

        arn_filter = f"AND identity.arn LIKE '%{arn_pattern}%'" if arn_pattern else ""

        query = f"""
        SELECT
            COUNT(*) as total_calls,
            SUM(CAST(input.inputTokenCount AS BIGINT)) as total_input_tokens,
            SUM(CAST(output.outputTokenCount AS BIGINT)) as total_output_tokens
        FROM bedrock_invocation_logs
        WHERE CAST(CONCAT(year, '-', LPAD(month, 2, '0'), '-', LPAD(day, 2, '0')) AS DATE)
            BETWEEN DATE '{start_date.strftime('%Y-%m-%d')}' AND DATE '{end_date.strftime('%Y-%m-%d')}'
            {arn_filter}
        """

        df = self.execute_athena_query(query)

        if not df.empty:
            result = {
                "total_calls": (
                    int(df.iloc[0]["total_calls"]) if df.iloc[0]["total_calls"] else 0
                ),
                "total_input_tokens": (
                    int(df.iloc[0]["total_input_tokens"])
                    if df.iloc[0]["total_input_tokens"]
                    else 0
                ),
                "total_output_tokens": (
                    int(df.iloc[0]["total_output_tokens"])
                    if df.iloc[0]["total_output_tokens"]
                    else 0
                ),
                "total_cost_usd": 0.0,  # 모델별로 계산 필요
            }
            logger.info(f"Total summary: {result}")
            return result
        else:
            logger.warning("No data found for summary")
            return {
                "total_calls": 0,
                "total_input_tokens": 0,
                "total_output_tokens": 0,
                "total_cost_usd": 0.0,
            }


class QCliAthenaTracker:
    """Amazon Q CLI 사용량 추적을 위한 Athena 쿼리 클래스"""

    def __init__(self, region=default_region):
        logger.info(f"Initializing QCliAthenaTracker with region: {region}")
        self.region = region
        self.athena = boto3.client("athena", region_name=region)
        sts_client = boto3.client("sts", region_name=region)
        self.account_id = sts_client.get_caller_identity()["Account"]
        self.results_bucket = f"amazonq-developer-reports-{self.account_id}"
        logger.info(
            f"Account ID: {self.account_id}, Results bucket: {self.results_bucket}"
        )

    def execute_athena_query(
        self, query: str, database: str = "qcli_analytics"
    ) -> pd.DataFrame:
        """Athena 쿼리 실행 및 결과 반환"""
        logger.info(f"Executing Athena query on database: {database}")
        logger.debug(f"Query: {query}")

        try:
            # 쿼리 실행
            response = self.athena.start_query_execution(
                QueryString=query,
                QueryExecutionContext={"Database": database},
                ResultConfiguration={
                    "OutputLocation": f"s3://{self.results_bucket}/query-results/"
                },
            )

            query_id = response["QueryExecutionId"]
            logger.info(f"Query execution started: {query_id}")

            # 쿼리 완료 대기
            max_wait = 60
            for i in range(max_wait):
                result = self.athena.get_query_execution(QueryExecutionId=query_id)
                status = result["QueryExecution"]["Status"]["State"]

                if status == "SUCCEEDED":
                    logger.info(f"Query succeeded in {i+1} seconds")
                    break
                elif status in ["FAILED", "CANCELLED"]:
                    error = result["QueryExecution"]["Status"].get(
                        "StateChangeReason", "Unknown error"
                    )
                    logger.error(f"Query failed: {error}")
                    raise Exception(f"Query failed: {error}")

                time.sleep(1)
            else:
                logger.error("Query timeout")
                raise Exception("Query timeout")

            # 결과 조회
            result_response = self.athena.get_query_results(QueryExecutionId=query_id)

            # DataFrame으로 변환
            columns = [
                col["Label"]
                for col in result_response["ResultSet"]["ResultSetMetadata"][
                    "ColumnInfo"
                ]
            ]
            rows = []

            for row in result_response["ResultSet"]["Rows"][1:]:  # 헤더 제외
                row_data = [field.get("VarCharValue", "") for field in row["Data"]]
                rows.append(row_data)

            df = pd.DataFrame(rows, columns=columns)
            logger.info(f"Query returned {len(df)} rows")
            return df

        except Exception as e:
            logger.error(f"Athena query execution failed: {str(e)}")
            st.error(f"Athena 쿼리 실행 실패: {str(e)}")
            return pd.DataFrame()

    def get_total_summary(
        self, start_date: datetime, end_date: datetime, user_pattern: str = None
    ) -> Dict:
        """전체 요약 통계 - Amazon Q Developer CSV 리포트 기반"""
        logger.info(
            f"Getting QCli total summary from {start_date} to {end_date}, user_pattern={user_pattern}"
        )

        user_filter = f"AND user_id LIKE '%{user_pattern}%'" if user_pattern else ""

        query = f"""
        SELECT
            SUM(CAST(request_count AS BIGINT)) as total_requests,
            SUM(CAST(agentic_request_count AS BIGINT)) as total_agentic_requests,
            SUM(CAST(cli_request_count AS BIGINT)) as total_cli_requests,
            COUNT(DISTINCT user_id) as unique_users,
            COUNT(DISTINCT date) as active_days
        FROM qcli_user_activity_reports
        WHERE date BETWEEN DATE '{start_date.strftime('%Y-%m-%d')}'
            AND DATE '{end_date.strftime('%Y-%m-%d')}'
            {user_filter}
        """

        df = self.execute_athena_query(query)

        if not df.empty and df.iloc[0]["total_requests"]:
            result = {
                "total_requests": (
                    int(df.iloc[0]["total_requests"])
                    if df.iloc[0]["total_requests"]
                    else 0
                ),
                "total_agentic_requests": (
                    int(df.iloc[0]["total_agentic_requests"])
                    if df.iloc[0]["total_agentic_requests"]
                    else 0
                ),
                "total_cli_requests": (
                    int(df.iloc[0]["total_cli_requests"])
                    if df.iloc[0]["total_cli_requests"]
                    else 0
                ),
                "unique_users": (
                    int(df.iloc[0]["unique_users"])
                    if df.iloc[0]["unique_users"]
                    else 0
                ),
                "active_days": (
                    int(df.iloc[0]["active_days"]) if df.iloc[0]["active_days"] else 0
                ),
            }
            logger.info(f"QCli total summary: {result}")
            return result
        else:
            logger.warning("No data found for summary")
            return {
                "total_requests": 0,
                "total_agentic_requests": 0,
                "total_cli_requests": 0,
                "unique_users": 0,
                "active_days": 0,
            }

    def get_user_usage_analysis(
        self, start_date: datetime, end_date: datetime, user_pattern: str = None
    ) -> pd.DataFrame:
        """사용자별 사용량 분석"""
        logger.info(
            f"Getting QCli user usage analysis from {start_date} to {end_date}, user_pattern={user_pattern}"
        )

        user_filter = f"AND user_id LIKE '%{user_pattern}%'" if user_pattern else ""

        query = f"""
        SELECT
            user_id,
            SUM(CAST(request_count AS BIGINT)) as total_requests,
            SUM(CAST(agentic_request_count AS BIGINT)) as total_agentic_requests,
            SUM(CAST(code_suggestion_count AS BIGINT)) as total_code_suggestions,
            SUM(CAST(cli_request_count AS BIGINT)) as total_cli_requests,
            SUM(CAST(ide_request_count AS BIGINT)) as total_ide_requests,
            COUNT(DISTINCT date) as active_days,
            MIN(date) as first_activity,
            MAX(date) as last_activity
        FROM qcli_user_activity_reports
        WHERE date BETWEEN DATE '{start_date.strftime('%Y-%m-%d')}'
            AND DATE '{end_date.strftime('%Y-%m-%d')}'
            {user_filter}
        GROUP BY user_id
        ORDER BY total_requests DESC
        """

        return self.execute_athena_query(query)

    def get_daily_usage_pattern(
        self, start_date: datetime, end_date: datetime, user_pattern: str = None
    ) -> pd.DataFrame:
        """일별 사용 패턴"""
        logger.info(
            f"Getting QCli daily usage pattern from {start_date} to {end_date}, user_pattern={user_pattern}"
        )

        user_filter = f"AND user_id LIKE '%{user_pattern}%'" if user_pattern else ""

        query = f"""
        SELECT
            CAST(date AS VARCHAR) as date_str,
            SUM(CAST(request_count AS BIGINT)) as total_requests,
            SUM(CAST(agentic_request_count AS BIGINT)) as total_agentic_requests,
            SUM(CAST(cli_request_count AS BIGINT)) as total_cli_requests,
            COUNT(DISTINCT user_id) as unique_users
        FROM qcli_user_activity_reports
        WHERE date BETWEEN DATE '{start_date.strftime('%Y-%m-%d')}'
            AND DATE '{end_date.strftime('%Y-%m-%d')}'
            {user_filter}
        GROUP BY date
        ORDER BY date
        """

        return self.execute_athena_query(query)


    def get_feature_usage_stats(
        self, start_date: datetime, end_date: datetime, user_pattern: str = None
    ) -> pd.DataFrame:
        """기능별 사용 통계 (CLI vs IDE, Agentic vs Code Suggestion)"""
        logger.info(
            f"Getting QCli feature usage stats from {start_date} to {end_date}, user_pattern={user_pattern}"
        )

        user_filter = f"AND user_id LIKE '%{user_pattern}%'" if user_pattern else ""

        query = f"""
        SELECT
            'CLI Requests' as feature_type,
            SUM(CAST(cli_request_count AS BIGINT)) as total_count,
            COUNT(DISTINCT user_id) as unique_users
        FROM qcli_user_activity_reports
        WHERE date BETWEEN DATE '{start_date.strftime('%Y-%m-%d')}'
            AND DATE '{end_date.strftime('%Y-%m-%d')}'
            {user_filter}
        UNION ALL
        SELECT
            'IDE Requests' as feature_type,
            SUM(CAST(ide_request_count AS BIGINT)) as total_count,
            COUNT(DISTINCT user_id) as unique_users
        FROM qcli_user_activity_reports
        WHERE date BETWEEN DATE '{start_date.strftime('%Y-%m-%d')}'
            AND DATE '{end_date.strftime('%Y-%m-%d')}'
            {user_filter}
        UNION ALL
        SELECT
            'Agentic Requests' as feature_type,
            SUM(CAST(agentic_request_count AS BIGINT)) as total_count,
            COUNT(DISTINCT user_id) as unique_users
        FROM qcli_user_activity_reports
        WHERE date BETWEEN DATE '{start_date.strftime('%Y-%m-%d')}'
            AND DATE '{end_date.strftime('%Y-%m-%d')}'
            {user_filter}
        UNION ALL
        SELECT
            'Code Suggestions' as feature_type,
            SUM(CAST(code_suggestion_count AS BIGINT)) as total_count,
            COUNT(DISTINCT user_id) as unique_users
        FROM qcli_user_activity_reports
        WHERE date BETWEEN DATE '{start_date.strftime('%Y-%m-%d')}'
            AND DATE '{end_date.strftime('%Y-%m-%d')}'
            {user_filter}
        ORDER BY total_count DESC
        """

        return self.execute_athena_query(query)


def calculate_cost_for_dataframe(
    df: pd.DataFrame, model_col: str = "model_name", region: str = "default"
) -> pd.DataFrame:
    """DataFrame에 비용 컬럼 추가 (리전별 가격 반영)

    Args:
        df: 비용을 계산할 DataFrame
        model_col: 모델명이 있는 컬럼명
        region: AWS 리전 (예: us-east-1, ap-northeast-2)

    Returns:
        pd.DataFrame: 비용 컬럼이 추가된 DataFrame
    """
    logger.info(f"Calculating cost for DataFrame with {len(df)} rows, region: {region}")

    if df.empty:
        return df

    costs = []
    for _, row in df.iterrows():
        model = row.get(model_col, "")
        input_tokens = (
            int(row.get("total_input_tokens", 0))
            if row.get("total_input_tokens")
            else 0
        )
        output_tokens = (
            int(row.get("total_output_tokens", 0))
            if row.get("total_output_tokens")
            else 0
        )
        cost = get_model_cost(model, input_tokens, output_tokens, region)
        costs.append(cost)

    df["estimated_cost_usd"] = costs
    logger.info(f"Total cost calculated for region {region}: ${sum(costs):.4f}")
    return df


def main():
    logger.info("Starting Analytics Dashboard")

    st.set_page_config(
        page_title="AWS Analytics Dashboard", page_icon="📊", layout="wide"
    )

    st.title("📊 AWS Analytics Dashboard")
    st.markdown("**Athena 기반 실시간 사용량 분석 - Bedrock & Amazon Q CLI**")

    # 사이드바 설정
    st.sidebar.header("⚙️ 분석 설정")

    # 분석 유형 선택
    analysis_type = st.sidebar.radio(
        "분석 유형 선택",
        ["AWS Bedrock", "Amazon Q CLI"],
        index=0
    )

    # 리전 선택
    if analysis_type == "Amazon Q CLI":
        # Amazon Q CLI는 us-east-1에서만 사용자 활동 리포트 관리
        st.sidebar.info("ℹ️ Amazon Q CLI 사용자 활동 리포트는 us-east-1에서만 관리됩니다.")
        selected_region = "us-east-1"
        st.sidebar.text(f"리전: {selected_region} - {REGIONS[selected_region]} (고정)")
    else:
        # Bedrock은 모든 리전 선택 가능
        selected_region = st.sidebar.selectbox(
            "리전 선택",
            options=list(REGIONS.keys()),
            format_func=lambda x: f"{x} - {REGIONS[x]}",
            index=4,
        )

    logger.info(f"Selected region: {selected_region}, Analysis type: {analysis_type}")

    # 날짜 범위 선택
    st.sidebar.subheader("📅 날짜 범위 선택")

    col1, col2 = st.sidebar.columns(2)
    with col1:
        start_date = st.date_input(
            "시작 날짜",
            value=datetime.now() - timedelta(days=7),
            max_value=datetime.now(),
        )
    with col2:
        end_date = st.date_input(
            "종료 날짜", value=datetime.now(), max_value=datetime.now()
        )

    logger.info(f"Date range: {start_date} to {end_date}")

    # 분석 유형에 따라 다른 대시보드 렌더링
    if analysis_type == "AWS Bedrock":
        render_bedrock_analytics(selected_region, start_date, end_date)
    else:
        render_qcli_analytics(selected_region, start_date, end_date)


def render_bedrock_analytics(selected_region, start_date, end_date):
    """Bedrock 분석 대시보드 렌더링"""
    logger.info("Rendering Bedrock Analytics")

    # ARN 패턴 필터
    st.sidebar.subheader("🔍 ARN 패턴 필터 (선택사항)")
    arn_pattern = st.sidebar.text_input(
        "ARN 패턴",
        value="",
        placeholder="예: AmazonQ-CLI, q-cli",
        key="bedrock_arn_pattern",
        help="특정 ARN 패턴을 포함하는 사용자만 필터링합니다. 비워두면 전체 사용자를 표시합니다."
    )

    # 현재 로깅 설정 자동 조회
    tracker = BedrockAthenaTracker(region=selected_region)

    with st.spinner("현재 Model Invocation Logging 설정 확인 중..."):
        current_config = tracker.get_current_logging_config()

    # 설정 상태 표시
    if current_config["status"] == "enabled":
        st.success("✅ Model Invocation Logging이 활성화되어 있습니다!")

        col1, col2 = st.columns(2)
        with col1:
            st.info(f"📁 **S3 버킷**: 설정됨 ({selected_region})")
        with col2:
            st.info(f"📂 **프리픽스**: 설정됨")

    elif current_config["status"] == "disabled":
        st.error("❌ Model Invocation Logging이 비활성화되어 있습니다.")
        st.markdown("👇 먼저 설정을 활성화해주세요:")
        st.code("python setup_bedrock_analytics.py")
        logger.error("Model Invocation Logging is disabled")
        return

    else:
        st.warning(
            f"⚠️ 설정 확인 중 오류: {current_config.get('error', 'Unknown error')}"
        )
        logger.error(f"Error checking logging config: {current_config.get('error')}")
        return

    # 분석 실행
    if st.sidebar.button("🔍 데이터 분석", type="primary"):
        logger.info("Analysis button clicked")

        with st.spinner("Athena에서 데이터 분석 중..."):

            # ARN 패턴 정보 표시
            if arn_pattern:
                st.info(f"🔍 ARN 패턴 필터링 적용: '{arn_pattern}'")

            # 전체 요약
            summary = tracker.get_total_summary(start_date, end_date, arn_pattern if arn_pattern else None)

            st.header("📊 전체 요약")

            col1, col2, col3, col4 = st.columns(4)

            with col1:
                st.metric("총 API 호출", f"{summary['total_calls']:,}")

            with col2:
                st.metric("총 Input 토큰", f"{summary['total_input_tokens']:,}")

            with col3:
                st.metric("총 Output 토큰", f"{summary['total_output_tokens']:,}")

            # 모델별 통계로 총 비용 계산
            model_df = tracker.get_model_usage_stats(start_date, end_date, arn_pattern if arn_pattern else None)
            if not model_df.empty:
                model_df = calculate_cost_for_dataframe(model_df, region=selected_region)
                total_cost = model_df["estimated_cost_usd"].sum()
                summary["total_cost_usd"] = total_cost

            with col4:
                st.metric("총 비용", f"${summary['total_cost_usd']:.4f}")

            # 사용자별 분석
            st.header("👥 사용자/애플리케이션별 분석")

            user_df = tracker.get_user_cost_analysis(start_date, end_date, arn_pattern if arn_pattern else None)

            if not user_df.empty:
                # 숫자 컬럼 변환
                numeric_columns = [
                    "call_count",
                    "total_input_tokens",
                    "total_output_tokens",
                ]
                for col in numeric_columns:
                    if col in user_df.columns:
                        user_df[col] = pd.to_numeric(
                            user_df[col], errors="coerce"
                        ).fillna(0)

                # 비용 계산을 위한 임시 모델명 추가 (모델별 평균 사용)
                # 실제로는 각 사용자가 어떤 모델을 사용했는지 알아야 정확함
                # 여기서는 Claude 3 Haiku 기본 가격 사용 (리전별 가격 반영)
                costs = []
                for _, row in user_df.iterrows():
                    input_tokens = int(row.get("total_input_tokens", 0)) if row.get("total_input_tokens") else 0
                    output_tokens = int(row.get("total_output_tokens", 0)) if row.get("total_output_tokens") else 0
                    # Claude 3 Haiku를 기본 모델로 사용
                    cost = get_model_cost("claude-3-haiku-20240307", input_tokens, output_tokens, selected_region)
                    costs.append(cost)
                user_df["estimated_cost_usd"] = costs

                st.dataframe(user_df, use_container_width=True)

                # 비용 차트
                if len(user_df) > 0:
                    import plotly.express as px

                    fig = px.bar(
                        user_df.head(10),
                        x="user_or_app",
                        y="estimated_cost_usd",
                        title="상위 10명 사용자/애플리케이션별 비용",
                        labels={
                            "user_or_app": "사용자/애플리케이션",
                            "estimated_cost_usd": "비용 (USD)",
                        },
                    )
                    st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("분석할 데이터가 없습니다.")

            # 유저별 애플리케이션별 상세 분석
            st.header("📱 유저별 애플리케이션별 상세 분석")

            user_app_df = tracker.get_user_app_detail_analysis(start_date, end_date, arn_pattern if arn_pattern else None)

            if not user_app_df.empty:
                # 숫자 컬럼 변환
                numeric_columns = [
                    "call_count",
                    "total_input_tokens",
                    "total_output_tokens",
                ]
                for col in numeric_columns:
                    if col in user_app_df.columns:
                        user_app_df[col] = pd.to_numeric(
                            user_app_df[col], errors="coerce"
                        ).fillna(0)

                # 비용 계산 (리전별 가격 반영)
                user_app_df = calculate_cost_for_dataframe(user_app_df, region=selected_region)

                st.dataframe(user_app_df, use_container_width=True)
            else:
                st.info("분석할 데이터가 없습니다.")

            # 모델별 분석
            st.header("🤖 모델별 사용 통계")

            if not model_df.empty:
                # 숫자 컬럼 변환
                numeric_columns = [
                    "call_count",
                    "avg_input_tokens",
                    "avg_output_tokens",
                    "total_input_tokens",
                    "total_output_tokens",
                    "estimated_cost_usd",
                ]
                for col in numeric_columns:
                    if col in model_df.columns:
                        model_df[col] = pd.to_numeric(
                            model_df[col], errors="coerce"
                        ).fillna(0)

                st.dataframe(model_df, use_container_width=True)

                # 모델별 호출 비율 차트
                if len(model_df) > 0:
                    import plotly.express as px

                    fig = px.pie(
                        model_df,
                        values="call_count",
                        names="model_name",
                        title="모델별 호출 비율",
                    )
                    st.plotly_chart(fig, use_container_width=True)

            # 일별 사용 패턴
            st.header("📅 일별 사용 패턴")

            daily_df = tracker.get_daily_usage_pattern(start_date, end_date, arn_pattern if arn_pattern else None)

            if not daily_df.empty and len(daily_df) > 0:
                # 날짜 컬럼 생성
                daily_df["date"] = pd.to_datetime(
                    daily_df["year"]
                    + "-"
                    + daily_df["month"].str.zfill(2)
                    + "-"
                    + daily_df["day"].str.zfill(2)
                )

                # 숫자 컬럼 변환
                numeric_columns = ["call_count", "total_input_tokens", "total_output_tokens"]
                for col in numeric_columns:
                    if col in daily_df.columns:
                        daily_df[col] = pd.to_numeric(
                            daily_df[col], errors="coerce"
                        ).fillna(0)

                # 표시용 DataFrame 생성 (날짜를 문자열로 포맷)
                display_df = daily_df.copy()
                display_df["날짜"] = display_df["date"].dt.strftime("%Y-%m-%d")
                display_df = display_df[["날짜", "call_count", "total_input_tokens", "total_output_tokens"]]
                display_df.columns = ["날짜", "API 호출 수", "Input 토큰", "Output 토큰"]

                # 1. 테이블 먼저 표시
                st.dataframe(display_df, use_container_width=True)

                # 2. 그래프 표시
                import plotly.express as px
                import plotly.graph_objects as go

                # 일별 API 호출 패턴
                fig = px.line(
                    daily_df,
                    x="date",
                    y="call_count",
                    title="일별 API 호출 패턴",
                    labels={"date": "날짜", "call_count": "API 호출 수"},
                    markers=True
                )
                st.plotly_chart(fig, use_container_width=True)

                # 일별 토큰 사용량
                fig2 = go.Figure()
                fig2.add_trace(go.Scatter(
                    x=daily_df["date"],
                    y=daily_df["total_input_tokens"],
                    mode='lines+markers',
                    name='Input 토큰',
                    line=dict(color='blue')
                ))
                fig2.add_trace(go.Scatter(
                    x=daily_df["date"],
                    y=daily_df["total_output_tokens"],
                    mode='lines+markers',
                    name='Output 토큰',
                    line=dict(color='red')
                ))
                fig2.update_layout(
                    title="일별 토큰 사용량",
                    xaxis_title="날짜",
                    yaxis_title="토큰 수",
                    hovermode='x unified'
                )
                st.plotly_chart(fig2, use_container_width=True)
            else:
                st.warning("선택한 기간에 일별 사용 데이터가 없습니다.")

            # 시간대별 패턴
            st.header("⏰ 시간대별 사용 패턴")

            hourly_df = tracker.get_hourly_usage_pattern(start_date, end_date, arn_pattern if arn_pattern else None)

            if not hourly_df.empty and len(hourly_df) > 0:
                # 시간 컬럼 생성
                hourly_df["datetime"] = pd.to_datetime(
                    hourly_df["year"]
                    + "-"
                    + hourly_df["month"].str.zfill(2)
                    + "-"
                    + hourly_df["day"].str.zfill(2)
                    + " "
                    + hourly_df["hour"].str.zfill(2)
                    + ":00:00"
                )

                # 숫자 컬럼 변환
                numeric_columns = ["call_count", "total_input_tokens", "total_output_tokens"]
                for col in numeric_columns:
                    if col in hourly_df.columns:
                        hourly_df[col] = pd.to_numeric(
                            hourly_df[col], errors="coerce"
                        ).fillna(0)

                # 표시용 DataFrame 생성
                display_df = hourly_df.copy()
                display_df["시간"] = display_df["datetime"].dt.strftime("%Y-%m-%d %H:00")
                display_df = display_df[["시간", "call_count", "total_input_tokens", "total_output_tokens"]]
                display_df.columns = ["시간", "API 호출 수", "Input 토큰", "Output 토큰"]

                # 1. 테이블 먼저 표시
                st.dataframe(display_df, use_container_width=True)

                # 2. 그래프 표시
                import plotly.express as px
                import plotly.graph_objects as go

                # 시간대별 API 호출 패턴
                fig = px.line(
                    hourly_df,
                    x="datetime",
                    y="call_count",
                    title="시간대별 API 호출 패턴",
                    labels={"datetime": "시간", "call_count": "API 호출 수"},
                    markers=True
                )
                st.plotly_chart(fig, use_container_width=True)

                # 시간대별 토큰 사용량
                fig2 = go.Figure()
                fig2.add_trace(go.Scatter(
                    x=hourly_df["datetime"],
                    y=hourly_df["total_input_tokens"],
                    mode='lines+markers',
                    name='Input 토큰',
                    line=dict(color='blue')
                ))
                fig2.add_trace(go.Scatter(
                    x=hourly_df["datetime"],
                    y=hourly_df["total_output_tokens"],
                    mode='lines+markers',
                    name='Output 토큰',
                    line=dict(color='red')
                ))
                fig2.update_layout(
                    title="시간대별 토큰 사용량",
                    xaxis_title="시간",
                    yaxis_title="토큰 수",
                    hovermode='x unified'
                )
                st.plotly_chart(fig2, use_container_width=True)
            else:
                st.warning("선택한 기간에 시간대별 사용 데이터가 없습니다.")

    else:
        # 초기 화면
        st.info(
            "👈 왼쪽 사이드바에서 리전과 날짜 범위를 선택한 후 '데이터 분석' 버튼을 클릭하세요."
        )

        st.markdown("### 🛠️ 환경 설정 가이드")

        st.markdown("#### 1️⃣ 환경 요구사항")
        st.markdown(
            """
        **AWS 권한**: 다음 서비스에 대한 권한이 필요합니다
        - Bedrock: InvokeModel, Get/PutModelInvocationLoggingConfiguration
        - S3: GetObject, ListBucket, PutObject, CreateBucket
        - Athena: StartQueryExecution, GetQueryExecution, GetQueryResults
        - Glue: CreateDatabase, CreateTable, GetDatabase, GetTable

        **Python 환경**:
        - Python 3.8 이상
        - boto3, streamlit, pandas, plotly
        """
        )

        st.markdown("#### 2️⃣ 설치 방법")
        st.code(
            """
# 1. 패키지 설치
pip install -r requirements.txt

# 2. AWS 자격증명 설정
aws configure
# 또는 환경변수 설정
export AWS_ACCESS_KEY_ID=your_key
export AWS_SECRET_ACCESS_KEY=your_secret
export AWS_DEFAULT_REGION=us-east-1
        """,
            language="bash"
        )

        st.markdown("#### 3️⃣ 초기 설정 단계")
        st.code(
            """
# Step 1: Athena 분석 환경 구축
python setup_athena_bucket.py

# Step 2: Bedrock 로깅 설정 확인 및 활성화
python check_bedrock_logging.py
python setup_bedrock_logging.py

# Step 3: IAM Role 권한 검증
python verify_bedrock_permissions.py

# Step 4: 테스트 데이터 생성 (선택사항)
python generate_test_data.py

# Step 5: 대시보드 실행
streamlit run bedrock_tracker.py
        """,
            language="bash"
        )

        st.markdown("### 📋 지원 모델")
        st.markdown(
            """
        - **Claude 3**: Haiku, Sonnet, Opus
        - **Claude 3.5**: Haiku, Sonnet
        - **Claude 3.7**: Sonnet
        - **Claude 4**: Sonnet 4, Sonnet 4.5
        - **Claude 4.1**: Opus
        """
        )

        st.markdown("### 🌍 지원 리전")
        for region_id, region_name in REGIONS.items():
            st.markdown(f"- **{region_id}**: {region_name}")

    logger.info("Bedrock Dashboard rendering complete")


def render_qcli_analytics(selected_region, start_date, end_date):
    """Amazon Q CLI 분석 대시보드 렌더링"""
    logger.info("Rendering Amazon Q CLI Analytics")

    # 사용자 패턴 필터
    st.sidebar.subheader("🔍 사용자 ID 필터 (선택사항)")
    user_pattern = st.sidebar.text_input(
        "사용자 ID 패턴",
        value="",
        placeholder="예: user@example.com",
        key="qcli_user_pattern",
        help="특정 사용자 ID 패턴을 포함하는 사용자만 필터링합니다. 비워두면 전체 사용자를 표시합니다."
    )

    # QCli Tracker 초기화
    tracker = QCliAthenaTracker(region=selected_region)

    # 초기 정보 표시
    st.info(
        "📋 **Amazon Q CLI 사용량 분석**\n\n"
        "이 대시보드는 Amazon Q Developer의 사용자 활동 리포트 CSV 파일을 기반으로 합니다.\n"
        "CSV 리포트는 매일 자정(UTC)에 생성되며 S3 버킷에 저장됩니다."
    )

    # 분석 실행
    if st.sidebar.button("🔍 데이터 분석", type="primary", key="qcli_analyze"):
        logger.info("QCli Analysis button clicked")

        with st.spinner("Athena에서 Amazon Q CLI 데이터 분석 중..."):

            # 사용자 패턴 정보 표시
            if user_pattern:
                st.info(f"🔍 사용자 ID 패턴 필터링 적용: '{user_pattern}'")

            # 전체 요약
            summary = tracker.get_total_summary(
                start_date, end_date, user_pattern if user_pattern else None
            )

            st.header("📊 전체 요약")

            col1, col2, col3, col4, col5 = st.columns(5)

            with col1:
                st.metric("총 요청 수", f"{summary['total_requests']:,}")

            with col2:
                st.metric("Agentic 요청", f"{summary['total_agentic_requests']:,}")

            with col3:
                st.metric("CLI 요청", f"{summary['total_cli_requests']:,}")

            with col4:
                st.metric("활성 사용자", f"{summary['unique_users']:,}")

            with col5:
                st.metric("활동 일수", f"{summary['active_days']:,}")

            # 사용자별 분석
            st.header("👥 사용자별 분석")

            user_df = tracker.get_user_usage_analysis(
                start_date, end_date, user_pattern if user_pattern else None
            )

            if not user_df.empty:
                # 숫자 컬럼 변환
                numeric_columns = [
                    "total_requests",
                    "total_agentic_requests",
                    "total_code_suggestions",
                    "total_cli_requests",
                    "total_ide_requests",
                    "active_days",
                ]
                for col in numeric_columns:
                    if col in user_df.columns:
                        user_df[col] = pd.to_numeric(user_df[col], errors="coerce").fillna(0)

                st.dataframe(user_df, use_container_width=True)

                # 사용자별 요청 수 차트
                if len(user_df) > 0:
                    import plotly.express as px

                    fig = px.bar(
                        user_df.head(10),
                        x="user_id",
                        y="total_requests",
                        title="상위 10명 사용자별 총 요청 수",
                        labels={"user_id": "사용자 ID", "total_requests": "총 요청 수"},
                    )
                    fig.update_xaxes(tickangle=45)
                    st.plotly_chart(fig, use_container_width=True)

                    # Agentic vs Non-Agentic 요청 비교
                    fig2 = px.bar(
                        user_df.head(10),
                        x="user_id",
                        y=["total_agentic_requests", "total_code_suggestions"],
                        title="상위 10명 사용자별 요청 유형 분포",
                        labels={"value": "요청 수", "user_id": "사용자 ID"},
                        barmode="group",
                    )
                    fig2.update_xaxes(tickangle=45)
                    st.plotly_chart(fig2, use_container_width=True)
            else:
                st.info("분석할 사용자 데이터가 없습니다.")

            # 기능별 사용 통계
            st.header("📱 기능별 사용 통계")

            feature_df = tracker.get_feature_usage_stats(
                start_date, end_date, user_pattern if user_pattern else None
            )

            if not feature_df.empty:
                # 숫자 컬럼 변환
                for col in ["total_count", "unique_users"]:
                    if col in feature_df.columns:
                        feature_df[col] = pd.to_numeric(feature_df[col], errors="coerce").fillna(0)

                st.dataframe(feature_df, use_container_width=True)

                # 기능별 사용량 파이 차트
                if len(feature_df) > 0:
                    import plotly.express as px

                    fig = px.pie(
                        feature_df,
                        values="total_count",
                        names="feature_type",
                        title="기능별 사용 비율",
                    )
                    st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("분석할 기능 데이터가 없습니다.")

            # 일별 사용 패턴
            st.header("📅 일별 사용 패턴")

            daily_df = tracker.get_daily_usage_pattern(
                start_date, end_date, user_pattern if user_pattern else None
            )

            if not daily_df.empty and len(daily_df) > 0:
                # 숫자 컬럼 변환
                numeric_columns = [
                    "total_requests",
                    "total_agentic_requests",
                    "total_cli_requests",
                    "unique_users",
                ]
                for col in numeric_columns:
                    if col in daily_df.columns:
                        daily_df[col] = pd.to_numeric(daily_df[col], errors="coerce").fillna(0)

                # 날짜를 datetime으로 변환
                daily_df["date"] = pd.to_datetime(daily_df["date_str"])

                # 표시용 DataFrame 생성
                display_df = daily_df.copy()
                display_df["날짜"] = display_df["date"].dt.strftime("%Y-%m-%d")
                display_df = display_df[
                    ["날짜", "total_requests", "total_agentic_requests", "total_cli_requests", "unique_users"]
                ]
                display_df.columns = ["날짜", "총 요청 수", "Agentic 요청", "CLI 요청", "활성 사용자"]

                # 1. 테이블 먼저 표시
                st.dataframe(display_df, use_container_width=True)

                # 2. 그래프 표시
                import plotly.express as px
                import plotly.graph_objects as go

                # 일별 요청 패턴
                fig = px.line(
                    daily_df,
                    x="date",
                    y="total_requests",
                    title="일별 총 요청 수",
                    labels={"date": "날짜", "total_requests": "총 요청 수"},
                    markers=True,
                )
                st.plotly_chart(fig, use_container_width=True)

                # 일별 요청 유형별 분포
                fig2 = go.Figure()
                fig2.add_trace(
                    go.Scatter(
                        x=daily_df["date"],
                        y=daily_df["total_agentic_requests"],
                        mode="lines+markers",
                        name="Agentic 요청",
                        line=dict(color="blue"),
                    )
                )
                fig2.add_trace(
                    go.Scatter(
                        x=daily_df["date"],
                        y=daily_df["total_cli_requests"],
                        mode="lines+markers",
                        name="CLI 요청",
                        line=dict(color="green"),
                    )
                )
                fig2.update_layout(
                    title="일별 요청 유형별 분포",
                    xaxis_title="날짜",
                    yaxis_title="요청 수",
                    hovermode="x unified",
                )
                st.plotly_chart(fig2, use_container_width=True)

                # 일별 활성 사용자 수
                fig3 = px.bar(
                    daily_df,
                    x="date",
                    y="unique_users",
                    title="일별 활성 사용자 수",
                    labels={"date": "날짜", "unique_users": "활성 사용자 수"},
                )
                st.plotly_chart(fig3, use_container_width=True)
            else:
                st.warning("선택한 기간에 일별 사용 데이터가 없습니다.")

    else:
        # 초기 화면
        st.info(
            "👈 왼쪽 사이드바에서 리전과 날짜 범위를 선택한 후 '데이터 분석' 버튼을 클릭하세요."
        )

        st.markdown("### 🛠️ 환경 설정 가이드")

        st.markdown("#### 1️⃣ Amazon Q Developer 설정")
        st.markdown(
            """
        1. **Amazon Q Developer 콘솔**에서 "Collect granular metrics per user" 옵션 활성화
        2. **S3 버킷 지정**: 사용자 활동 리포트가 저장될 S3 버킷 설정
        3. **매일 자정(UTC)**에 CSV 리포트가 자동으로 생성됩니다
        """
        )

        st.markdown("#### 2️⃣ 분석 환경 구축")
        st.code(
            """
# Amazon Q CLI 분석 환경 설정
python setup_qcli_analytics.py --region us-east-1

# 대시보드 실행
streamlit run bedrock_tracker.py
        """,
            language="bash",
        )

        st.markdown("#### 3️⃣ 데이터 소스")
        st.markdown(
            """
        **CSV 리포트 (사용자 활동)**:
        - 일별 사용자별 요청 수
        - Agentic 요청 수
        - CLI/IDE 요청 수
        - 코드 제안 수
        """
        )

        st.markdown("### 📋 주요 메트릭")
        st.markdown(
            """
        - **총 요청 수**: 전체 Amazon Q 요청 수
        - **Agentic 요청**: Q&A 챗 또는 agentic 코딩 상호작용
        - **CLI 요청**: Amazon Q CLI를 통한 요청
        - **IDE 요청**: IDE 플러그인을 통한 요청
        - **코드 제안**: 코드 자동 완성 제안 수
        """
        )

    logger.info("QCli Dashboard rendering complete")


if __name__ == "__main__":
    main()
