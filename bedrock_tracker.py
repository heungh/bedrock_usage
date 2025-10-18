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

# AWS Bedrock 모델 가격 테이블 (모든 리전 동일)
MODEL_PRICING = {
    # Claude 3 모델
    "claude-3-haiku-20240307": {
        "input": 0.00025 / 1000,  # per token
        "output": 0.00125 / 1000,
    },
    "claude-3-sonnet-20240229": {"input": 0.003 / 1000, "output": 0.015 / 1000},
    "claude-3-opus-20240229": {"input": 0.015 / 1000, "output": 0.075 / 1000},
    # Claude 3.5 모델
    "claude-3-5-haiku-20241022": {"input": 0.0008 / 1000, "output": 0.004 / 1000},
    "claude-3-5-sonnet-20240620": {"input": 0.003 / 1000, "output": 0.015 / 1000},
    "claude-3-5-sonnet-20241022": {"input": 0.003 / 1000, "output": 0.015 / 1000},
    # Claude 3.7 모델
    "claude-3-7-sonnet-20250219": {"input": 0.003 / 1000, "output": 0.015 / 1000},
    # Claude 4 모델
    "claude-sonnet-4-20250514": {"input": 0.003 / 1000, "output": 0.015 / 1000},
    "claude-sonnet-4-5-20250929": {"input": 0.003 / 1000, "output": 0.015 / 1000},
    "claude-opus-4-20250514": {"input": 0.015 / 1000, "output": 0.075 / 1000},
    "claude-opus-4-1-20250808": {"input": 0.015 / 1000, "output": 0.075 / 1000},
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


def get_model_cost(model_id: str, input_tokens: int, output_tokens: int) -> float:
    """모델별 비용 계산"""
    logger.debug(
        f"Calculating cost for model: {model_id}, input: {input_tokens}, output: {output_tokens}"
    )

    # 모델 ID에서 모델명 추출 (예: us.anthropic.claude-3-haiku-20240307-v1:0 -> claude-3-haiku-20240307)
    model_name = model_id.split(".")[-1].split("-v")[0] if "." in model_id else model_id

    # 가격 테이블에서 찾기
    for key, pricing in MODEL_PRICING.items():
        if key in model_name:
            cost = (input_tokens * pricing["input"]) + (
                output_tokens * pricing["output"]
            )
            logger.debug(f"Model: {key}, Cost: ${cost:.6f}")
            return cost

    # 기본 가격 (Claude 3 Haiku)
    logger.warning(f"Unknown model: {model_id}, using default pricing")
    default_cost = (input_tokens * 0.00025 / 1000) + (output_tokens * 0.00125 / 1000)
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
        self, start_date: datetime, end_date: datetime
    ) -> pd.DataFrame:
        """사용자별 비용 분석"""
        logger.info(f"Getting user cost analysis from {start_date} to {end_date}")

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
        WHERE year >= '{start_date.year}'
            AND month >= '{start_date.month:02d}'
            AND day >= '{start_date.day:02d}'
            AND year <= '{end_date.year}'
            AND month <= '{end_date.month:02d}'
            AND day <= '{end_date.day:02d}'
        GROUP BY identity.arn
        ORDER BY call_count DESC
        """

        return self.execute_athena_query(query)

    def get_user_app_detail_analysis(
        self, start_date: datetime, end_date: datetime
    ) -> pd.DataFrame:
        """유저별 애플리케이션별 상세 분석"""
        logger.info(f"Getting user-app detail analysis from {start_date} to {end_date}")

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
        WHERE year >= '{start_date.year}'
            AND month >= '{start_date.month:02d}'
            AND day >= '{start_date.day:02d}'
            AND year <= '{end_date.year}'
            AND month <= '{end_date.month:02d}'
            AND day <= '{end_date.day:02d}'
        GROUP BY identity.arn, modelId
        ORDER BY user_or_app, call_count DESC
        """

        return self.execute_athena_query(query)

    def get_hourly_usage_pattern(
        self, start_date: datetime, end_date: datetime
    ) -> pd.DataFrame:
        """시간별 사용 패턴"""
        logger.info(f"Getting hourly usage pattern from {start_date} to {end_date}")

        query = f"""
        SELECT
            year, month, day, hour,
            COUNT(*) as call_count,
            SUM(CAST(input.inputTokenCount AS BIGINT)) as total_input_tokens,
            SUM(CAST(output.outputTokenCount AS BIGINT)) as total_output_tokens
        FROM bedrock_invocation_logs
        WHERE year >= '{start_date.year}'
            AND month >= '{start_date.month:02d}'
            AND day >= '{start_date.day:02d}'
            AND year <= '{end_date.year}'
            AND month <= '{end_date.month:02d}'
            AND day <= '{end_date.day:02d}'
        GROUP BY year, month, day, hour
        ORDER BY year, month, day, hour
        """

        return self.execute_athena_query(query)

    def get_daily_usage_pattern(
        self, start_date: datetime, end_date: datetime
    ) -> pd.DataFrame:
        """일별 사용 패턴"""
        logger.info(f"Getting daily usage pattern from {start_date} to {end_date}")

        query = f"""
        SELECT
            year, month, day,
            COUNT(*) as call_count,
            SUM(CAST(input.inputTokenCount AS BIGINT)) as total_input_tokens,
            SUM(CAST(output.outputTokenCount AS BIGINT)) as total_output_tokens
        FROM bedrock_invocation_logs
        WHERE year >= '{start_date.year}'
            AND month >= '{start_date.month:02d}'
            AND day >= '{start_date.day:02d}'
            AND year <= '{end_date.year}'
            AND month <= '{end_date.month:02d}'
            AND day <= '{end_date.day:02d}'
        GROUP BY year, month, day
        ORDER BY year, month, day
        """

        return self.execute_athena_query(query)

    def get_model_usage_stats(
        self, start_date: datetime, end_date: datetime
    ) -> pd.DataFrame:
        """모델별 사용 통계"""
        logger.info(f"Getting model usage stats from {start_date} to {end_date}")

        query = f"""
        SELECT
            regexp_extract(modelId, '([^/]+)$') as model_name,
            COUNT(*) as call_count,
            AVG(CAST(input.inputTokenCount AS DOUBLE)) as avg_input_tokens,
            AVG(CAST(output.outputTokenCount AS DOUBLE)) as avg_output_tokens,
            SUM(CAST(input.inputTokenCount AS BIGINT)) as total_input_tokens,
            SUM(CAST(output.outputTokenCount AS BIGINT)) as total_output_tokens
        FROM bedrock_invocation_logs
        WHERE year >= '{start_date.year}'
            AND month >= '{start_date.month:02d}'
            AND day >= '{start_date.day:02d}'
            AND year <= '{end_date.year}'
            AND month <= '{end_date.month:02d}'
            AND day <= '{end_date.day:02d}'
        GROUP BY modelId
        ORDER BY call_count DESC
        """

        return self.execute_athena_query(query)

    def get_total_summary(self, start_date: datetime, end_date: datetime) -> Dict:
        """전체 요약 통계"""
        logger.info(f"Getting total summary from {start_date} to {end_date}")

        query = f"""
        SELECT
            COUNT(*) as total_calls,
            SUM(CAST(input.inputTokenCount AS BIGINT)) as total_input_tokens,
            SUM(CAST(output.outputTokenCount AS BIGINT)) as total_output_tokens
        FROM bedrock_invocation_logs
        WHERE year >= '{start_date.year}'
            AND month >= '{start_date.month:02d}'
            AND day >= '{start_date.day:02d}'
            AND year <= '{end_date.year}'
            AND month <= '{end_date.month:02d}'
            AND day <= '{end_date.day:02d}'
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


def calculate_cost_for_dataframe(
    df: pd.DataFrame, model_col: str = "model_name"
) -> pd.DataFrame:
    """DataFrame에 비용 컬럼 추가"""
    logger.info(f"Calculating cost for DataFrame with {len(df)} rows")

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
        cost = get_model_cost(model, input_tokens, output_tokens)
        costs.append(cost)

    df["estimated_cost_usd"] = costs
    logger.info(f"Total cost calculated: ${sum(costs):.4f}")
    return df


def main():
    logger.info("Starting Bedrock Analytics Dashboard")

    st.set_page_config(
        page_title="Bedrock Analytics Dashboard", page_icon="📊", layout="wide"
    )

    st.title("📊 AWS Bedrock Analytics Dashboard")
    st.markdown("**Athena 기반 실시간 사용량 분석**")

    # 사이드바 설정
    st.sidebar.header("⚙️ 분석 설정")

    # 리전 선택
    selected_region = st.sidebar.selectbox(
        "리전 선택",
        options=list(REGIONS.keys()),
        format_func=lambda x: f"{x} - {REGIONS[x]}",
        index=4,
    )
    logger.info(f"Selected region: {selected_region}")

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

    # 분석 실행
    if st.sidebar.button("🔍 데이터 분석", type="primary"):
        logger.info("Analysis button clicked")

        with st.spinner("Athena에서 데이터 분석 중..."):

            # 전체 요약
            summary = tracker.get_total_summary(start_date, end_date)

            st.header("📊 전체 요약")

            col1, col2, col3, col4 = st.columns(4)

            with col1:
                st.metric("총 API 호출", f"{summary['total_calls']:,}")

            with col2:
                st.metric("총 Input 토큰", f"{summary['total_input_tokens']:,}")

            with col3:
                st.metric("총 Output 토큰", f"{summary['total_output_tokens']:,}")

            # 모델별 통계로 총 비용 계산
            model_df = tracker.get_model_usage_stats(start_date, end_date)
            if not model_df.empty:
                model_df = calculate_cost_for_dataframe(model_df)
                total_cost = model_df["estimated_cost_usd"].sum()
                summary["total_cost_usd"] = total_cost

            with col4:
                st.metric("총 비용", f"${summary['total_cost_usd']:.4f}")

            # 사용자별 분석
            st.header("👥 사용자/애플리케이션별 분석")

            user_df = tracker.get_user_cost_analysis(start_date, end_date)

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
                # 여기서는 Claude 3 Haiku 기본 가격 사용
                user_df["estimated_cost_usd"] = (
                    user_df["total_input_tokens"] * 0.00025 / 1000
                    + user_df["total_output_tokens"] * 0.00125 / 1000
                )

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

            user_app_df = tracker.get_user_app_detail_analysis(start_date, end_date)

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

                # 비용 계산
                user_app_df = calculate_cost_for_dataframe(user_app_df)

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

            daily_df = tracker.get_daily_usage_pattern(start_date, end_date)

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
                daily_df["call_count"] = pd.to_numeric(
                    daily_df["call_count"], errors="coerce"
                ).fillna(0)
                daily_df["total_input_tokens"] = pd.to_numeric(
                    daily_df["total_input_tokens"], errors="coerce"
                ).fillna(0)
                daily_df["total_output_tokens"] = pd.to_numeric(
                    daily_df["total_output_tokens"], errors="coerce"
                ).fillna(0)

                import plotly.express as px

                fig = px.line(
                    daily_df,
                    x="date",
                    y="call_count",
                    title="일별 API 호출 패턴",
                    labels={"date": "날짜", "call_count": "API 호출 수"},
                )
                st.plotly_chart(fig, use_container_width=True)

                # 일별 토큰 사용량
                fig2 = px.line(
                    daily_df,
                    x="date",
                    y=["total_input_tokens", "total_output_tokens"],
                    title="일별 토큰 사용량",
                    labels={
                        "date": "날짜",
                        "value": "토큰 수",
                        "variable": "토큰 종류",
                    },
                )
                st.plotly_chart(fig2, use_container_width=True)

            # 시간대별 패턴
            st.header("⏰ 시간대별 사용 패턴")

            hourly_df = tracker.get_hourly_usage_pattern(start_date, end_date)

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
                hourly_df["call_count"] = pd.to_numeric(
                    hourly_df["call_count"], errors="coerce"
                ).fillna(0)

                import plotly.express as px

                fig = px.line(
                    hourly_df,
                    x="datetime",
                    y="call_count",
                    title="시간대별 API 호출 패턴",
                    labels={"datetime": "시간", "call_count": "API 호출 수"},
                )
                st.plotly_chart(fig, use_container_width=True)

    else:
        # 초기 화면
        st.info(
            "👈 왼쪽 사이드바에서 리전과 날짜 범위를 선택한 후 '데이터 분석' 버튼을 클릭하세요."
        )

        st.markdown("### 🚀 Athena 기반 분석의 장점")

        st.markdown(
            """
        - **🚀 고성능**: 페타바이트 규모 데이터 처리 가능
        - **💰 비용 효율적**: 스캔한 데이터량만큼만 과금
        - **📊 SQL 쿼리**: 표준 SQL로 복잡한 분석 가능
        - **🔗 QuickSight 연동**: 실시간 대시보드 구축 가능
        - **📈 확장성**: 데이터 증가에 따른 성능 저하 없음
        """
        )

        st.markdown("### 🛠️ 설정이 필요한 경우")

        st.code(
            """
# Bedrock Analytics 통합 설정 실행
python setup_bedrock_analytics.py

# 또는 커스텀 버킷명으로 설정
python setup_bedrock_analytics.py --bucket my-bedrock-logs
        """
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

    logger.info("Dashboard rendering complete")


if __name__ == "__main__":
    main()
