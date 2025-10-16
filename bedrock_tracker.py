import streamlit as st
import boto3
import pandas as pd
from datetime import datetime, timedelta
import json
from typing import Dict, List, Tuple

class BedrockUsageTracker:
    def __init__(self):
        self.regions = ['us-east-1', 'us-west-2', 'eu-west-1', 'ap-northeast-1', 'ap-southeast-1']
        # 실제 사용되는 모델은 CloudTrail에서 동적으로 추출합니다
        self.discovered_models = set()
        self.discovered_applications = set()
        self.pricing = {
            'us-east-1': {'input': 0.003, 'output': 0.015},
            'us-west-2': {'input': 0.003, 'output': 0.015},
            'eu-west-1': {'input': 0.0035, 'output': 0.0175},
            'ap-northeast-1': {'input': 0.004, 'output': 0.02},
            'ap-southeast-1': {'input': 0.004, 'output': 0.02}
        }

    def extract_model_id_from_event(self, event: Dict) -> str:
        """CloudTrail 이벤트에서 모델 ID 추출"""
        try:
            # CloudTrailEvent는 JSON 문자열로 되어있을 수 있음
            if 'CloudTrailEvent' in event:
                event_data = json.loads(event['CloudTrailEvent'])
                if 'requestParameters' in event_data and 'modelId' in event_data['requestParameters']:
                    return event_data['requestParameters']['modelId']

            # Resources에서도 확인
            if 'Resources' in event:
                for resource in event['Resources']:
                    if resource.get('ResourceType') == 'AWS::Bedrock::Model':
                        return resource.get('ResourceName', '')
        except Exception as e:
            pass
        return 'Unknown'

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

    def get_cloudtrail_events(self, regions: List[str], start_time: datetime, end_time: datetime) -> List[Dict]:
        events = []
        event_names = ['InvokeModel', 'InvokeModelWithResponseStream']

        for region in regions:
            try:
                client = boto3.client('cloudtrail', region_name=region)

                # CloudTrail lookup_events는 한 번에 하나의 AttributeKey만 지원
                # 각 EventName별로 별도 조회
                for event_name in event_names:
                    try:
                        response = client.lookup_events(
                            LookupAttributes=[
                                {'AttributeKey': 'EventName', 'AttributeValue': event_name}
                            ],
                            StartTime=start_time,
                            EndTime=end_time,
                            MaxResults=50  # 페이지네이션 필요시 조정
                        )

                        for event in response['Events']:
                            model_id = self.extract_model_id_from_event(event)
                            if model_id and model_id != 'Unknown':
                                self.discovered_models.add(model_id)

                            # 토큰 사용량 추출
                            token_usage = self.extract_token_usage_from_event(event)

                            # 애플리케이션 정보 추출
                            application = self.extract_application_info(event)
                            if application and application != 'Unknown':
                                self.discovered_applications.add(application)

                            events.append({
                                'region': region,
                                'time': event['EventTime'],
                                'user': event.get('Username', 'Unknown'),
                                'event_name': event['EventName'],
                                'model_id': model_id,
                                'application': application,
                                'input_tokens': token_usage['input_tokens'],
                                'output_tokens': token_usage['output_tokens'],
                                'has_token_data': token_usage['input_tokens'] > 0 or token_usage['output_tokens'] > 0,
                                'resources': event.get('Resources', []),
                                'cloud_trail_event': event
                            })
                    except Exception as e:
                        st.warning(f"Error fetching {event_name} in {region}: {str(e)}")

            except Exception as e:
                st.error(f"CloudTrail error in {region}: {str(e)}")

        return events

    def get_cloudwatch_metrics(self, regions: List[str], model_ids: List[str], start_time: datetime, end_time: datetime) -> Dict:
        """실제 사용된 모델 ID로 CloudWatch 메트릭 조회"""
        metrics_data = {}

        for region in regions:
            try:
                client = boto3.client('cloudwatch', region_name=region)
                metrics_data[region] = {}

                for model_id in model_ids:
                    try:
                        # Input tokens
                        input_response = client.get_metric_statistics(
                            Namespace='AWS/Bedrock',
                            MetricName='InputTokenCount',
                            Dimensions=[{'Name': 'ModelId', 'Value': model_id}],
                            StartTime=start_time,
                            EndTime=end_time,
                            Period=3600,
                            Statistics=['Sum']
                        )

                        # Output tokens
                        output_response = client.get_metric_statistics(
                            Namespace='AWS/Bedrock',
                            MetricName='OutputTokenCount',
                            Dimensions=[{'Name': 'ModelId', 'Value': model_id}],
                            StartTime=start_time,
                            EndTime=end_time,
                            Period=3600,
                            Statistics=['Sum']
                        )

                        input_sum = sum([point['Sum'] for point in input_response['Datapoints']])
                        output_sum = sum([point['Sum'] for point in output_response['Datapoints']])

                        # 토큰이 있는 경우만 저장
                        if input_sum > 0 or output_sum > 0:
                            metrics_data[region][model_id] = {
                                'input_tokens': input_sum,
                                'output_tokens': output_sum
                            }
                    except Exception as e:
                        st.warning(f"CloudWatch error for model {model_id} in {region}: {str(e)}")

            except Exception as e:
                st.error(f"CloudWatch error in {region}: {str(e)}")

        return metrics_data

    def calculate_costs(self, metrics_data: Dict) -> pd.DataFrame:
        """메트릭 데이터를 기반으로 비용 계산"""
        cost_data = []
        for region, models in metrics_data.items():
            region_pricing = self.pricing.get(region, self.pricing['us-east-1'])
            for model_id, tokens in models.items():
                input_cost = (tokens['input_tokens'] / 1000) * region_pricing['input']
                output_cost = (tokens['output_tokens'] / 1000) * region_pricing['output']
                total_cost = input_cost + output_cost

                cost_data.append({
                    'Region': region,
                    'Model ID': model_id,
                    'Input Tokens': int(tokens['input_tokens']),
                    'Output Tokens': int(tokens['output_tokens']),
                    'Input Cost ($)': round(input_cost, 4),
                    'Output Cost ($)': round(output_cost, 4),
                    'Total Cost ($)': round(total_cost, 4)
                })

        return pd.DataFrame(cost_data)

    def analyze_user_usage(self, events: List[Dict]) -> pd.DataFrame:
        """사용자별 모델 사용량 분석"""
        user_data = {}

        for event in events:
            user = event['user']
            model_id = event['model_id']
            region = event['region']

            key = f"{user}|{model_id}|{region}"
            if key not in user_data:
                user_data[key] = {
                    'User': user,
                    'Model ID': model_id,
                    'Region': region,
                    'Invocation Count': 0
                }
            user_data[key]['Invocation Count'] += 1

        df = pd.DataFrame(list(user_data.values()))
        return df.sort_values(by='Invocation Count', ascending=False) if not df.empty else df

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

            for user_key, data in user_data.items():
                region_pricing = self.pricing.get(data['region'], self.pricing['us-east-1'])
                input_cost = (data['input_tokens'] / 1000) * region_pricing['input']
                output_cost = (data['output_tokens'] / 1000) * region_pricing['output']
                total_cost = input_cost + output_cost

                user_cost_data.append({
                    'User': data['user'],
                    'Region': data['region'],
                    'Model ID': data['model_id'],
                    'Invocation Count': data['count'],
                    'Input Tokens': int(data['input_tokens']),
                    'Output Tokens': int(data['output_tokens']),
                    'Input Cost ($)': round(input_cost, 4),
                    'Output Cost ($)': round(output_cost, 4),
                    'Total Cost ($)': round(total_cost, 4),
                    'Data Source': 'CloudTrail (Actual)'
                })

            calculation_method = "actual"

        else:
            # 방법 2: CloudWatch 메트릭을 호출 비율로 분배 (추정)
            total_calls = {}
            user_calls = {}

            for event in events:
                user = event['user']
                model_id = event['model_id']
                region = event['region']
                key = f"{region}|{model_id}"

                if key not in total_calls:
                    total_calls[key] = 0
                total_calls[key] += 1

                user_key = f"{user}|{region}|{model_id}"
                if user_key not in user_calls:
                    user_calls[user_key] = {
                        'user': user,
                        'region': region,
                        'model_id': model_id,
                        'count': 0
                    }
                user_calls[user_key]['count'] += 1

            for user_key, user_info in user_calls.items():
                user = user_info['user']
                region = user_info['region']
                model_id = user_info['model_id']
                user_count = user_info['count']

                key = f"{region}|{model_id}"
                total_count = total_calls.get(key, 1)
                ratio = user_count / total_count if total_count > 0 else 0

                if region in metrics_data and model_id in metrics_data[region]:
                    tokens = metrics_data[region][model_id]
                    user_input_tokens = tokens['input_tokens'] * ratio
                    user_output_tokens = tokens['output_tokens'] * ratio

                    region_pricing = self.pricing.get(region, self.pricing['us-east-1'])
                    input_cost = (user_input_tokens / 1000) * region_pricing['input']
                    output_cost = (user_output_tokens / 1000) * region_pricing['output']
                    total_cost = input_cost + output_cost

                    user_cost_data.append({
                        'User': user,
                        'Region': region,
                        'Model ID': model_id,
                        'Invocation Count': user_count,
                        'Call Ratio (%)': round(ratio * 100, 2),
                        'Est. Input Tokens': int(user_input_tokens),
                        'Est. Output Tokens': int(user_output_tokens),
                        'Input Cost ($)': round(input_cost, 4),
                        'Output Cost ($)': round(output_cost, 4),
                        'Total Cost ($)': round(total_cost, 4),
                        'Data Source': 'CloudWatch (Estimated)'
                    })

            calculation_method = "estimated"

        df = pd.DataFrame(user_cost_data)
        return (df.sort_values(by='Total Cost ($)', ascending=False) if not df.empty else df), calculation_method

    def calculate_application_costs(self, events: List[Dict], metrics_data: Dict) -> Tuple[pd.DataFrame, str]:
        """애플리케이션별 토큰 사용량과 비용 계산 (실제 토큰 우선, 없으면 추정)"""
        app_cost_data = []

        # CloudTrail에 토큰 데이터가 있는지 확인
        events_with_tokens = [e for e in events if e.get('has_token_data', False)]
        has_actual_token_data = len(events_with_tokens) > 0

        if has_actual_token_data:
            # 방법 1: CloudTrail에서 실제 토큰 데이터 사용 (가장 정확)
            app_data = {}

            for event in events:
                application = event.get('application', 'Unknown')
                region = event['region']
                model_id = event['model_id']
                app_key = f"{application}|{region}|{model_id}"

                if app_key not in app_data:
                    app_data[app_key] = {
                        'application': application,
                        'region': region,
                        'model_id': model_id,
                        'count': 0,
                        'input_tokens': 0,
                        'output_tokens': 0
                    }

                app_data[app_key]['count'] += 1
                app_data[app_key]['input_tokens'] += event.get('input_tokens', 0)
                app_data[app_key]['output_tokens'] += event.get('output_tokens', 0)

            for app_key, data in app_data.items():
                region_pricing = self.pricing.get(data['region'], self.pricing['us-east-1'])
                input_cost = (data['input_tokens'] / 1000) * region_pricing['input']
                output_cost = (data['output_tokens'] / 1000) * region_pricing['output']
                total_cost = input_cost + output_cost

                app_cost_data.append({
                    'Application': data['application'],
                    'Region': data['region'],
                    'Model ID': data['model_id'],
                    'Invocation Count': data['count'],
                    'Input Tokens': int(data['input_tokens']),
                    'Output Tokens': int(data['output_tokens']),
                    'Input Cost ($)': round(input_cost, 4),
                    'Output Cost ($)': round(output_cost, 4),
                    'Total Cost ($)': round(total_cost, 4),
                    'Data Source': 'CloudTrail (Actual)'
                })

            calculation_method = "actual"

        else:
            # 방법 2: CloudWatch 메트릭을 호출 비율로 분배 (추정)
            total_calls = {}
            app_calls = {}

            for event in events:
                application = event.get('application', 'Unknown')
                model_id = event['model_id']
                region = event['region']
                key = f"{region}|{model_id}"

                if key not in total_calls:
                    total_calls[key] = 0
                total_calls[key] += 1

                app_key = f"{application}|{region}|{model_id}"
                if app_key not in app_calls:
                    app_calls[app_key] = {
                        'application': application,
                        'region': region,
                        'model_id': model_id,
                        'count': 0
                    }
                app_calls[app_key]['count'] += 1

            for app_key, app_info in app_calls.items():
                application = app_info['application']
                region = app_info['region']
                model_id = app_info['model_id']
                app_count = app_info['count']

                key = f"{region}|{model_id}"
                total_count = total_calls.get(key, 1)
                ratio = app_count / total_count if total_count > 0 else 0

                if region in metrics_data and model_id in metrics_data[region]:
                    tokens = metrics_data[region][model_id]
                    app_input_tokens = tokens['input_tokens'] * ratio
                    app_output_tokens = tokens['output_tokens'] * ratio

                    region_pricing = self.pricing.get(region, self.pricing['us-east-1'])
                    input_cost = (app_input_tokens / 1000) * region_pricing['input']
                    output_cost = (app_output_tokens / 1000) * region_pricing['output']
                    total_cost = input_cost + output_cost

                    app_cost_data.append({
                        'Application': application,
                        'Region': region,
                        'Model ID': model_id,
                        'Invocation Count': app_count,
                        'Call Ratio (%)': round(ratio * 100, 2),
                        'Est. Input Tokens': int(app_input_tokens),
                        'Est. Output Tokens': int(app_output_tokens),
                        'Input Cost ($)': round(input_cost, 4),
                        'Output Cost ($)': round(output_cost, 4),
                        'Total Cost ($)': round(total_cost, 4),
                        'Data Source': 'CloudWatch (Estimated)'
                    })

            calculation_method = "estimated"

        df = pd.DataFrame(app_cost_data)
        return (df.sort_values(by='Total Cost ($)', ascending=False) if not df.empty else df), calculation_method

def main():
    st.set_page_config(page_title="Bedrock Usage Tracker", layout="wide")
    st.title("🔍 Amazon Bedrock Usage Tracker")

    tracker = BedrockUsageTracker()

    # Sidebar
    st.sidebar.header("Configuration")

    selected_regions = st.sidebar.multiselect(
        "Select Regions",
        tracker.regions,
        default=['us-east-1']
    )

    # Date range
    col1, col2 = st.sidebar.columns(2)
    with col1:
        start_date = st.date_input("Start Date", datetime.now() - timedelta(days=7))
    with col2:
        end_date = st.date_input("End Date", datetime.now())

    start_time = datetime.combine(start_date, datetime.min.time())
    end_time = datetime.combine(end_date, datetime.max.time())

    if st.sidebar.button("🔄 Refresh Data"):
        if not selected_regions:
            st.error("Please select at least one region.")
            return

        with st.spinner("Fetching CloudTrail events..."):
            # Step 1: CloudTrail Events - 실제 사용된 모델 ID 추출
            events = tracker.get_cloudtrail_events(selected_regions, start_time, end_time)

            if not events:
                st.warning("No CloudTrail events found for the selected criteria.")
                return

            # 발견된 모델 ID 표시
            st.success(f"Found {len(events)} Bedrock API calls")

            with st.expander("🎯 Discovered Model IDs", expanded=True):
                if tracker.discovered_models:
                    st.write("**Models used in the selected time period:**")
                    for model_id in sorted(tracker.discovered_models):
                        model_type = "Cross-Region" if model_id.startswith(("us.", "eu.", "ap.")) else "Standard"
                        st.code(f"{model_id} ({model_type})", language="")
                else:
                    st.info("No model IDs could be extracted from CloudTrail events.")

            # Step 2: 사용자별 사용량 분석
            st.subheader("👥 User Activity Analysis")
            user_df = tracker.analyze_user_usage(events)
            if not user_df.empty:
                st.dataframe(user_df, use_container_width=True)
            else:
                st.info("No user activity data available.")

            # Step 3: CloudTrail 이벤트 상세
            with st.expander("📋 CloudTrail Events Details"):
                events_df = pd.DataFrame(events)
                display_columns = ['region', 'time', 'user', 'application', 'event_name', 'model_id', 'input_tokens', 'output_tokens']
                # 컬럼이 존재하는 것만 표시
                available_columns = [col for col in display_columns if col in events_df.columns]
                st.dataframe(events_df[available_columns], use_container_width=True)

        # Step 4: CloudWatch Metrics - 실제 사용된 모델만 조회
        if tracker.discovered_models:
            with st.spinner("Fetching CloudWatch metrics for token usage..."):
                st.subheader("📊 Token Usage & Costs")

                model_ids_list = list(tracker.discovered_models)
                metrics_data = tracker.get_cloudwatch_metrics(selected_regions, model_ids_list, start_time, end_time)

                if any(models for models in metrics_data.values()):
                    cost_df = tracker.calculate_costs(metrics_data)

                    # Summary metrics
                    col1, col2, col3, col4 = st.columns(4)
                    with col1:
                        st.metric("Total Input Tokens", f"{cost_df['Input Tokens'].sum():,}")
                    with col2:
                        st.metric("Total Output Tokens", f"{cost_df['Output Tokens'].sum():,}")
                    with col3:
                        st.metric("Total Cost", f"${cost_df['Total Cost ($)'].sum():.4f}")
                    with col4:
                        st.metric("Avg Cost per Model", f"${cost_df['Total Cost ($)'].mean():.4f}")

                    # Detailed table
                    st.dataframe(cost_df, use_container_width=True)

                    # Charts
                    col1, col2 = st.columns(2)
                    with col1:
                        st.subheader("Cost by Region")
                        region_costs = cost_df.groupby('Region')['Total Cost ($)'].sum()
                        st.bar_chart(region_costs)

                    with col2:
                        st.subheader("Token Usage by Model")
                        model_tokens = cost_df.groupby('Model ID')[['Input Tokens', 'Output Tokens']].sum()
                        st.bar_chart(model_tokens)

                    # Step 5: 사용자별 비용 분석
                    st.subheader("💰 User Cost Analysis")

                    user_cost_df, calc_method = tracker.calculate_user_costs(events, metrics_data)

                    if calc_method == "actual":
                        st.success("✅ Using actual token data from CloudTrail events (most accurate)")
                    else:
                        st.info("📌 User costs are estimated based on their API call ratio, as CloudWatch metrics don't provide per-user token counts.")

                    if not user_cost_df.empty:
                        # 사용자별 총 비용 요약
                        # 실제 토큰 vs 추정 토큰에 따라 컬럼 이름 다름
                        if calc_method == "actual":
                            user_summary = user_cost_df.groupby('User').agg({
                                'Total Cost ($)': 'sum',
                                'Invocation Count': 'sum',
                                'Input Tokens': 'sum',
                                'Output Tokens': 'sum'
                            }).reset_index()
                        else:
                            user_summary = user_cost_df.groupby('User').agg({
                                'Total Cost ($)': 'sum',
                                'Invocation Count': 'sum',
                                'Est. Input Tokens': 'sum',
                                'Est. Output Tokens': 'sum'
                            }).reset_index()
                        user_summary = user_summary.sort_values(by='Total Cost ($)', ascending=False)

                        # 요약 메트릭
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.metric("Top User", user_summary.iloc[0]['User'] if len(user_summary) > 0 else "N/A")
                        with col2:
                            st.metric("Top User Cost", f"${user_summary.iloc[0]['Total Cost ($)']:.4f}" if len(user_summary) > 0 else "$0")
                        with col3:
                            st.metric("Total Users", len(user_summary))

                        # 사용자별 요약 테이블
                        st.write("**User Cost Summary:**")

                        # 실제 토큰 vs 추정 토큰에 따라 컬럼 이름 다르게 표시
                        if calc_method == "actual":
                            format_dict = {
                                'Total Cost ($)': '${:.4f}',
                                'Input Tokens': '{:,.0f}',
                                'Output Tokens': '{:,.0f}',
                                'Invocation Count': '{:,.0f}'
                            }
                        else:
                            format_dict = {
                                'Total Cost ($)': '${:.4f}',
                                'Est. Input Tokens': '{:,.0f}',
                                'Est. Output Tokens': '{:,.0f}',
                                'Invocation Count': '{:,.0f}'
                            }

                        st.dataframe(user_summary.style.format(format_dict), use_container_width=True)

                        # 상세 사용자별 비용 (모델/리전 분리)
                        with st.expander("📊 Detailed User Costs by Model & Region"):
                            st.dataframe(user_cost_df, use_container_width=True)

                        # 사용자별 비용 차트
                        st.subheader("Cost by User")
                        user_costs = user_summary.set_index('User')['Total Cost ($)']
                        st.bar_chart(user_costs)
                    else:
                        st.info("Unable to calculate user costs. Make sure CloudWatch metrics are available.")

                    # Step 6: 애플리케이션별 비용 분석
                    st.subheader("🚀 Application Cost Analysis")

                    if tracker.discovered_applications:
                        st.write(f"**Discovered Applications:** {', '.join(sorted(tracker.discovered_applications))}")

                        app_cost_df, app_calc_method = tracker.calculate_application_costs(events, metrics_data)

                        if app_calc_method == "actual":
                            st.success("✅ Using actual token data from CloudTrail events (most accurate)")
                        else:
                            st.info("📌 Application costs are estimated based on their API call ratio.")

                        if not app_cost_df.empty:
                            # 애플리케이션별 총 비용 요약
                            app_summary = app_cost_df.groupby('Application').agg({
                                'Total Cost ($)': 'sum',
                                'Invocation Count': 'sum'
                            }).reset_index()
                            app_summary = app_summary.sort_values(by='Total Cost ($)', ascending=False)

                            # 요약 메트릭
                            col1, col2, col3 = st.columns(3)
                            with col1:
                                st.metric("Top Application", app_summary.iloc[0]['Application'] if len(app_summary) > 0 else "N/A")
                            with col2:
                                st.metric("Top App Cost", f"${app_summary.iloc[0]['Total Cost ($)']:.4f}" if len(app_summary) > 0 else "$0")
                            with col3:
                                st.metric("Total Applications", len(app_summary))

                            # 애플리케이션별 요약 테이블
                            st.write("**Application Cost Summary:**")
                            st.dataframe(app_summary.style.format({
                                'Total Cost ($)': '${:.4f}',
                                'Invocation Count': '{:,.0f}'
                            }), use_container_width=True)

                            # 상세 애플리케이션별 비용 (모델/리전 분리)
                            with st.expander("📊 Detailed Application Costs by Model & Region"):
                                st.dataframe(app_cost_df, use_container_width=True)

                            # 애플리케이션별 비용 차트
                            st.subheader("Cost by Application")
                            app_costs = app_summary.set_index('Application')['Total Cost ($)']
                            st.bar_chart(app_costs)
                        else:
                            st.info("Unable to calculate application costs. Make sure CloudWatch metrics are available.")
                    else:
                        st.info("No applications identified. Applications can be identified via:\n"
                               "- IAM Role names (e.g., AppName-BedrockRole)\n"
                               "- UserAgent strings set by your application code\n\n"
                               "See the documentation for setup instructions.")

                else:
                    st.info("No CloudWatch metrics data found. This may be because:\n"
                           "- CloudWatch metrics are delayed (can take up to 15 minutes)\n"
                           "- The models were invoked but no metrics are published yet\n"
                           "- CloudWatch detailed monitoring is not enabled")
        else:
            st.warning("No model IDs were discovered in CloudTrail events. Cannot query CloudWatch metrics.")

if __name__ == "__main__":
    main()
