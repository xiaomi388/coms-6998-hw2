import boto3
import json
from boto3.dynamodb.conditions import Key


def lambda_handler(event, context):
    dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
    table = dynamodb.Table("passcodes")

    body = json.loads(event["body"])
    # check if face is existed
    rec = table.query(KeyConditionExpression=Key("passcode").eq(body["otp"]))
    if rec["Count"] == 0:
        return {
            "statusCode": 403,
            "body": json.dumps({"error": "permission denied"})
        }
    return {
        "statusCode": 200,
        "body": json.dumps({"error": ""})
    }


if __name__ == "__main__":
    print(lambda_handler({"body": json.dumps({"otp": "0556"})}, None))
