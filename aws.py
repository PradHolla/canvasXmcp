import boto3
from datetime import datetime

cloudwatch = boto3.client('cloudwatch')

response = cloudwatch.get_metric_data(
    MetricDataQueries=[
        {
            'Id': 'input_tokens',
            'MetricStat': {
                'Metric': {
                    'Namespace': 'AWS/Bedrock',
                    'MetricName': 'InputTokenCount',
                    'Dimensions': [
                        {
                            'Name': 'ModelId',
                            'Value': 'us.meta.llama4-maverick-17b-instruct-v1:0'
                        }
                    ]
                },
                'Period': 3600,
                'Stat': 'Sum'
            }
        },
        {
            'Id': 'output_tokens',
            'MetricStat': {
                'Metric': {
                    'Namespace': 'AWS/Bedrock',
                    'MetricName': 'OutputTokenCount',
                    'Dimensions': [
                        {
                            'Name': 'ModelId',
                            'Value': 'us.meta.llama4-maverick-17b-instruct-v1:0'
                        }
                    ]
                },
                'Period': 3600,
                'Stat': 'Sum'
            }
        }
    ],
    StartTime=datetime(2025, 10, 1),
    EndTime=datetime(2025, 10, 13)
)

for result in response['MetricDataResults']:
    print(f"{result['Label']}: {sum(result['Values'])}")
