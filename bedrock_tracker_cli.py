#!/usr/bin/env python3
"""
CLI 버전의 Bedrock Usage Tracker - Athena 기반
터미널에서 사용 가능한 다양한 분석 기능 제공
"""

import boto3
import pandas as pd
from datetime import datetime, timedelta
import argparse
import time
from typing import Dict
import logging
from pathlib import Path
import json
import sys

# 로깅 설정
def setup_logger():
    """디버깅용 로거 설정"""
    log_dir = Path(__file__).parent / 'log'
    log_dir.mkdir(exist_ok=True)

    log_filename = log_dir / f"bedrock_tracker_cli_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

    logger = logging.getLogger('BedrockTrackerCLI')
    logger.setLevel(logging.DEBUG)

    # 파일 핸들러
    file_handler = logging.FileHandler(log_filename, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)

    # 포맷 설정
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s'
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
    model_name = model_id.split('.')[-1].split('-v')[0] if '.' in model_id else model_id

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
    def __init__(self, region='us-east-1'):
        logger.info(f"Initializing BedrockAthenaTracker with region: {region}")
        self.region = region
        self.athena = boto3.client('athena', region_name=region)
        sts_client = boto3.client('sts', region_name=region)
        self.account_id = sts_client.get_caller_identity()['Account']
        # bedrock_tracker.py와 동일한 버킷명 사용
        self.results_bucket = f'bedrock-analytics-{self.account_id}-{self.region}'
        logger.info(f"Account ID: {self.account_id}, Results bucket: {self.results_bucket}")

    def get_current_logging_config(self) -> Dict:
        """현재 설정된 Model Invocation Logging 정보 조회"""
        logger.info("Getting current logging configuration")
        try:
            bedrock = boto3.client('bedrock', region_name=self.region)
            response = bedrock.get_model_invocation_logging_configuration()

            if 'loggingConfig' in response:
                config = response['loggingConfig']

                if 's3Config' in config:
                    result = {
                        'type': 's3',
                        'bucket': config['s3Config'].get('bucketName', ''),
                        'prefix': config['s3Config'].get('keyPrefix', ''),
                        'status': 'enabled'
                    }
                    logger.info(f"Logging config: {result}")
                    return result

            logger.warning("Logging is disabled")
            return {'status': 'disabled'}

        except Exception as e:
            logger.error(f"Error getting logging config: {str(e)}")
            return {'status': 'error', 'error': str(e)}

    def execute_athena_query(self, query: str, database: str = 'bedrock_analytics') -> pd.DataFrame:
        """Athena 쿼리 실행 및 결과 반환"""
        logger.info(f"Executing Athena query on database: {database}")
        logger.debug(f"Query: {query}")

        try:
            response = self.athena.start_query_execution(
                QueryString=query,
                QueryExecutionContext={'Database': database},
                ResultConfiguration={
                    'OutputLocation': f's3://{self.results_bucket}/query-results/'
                }
            )

            query_id = response['QueryExecutionId']
            logger.info(f"Query execution started: {query_id}")

            max_wait = 60
            for i in range(max_wait):
                result = self.athena.get_query_execution(QueryExecutionId=query_id)
                status = result['QueryExecution']['Status']['State']

                if status == 'SUCCEEDED':
                    logger.info(f"Query succeeded in {i+1} seconds")
                    break
                elif status in ['FAILED', 'CANCELLED']:
                    error = result['QueryExecution']['Status'].get('StateChangeReason', 'Unknown error')
                    logger.error(f"Query failed: {error}")
                    raise Exception(f"Query failed: {error}")

                time.sleep(1)
            else:
                logger.error("Query timeout")
                raise Exception("Query timeout")

            result_response = self.athena.get_query_results(QueryExecutionId=query_id)

            columns = [col['Label'] for col in result_response['ResultSet']['ResultSetMetadata']['ColumnInfo']]
            rows = []

            for row in result_response['ResultSet']['Rows'][1:]:
                row_data = [field.get('VarCharValue', '') for field in row['Data']]
                rows.append(row_data)

            df = pd.DataFrame(rows, columns=columns)
            logger.info(f"Query returned {len(df)} rows")
            return df

        except Exception as e:
            logger.error(f"Athena query execution failed: {str(e)}")
            print(f"❌ Athena 쿼리 실행 실패: {str(e)}", file=sys.stderr)
            return pd.DataFrame()

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
                'total_calls': int(df.iloc[0]['total_calls']) if df.iloc[0]['total_calls'] else 0,
                'total_input_tokens': int(df.iloc[0]['total_input_tokens']) if df.iloc[0]['total_input_tokens'] else 0,
                'total_output_tokens': int(df.iloc[0]['total_output_tokens']) if df.iloc[0]['total_output_tokens'] else 0,
                'total_cost_usd': 0.0
            }
            logger.info(f"Total summary: {result}")
            return result
        else:
            logger.warning("No data found for summary")
            return {'total_calls': 0, 'total_input_tokens': 0, 'total_output_tokens': 0, 'total_cost_usd': 0.0}

    def get_user_cost_analysis(self, start_date: datetime, end_date: datetime, arn_pattern: str = None) -> pd.DataFrame:
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

    def get_user_app_detail_analysis(self, start_date: datetime, end_date: datetime, arn_pattern: str = None) -> pd.DataFrame:
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

    def get_model_usage_stats(self, start_date: datetime, end_date: datetime, arn_pattern: str = None) -> pd.DataFrame:
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

    def get_daily_usage_pattern(self, start_date: datetime, end_date: datetime, arn_pattern: str = None) -> pd.DataFrame:
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

    def get_hourly_usage_pattern(self, start_date: datetime, end_date: datetime, arn_pattern: str = None) -> pd.DataFrame:
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


def calculate_cost_for_dataframe(df: pd.DataFrame, model_col: str = 'model_name', region: str = "default") -> pd.DataFrame:
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
        model = row.get(model_col, '')
        input_tokens = int(row.get('total_input_tokens', 0)) if row.get('total_input_tokens') else 0
        output_tokens = int(row.get('total_output_tokens', 0)) if row.get('total_output_tokens') else 0
        cost = get_model_cost(model, input_tokens, output_tokens, region)
        costs.append(cost)

    df['estimated_cost_usd'] = costs
    logger.info(f"Total cost calculated for region {region}: ${sum(costs):.4f}")
    return df


def print_summary(summary: Dict):
    """전체 요약 출력"""
    print("\n" + "="*80)
    print("📊 전체 요약".center(80))
    print("="*80)
    print(f"  총 API 호출:       {summary['total_calls']:>15,}")
    print(f"  총 Input 토큰:     {summary['total_input_tokens']:>15,}")
    print(f"  총 Output 토큰:    {summary['total_output_tokens']:>15,}")
    print(f"  총 비용 (USD):     ${summary['total_cost_usd']:>14.4f}")
    print("="*80 + "\n")


def print_dataframe_table(df: pd.DataFrame, title: str, max_rows: int = 20):
    """DataFrame을 테이블 형식으로 출력"""
    if df.empty:
        print(f"\n{title}: 데이터 없음\n")
        return

    print(f"\n{'='*80}")
    print(f"{title}".center(80))
    print("="*80)

    # pandas 출력 옵션 설정
    pd.set_option('display.max_rows', max_rows)
    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', 1000)
    pd.set_option('display.colheader_justify', 'left')

    print(df.head(max_rows).to_string(index=False))

    if len(df) > max_rows:
        print(f"\n... ({len(df) - max_rows} more rows)")

    print("="*80 + "\n")


def save_to_csv(df: pd.DataFrame, filename: str):
    """CSV로 저장"""
    report_dir = Path(__file__).parent / 'report'
    report_dir.mkdir(exist_ok=True)

    filepath = report_dir / filename
    df.to_csv(filepath, index=False, encoding='utf-8-sig')
    print(f"✅ CSV 저장: {filepath}")


def save_to_json(data: dict, filename: str):
    """JSON으로 저장"""
    report_dir = Path(__file__).parent / 'report'
    report_dir.mkdir(exist_ok=True)

    filepath = report_dir / filename
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"✅ JSON 저장: {filepath}")


def main():
    parser = argparse.ArgumentParser(description='Bedrock Usage Tracker CLI - Athena 기반')
    parser.add_argument('--days', type=int, default=7, help='분석할 일수 (기본값: 7일)')
    parser.add_argument('--region', default='us-east-1',
                       choices=list(REGIONS.keys()),
                       help='AWS 리전 (기본값: us-east-1)')
    parser.add_argument('--start-date', help='시작 날짜 (YYYY-MM-DD)')
    parser.add_argument('--end-date', help='종료 날짜 (YYYY-MM-DD)')
    parser.add_argument('--analysis',
                       choices=['all', 'summary', 'user', 'user-app', 'model', 'daily', 'hourly'],
                       default='all',
                       help='분석 유형 (기본값: all)')
    parser.add_argument('--format',
                       choices=['terminal', 'csv', 'json'],
                       default='terminal',
                       help='출력 형식 (기본값: terminal)')
    parser.add_argument('--max-rows', type=int, default=20,
                       help='테이블 최대 행 수 (기본값: 20)')
    parser.add_argument('--arn-pattern', type=str, default='',
                       help='ARN 패턴 필터 (예: AmazonQ-CLI, q-cli)')

    args = parser.parse_args()

    print("🚀 Bedrock Analytics CLI (Athena 기반)")
    print("="*80)

    # 날짜 범위 설정
    if args.start_date and args.end_date:
        start_date = datetime.strptime(args.start_date, '%Y-%m-%d')
        end_date = datetime.strptime(args.end_date, '%Y-%m-%d')
    else:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=args.days)

    arn_pattern = args.arn_pattern if args.arn_pattern else None

    print(f"📅 분석 기간: {start_date.strftime('%Y-%m-%d')} ~ {end_date.strftime('%Y-%m-%d')}")
    print(f"🌍 리전: {args.region} ({REGIONS[args.region]})")
    print(f"📋 분석 유형: {args.analysis}")
    print(f"📄 출력 형식: {args.format}")
    if arn_pattern:
        print(f"🔍 ARN 패턴 필터: '{arn_pattern}'")
    print()

    # Tracker 초기화
    tracker = BedrockAthenaTracker(region=args.region)

    # 로깅 설정 확인
    print("🔍 Model Invocation Logging 설정 확인 중...")
    current_config = tracker.get_current_logging_config()

    if current_config['status'] == 'enabled':
        print("✅ Model Invocation Logging이 활성화되어 있습니다!")
        print(f"   S3 버킷: {current_config['bucket']}")
        print(f"   프리픽스: {current_config['prefix']}")
    elif current_config['status'] == 'disabled':
        print("❌ Model Invocation Logging이 비활성화되어 있습니다.")
        print("💡 먼저 설정을 활성화해주세요:")
        print("   python setup_bedrock_logging.py")
        return
    else:
        print(f"⚠️ 설정 확인 중 오류: {current_config.get('error', 'Unknown error')}")
        return

    print()
    print("📊 데이터 분석 중...\n")

    # 데이터 수집
    results = {}

    if args.analysis in ['all', 'summary']:
        summary = tracker.get_total_summary(start_date, end_date, arn_pattern if arn_pattern else None)
        results['summary'] = summary

    if args.analysis in ['all', 'user']:
        user_df = tracker.get_user_cost_analysis(start_date, end_date, arn_pattern if arn_pattern else None)
        if not user_df.empty:
            # 숫자 변환 및 비용 계산
            for col in ['call_count', 'total_input_tokens', 'total_output_tokens']:
                if col in user_df.columns:
                    user_df[col] = pd.to_numeric(user_df[col], errors='coerce').fillna(0)
            # 리전별 가격으로 비용 계산 (사용자별 분석은 모델 정보가 없으므로 기본 Haiku 가격 사용)
            costs = []
            for _, row in user_df.iterrows():
                input_tokens = int(row.get('total_input_tokens', 0)) if row.get('total_input_tokens') else 0
                output_tokens = int(row.get('total_output_tokens', 0)) if row.get('total_output_tokens') else 0
                # Claude 3 Haiku를 기본 모델로 사용
                cost = get_model_cost('claude-3-haiku-20240307', input_tokens, output_tokens, args.region)
                costs.append(cost)
            user_df['estimated_cost_usd'] = costs
        results['user'] = user_df

    if args.analysis in ['all', 'user-app']:
        user_app_df = tracker.get_user_app_detail_analysis(start_date, end_date, arn_pattern if arn_pattern else None)
        if not user_app_df.empty:
            for col in ['call_count', 'total_input_tokens', 'total_output_tokens']:
                if col in user_app_df.columns:
                    user_app_df[col] = pd.to_numeric(user_app_df[col], errors='coerce').fillna(0)
            user_app_df = calculate_cost_for_dataframe(user_app_df, region=args.region)
        results['user_app'] = user_app_df

    if args.analysis in ['all', 'model']:
        model_df = tracker.get_model_usage_stats(start_date, end_date, arn_pattern if arn_pattern else None)
        if not model_df.empty:
            for col in ['call_count', 'avg_input_tokens', 'avg_output_tokens',
                       'total_input_tokens', 'total_output_tokens']:
                if col in model_df.columns:
                    model_df[col] = pd.to_numeric(model_df[col], errors='coerce').fillna(0)
            model_df = calculate_cost_for_dataframe(model_df, region=args.region)
            # 총 비용 업데이트
            if 'summary' in results:
                results['summary']['total_cost_usd'] = model_df['estimated_cost_usd'].sum()
        results['model'] = model_df

    if args.analysis in ['all', 'daily']:
        daily_df = tracker.get_daily_usage_pattern(start_date, end_date, arn_pattern if arn_pattern else None)
        if not daily_df.empty:
            for col in ['call_count', 'total_input_tokens', 'total_output_tokens']:
                if col in daily_df.columns:
                    daily_df[col] = pd.to_numeric(daily_df[col], errors='coerce').fillna(0)
        results['daily'] = daily_df

    if args.analysis in ['all', 'hourly']:
        hourly_df = tracker.get_hourly_usage_pattern(start_date, end_date, arn_pattern if arn_pattern else None)
        if not hourly_df.empty:
            for col in ['call_count', 'total_input_tokens', 'total_output_tokens']:
                if col in hourly_df.columns:
                    hourly_df[col] = pd.to_numeric(hourly_df[col], errors='coerce').fillna(0)
        results['hourly'] = hourly_df

    # 출력 형식에 따라 결과 출력
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

    if args.format == 'terminal':
        # 터미널 출력
        if 'summary' in results:
            print_summary(results['summary'])

        if 'user' in results and not results['user'].empty:
            print_dataframe_table(results['user'], "👥 사용자/애플리케이션별 분석", args.max_rows)

        if 'user_app' in results and not results['user_app'].empty:
            print_dataframe_table(results['user_app'], "📱 유저별 애플리케이션별 상세 분석", args.max_rows)

        if 'model' in results and not results['model'].empty:
            print_dataframe_table(results['model'], "🤖 모델별 사용 통계", args.max_rows)

        if 'daily' in results and not results['daily'].empty:
            print_dataframe_table(results['daily'], "📅 일별 사용 패턴", args.max_rows)

        if 'hourly' in results and not results['hourly'].empty:
            print_dataframe_table(results['hourly'], "⏰ 시간별 사용 패턴", args.max_rows)

    elif args.format == 'csv':
        # CSV 저장
        for key, data in results.items():
            if key == 'summary':
                continue
            if isinstance(data, pd.DataFrame) and not data.empty:
                filename = f"bedrock_{key}_{args.region}_{timestamp}.csv"
                save_to_csv(data, filename)

    elif args.format == 'json':
        # JSON 저장
        json_data = {}

        if 'summary' in results:
            json_data['summary'] = results['summary']

        for key, data in results.items():
            if key == 'summary':
                continue
            if isinstance(data, pd.DataFrame) and not data.empty:
                json_data[key] = data.to_dict(orient='records')

        filename = f"bedrock_analysis_{args.region}_{timestamp}.json"
        save_to_json(json_data, filename)

    print("\n✅ 분석 완료!")
    logger.info("Analysis completed successfully")


if __name__ == "__main__":
    main()
