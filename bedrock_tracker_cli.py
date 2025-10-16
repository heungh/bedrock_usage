#!/usr/bin/env python3
"""
CLI 버전의 Bedrock Usage Tracker
10월 1일부터 현재까지, us-east-1과 us-west-2 리전의 사용량 확인
"""

import boto3
import pandas as pd
from datetime import datetime, timedelta
import json
from typing import Dict, List, Tuple

class BedrockUsageTracker:
    def __init__(self):
        self.regions = ['us-east-1', 'us-west-2', 'eu-west-1', 'ap-northeast-1', 'ap-southeast-1']
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
            if 'CloudTrailEvent' in event:
                event_data = json.loads(event['CloudTrailEvent'])
                if 'requestParameters' in event_data and 'modelId' in event_data['requestParameters']:
                    return event_data['requestParameters']['modelId']

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

                if 'responseElements' in event_data:
                    response_elements = event_data['responseElements']

                    if 'usage' in response_elements:
                        usage = response_elements['usage']
                        return {
                            'input_tokens': usage.get('inputTokens', 0),
                            'output_tokens': usage.get('outputTokens', 0)
                        }

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

                if 'userIdentity' in event_data:
                    user_identity = event_data['userIdentity']

                    if user_identity.get('type') == 'AssumedRole':
                        arn = user_identity.get('arn', '')
                        if 'assumed-role' in arn:
                            parts = arn.split('/')
                            if len(parts) >= 2:
                                role_name = parts[-2]
                                if '-BedrockRole' in role_name:
                                    return role_name.replace('-BedrockRole', '')
                                return role_name

                user_agent = event_data.get('userAgent', '')
                if user_agent:
                    parts = user_agent.split()
                    for part in parts:
                        if '/' in part and not part.startswith(('aws-', 'Python/', 'boto', 'Boto', 'exec-env')):
                            app_name = part.split('/')[0]
                            if app_name not in ['botocore', 'urllib3', 'APN']:
                                return app_name

        except Exception as e:
            pass

        return 'Unknown'

    def get_cloudtrail_events(self, regions: List[str], start_time: datetime, end_time: datetime) -> List[Dict]:
        events = []
        event_names = ['InvokeModel', 'InvokeModelWithResponseStream']

        for region in regions:
            print(f"\n🔍 Fetching CloudTrail events from {region}...")
            try:
                client = boto3.client('cloudtrail', region_name=region)

                for event_name in event_names:
                    try:
                        response = client.lookup_events(
                            LookupAttributes=[
                                {'AttributeKey': 'EventName', 'AttributeValue': event_name}
                            ],
                            StartTime=start_time,
                            EndTime=end_time,
                            MaxResults=50
                        )

                        for event in response['Events']:
                            model_id = self.extract_model_id_from_event(event)
                            if model_id and model_id != 'Unknown':
                                self.discovered_models.add(model_id)

                            token_usage = self.extract_token_usage_from_event(event)
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
                        print(f"⚠️  Error fetching {event_name} in {region}: {str(e)}")

            except Exception as e:
                print(f"❌ CloudTrail error in {region}: {str(e)}")

        return events

    def get_cloudwatch_metrics(self, regions: List[str], model_ids: List[str], start_time: datetime, end_time: datetime) -> Dict:
        """CloudWatch 메트릭 조회"""
        metrics_data = {}

        for region in regions:
            print(f"  🔍 Fetching CloudWatch metrics from {region}...")
            try:
                client = boto3.client('cloudwatch', region_name=region)
                metrics_data[region] = {}

                for model_id in model_ids:
                    try:
                        input_response = client.get_metric_statistics(
                            Namespace='AWS/Bedrock',
                            MetricName='InputTokenCount',
                            Dimensions=[{'Name': 'ModelId', 'Value': model_id}],
                            StartTime=start_time,
                            EndTime=end_time,
                            Period=3600,
                            Statistics=['Sum']
                        )

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

                        if input_sum > 0 or output_sum > 0:
                            metrics_data[region][model_id] = {
                                'input_tokens': input_sum,
                                'output_tokens': output_sum
                            }
                    except Exception as e:
                        print(f"    ⚠️  Error for model {model_id}: {str(e)}")

            except Exception as e:
                print(f"    ❌ CloudWatch error in {region}: {str(e)}")

        return metrics_data

    def calculate_user_costs(self, events: List[Dict], metrics_data: Dict) -> Tuple[pd.DataFrame, str]:
        """사용자별 토큰 사용량과 비용 계산 (실제 토큰 우선, 없으면 추정)"""
        user_cost_data = []

        events_with_tokens = [e for e in events if e.get('has_token_data', False)]
        has_actual_token_data = len(events_with_tokens) > 0

        if has_actual_token_data:
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
            if not metrics_data or not any(models for models in metrics_data.values()):
                calculation_method = "no_data"
            else:
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

        events_with_tokens = [e for e in events if e.get('has_token_data', False)]
        has_actual_token_data = len(events_with_tokens) > 0

        if has_actual_token_data:
            # 방법 1: CloudTrail에서 실제 토큰 데이터 사용
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
            if not metrics_data or not any(models for models in metrics_data.values()):
                calculation_method = "no_data"
            else:
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
    print("=" * 80)
    print("🔍 Bedrock Usage Tracker - CLI Version")
    print("=" * 80)

    # 10월 1일부터 현재까지
    start_time = datetime(2025, 10, 1)
    end_time = datetime.now()
    regions = ['us-east-1', 'us-west-2']

    print(f"\n📅 Period: {start_time.date()} to {end_time.date()}")
    print(f"🌍 Regions: {', '.join(regions)}")

    tracker = BedrockUsageTracker()

    # CloudTrail 이벤트 가져오기
    print("\n" + "=" * 80)
    print("Step 1: Fetching CloudTrail Events")
    print("=" * 80)

    events = tracker.get_cloudtrail_events(regions, start_time, end_time)

    if not events:
        print("\n⚠️  No CloudTrail events found for the selected period and regions.")
        print("This could mean:")
        print("  - No Bedrock API calls were made")
        print("  - CloudTrail logging is not enabled")
        print("  - Events are still being processed (wait up to 15 minutes)")
        return

    print(f"\n✅ Found {len(events)} Bedrock API calls")

    # 발견된 모델 표시
    if tracker.discovered_models:
        print(f"\n🎯 Discovered {len(tracker.discovered_models)} model(s):")
        for model_id in sorted(tracker.discovered_models):
            print(f"  • {model_id}")

    # 발견된 애플리케이션 표시
    if tracker.discovered_applications:
        print(f"\n🚀 Discovered {len(tracker.discovered_applications)} application(s):")
        for app in sorted(tracker.discovered_applications):
            print(f"  • {app}")

    # 토큰 데이터 확인
    events_with_tokens = [e for e in events if e.get('has_token_data', False)]
    print(f"\n📊 Events with token data: {len(events_with_tokens)} / {len(events)}")

    # CloudWatch 메트릭 가져오기
    print("\n" + "=" * 80)
    print("Step 2: Fetching CloudWatch Metrics")
    print("=" * 80)

    model_ids_list = list(tracker.discovered_models)
    metrics_data = tracker.get_cloudwatch_metrics(regions, model_ids_list, start_time, end_time)

    if any(models for models in metrics_data.values()):
        print("\n✅ CloudWatch metrics retrieved successfully")
        for region, models in metrics_data.items():
            print(f"\n  {region}:")
            for model_id, tokens in models.items():
                print(f"    • {model_id}")
                print(f"      Input: {int(tokens['input_tokens']):,} tokens")
                print(f"      Output: {int(tokens['output_tokens']):,} tokens")
    else:
        print("\n⚠️  No CloudWatch metrics found (may take up to 15 minutes to appear)")

    # 사용자별 비용 계산
    print("\n" + "=" * 80)
    print("Step 3: Calculating User Costs")
    print("=" * 80)

    user_cost_df, calc_method = tracker.calculate_user_costs(events, metrics_data)

    if calc_method == "actual":
        print("\n✅ Using ACTUAL token data from CloudTrail (most accurate)")
    elif calc_method == "estimated":
        print("\n📊 Using ESTIMATED costs based on CloudWatch metrics and call ratios")
    else:
        print("\n⚠️  No token data available")

    if not user_cost_df.empty:
        print(f"\n{'=' * 80}")
        print("💰 USER COST ANALYSIS")
        print(f"{'=' * 80}\n")

        # 사용자별 요약
        if calc_method == "actual":
            user_summary = user_cost_df.groupby('User').agg({
                'Total Cost ($)': 'sum',
                'Invocation Count': 'sum',
                'Input Tokens': 'sum',
                'Output Tokens': 'sum'
            }).reset_index()
        elif calc_method == "estimated":
            user_summary = user_cost_df.groupby('User').agg({
                'Total Cost ($)': 'sum',
                'Invocation Count': 'sum',
                'Est. Input Tokens': 'sum',
                'Est. Output Tokens': 'sum'
            }).reset_index()
        else:
            user_summary = user_cost_df.groupby('User').agg({
                'Total Cost ($)': 'sum',
                'Invocation Count': 'sum'
            }).reset_index()

        user_summary = user_summary.sort_values(by='Total Cost ($)', ascending=False)

        print(user_summary.to_string(index=False))

        print(f"\n{'=' * 80}")
        print("📋 DETAILED BREAKDOWN BY USER, REGION, AND MODEL")
        print(f"{'=' * 80}\n")

        print(user_cost_df.to_string(index=False))

        # 총계
        total_cost = user_cost_df['Total Cost ($)'].sum()
        if calc_method == "actual":
            total_input = user_cost_df['Input Tokens'].sum()
            total_output = user_cost_df['Output Tokens'].sum()
        elif calc_method == "estimated":
            total_input = user_cost_df['Est. Input Tokens'].sum()
            total_output = user_cost_df['Est. Output Tokens'].sum()
        else:
            total_input = 0
            total_output = 0

        print(f"\n{'=' * 80}")
        print("📊 TOTAL SUMMARY")
        print(f"{'=' * 80}")
        print(f"Total Users: {len(user_summary)}")
        print(f"Total API Calls: {user_cost_df['Invocation Count'].sum():,}")
        if calc_method in ["actual", "estimated"]:
            print(f"Total Input Tokens: {int(total_input):,}")
            print(f"Total Output Tokens: {int(total_output):,}")
        print(f"💵 TOTAL COST: ${total_cost:.4f}")
        print(f"{'=' * 80}\n")

        # 사용자별 금액이 동일한지 확인
        unique_costs = user_summary['Total Cost ($)'].nunique()
        if unique_costs == 1 and len(user_summary) > 1:
            print("⚠️  WARNING: All users have the SAME cost!")
            print("   This indicates:")
            if calc_method == "estimated":
                print("   - Each user made the same number of API calls")
                print("   - Costs are estimated based on call ratios")
                print("   - For accurate per-user costs, enable CloudTrail data event logging")
                print("     with responseElements to capture actual token usage")
            else:
                print("   - There may be a problem with the cost calculation logic")
        else:
            print(f"✅ Users have DIFFERENT costs ({unique_costs} unique cost values)")
            print("   Cost calculation is working correctly!")
    else:
        print("\n⚠️  No cost data available to display.")
        print("\nPossible reasons:")
        print("  - No CloudWatch metrics available yet (can take up to 15 minutes)")
        print("  - No token usage in the selected period")
        print("  - CloudWatch metrics may not be enabled for Bedrock")

    # 애플리케이션별 비용 분석
    if tracker.discovered_applications:
        print("\n" + "=" * 80)
        print("Step 4: Calculating Application Costs")
        print("=" * 80)

        app_cost_df, app_calc_method = tracker.calculate_application_costs(events, metrics_data)

        if app_calc_method == "actual":
            print("\n✅ Using ACTUAL token data from CloudTrail events (most accurate)")
        elif app_calc_method == "estimated":
            print("\n📊 Using ESTIMATED costs based on CloudWatch metrics and call ratios")
        else:
            print("\n⚠️  No token data available")

        if not app_cost_df.empty:
            print(f"\n{'=' * 80}")
            print("🚀 APPLICATION COST ANALYSIS")
            print(f"{'=' * 80}\n")

            # 애플리케이션별 요약
            if app_calc_method == "actual":
                app_summary = app_cost_df.groupby('Application').agg({
                    'Total Cost ($)': 'sum',
                    'Invocation Count': 'sum',
                    'Input Tokens': 'sum',
                    'Output Tokens': 'sum'
                }).reset_index()
            elif app_calc_method == "estimated":
                app_summary = app_cost_df.groupby('Application').agg({
                    'Total Cost ($)': 'sum',
                    'Invocation Count': 'sum',
                    'Est. Input Tokens': 'sum',
                    'Est. Output Tokens': 'sum'
                }).reset_index()
            else:
                app_summary = app_cost_df.groupby('Application').agg({
                    'Total Cost ($)': 'sum',
                    'Invocation Count': 'sum'
                }).reset_index()

            app_summary = app_summary.sort_values(by='Total Cost ($)', ascending=False)

            print(app_summary.to_string(index=False))

            print(f"\n{'=' * 80}")
            print("📋 DETAILED BREAKDOWN BY APPLICATION, REGION, AND MODEL")
            print(f"{'=' * 80}\n")

            print(app_cost_df.to_string(index=False))

            # 애플리케이션별 총계
            total_app_cost = app_cost_df['Total Cost ($)'].sum()

            print(f"\n{'=' * 80}")
            print("📊 APPLICATION SUMMARY")
            print(f"{'=' * 80}")
            print(f"Total Applications: {len(app_summary)}")
            print(f"💵 TOTAL APPLICATION COST: ${total_app_cost:.4f}")
            print(f"{'=' * 80}\n")
        else:
            print("\n⚠️  No application cost data available.")
    else:
        print("\n" + "=" * 80)
        print("ℹ️  No Applications Identified")
        print("=" * 80)
        print("\nApplications can be identified via:")
        print("  • IAM Role names (e.g., AppName-BedrockRole)")
        print("  • UserAgent strings set by your application code")
        print("\nSee README.md for setup instructions.")


if __name__ == "__main__":
    main()
