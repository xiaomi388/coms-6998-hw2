import boto3
import json
from boto3.dynamodb.conditions import Key


def lambda_handler(event, context):
    dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
    table = dynamodb.Table("passcodes")

    body = json.loads(event["body"])
    rec = table.query(IndexName="passcode-index", KeyConditionExpression=Key("passcode").eq(body["otp"]))
    if rec["Count"] == 0:
        return {
            "statusCode": 403,
            "headers": {
                'Access-Control-Allow-Origin': '*'
            },
            "body": json.dumps({"error": "permission denied"})
        }
    face_id = rec["Items"][0]["faceId"]
    table.delete_item(Key={"faceId": face_id, "passcode": body["otp"]})
    table = dynamodb.Table("visitors")
    rec = table.query(KeyConditionExpression=Key("faceId").eq(face_id))
    name = rec["Items"][0]["name"]
    return {
        'statusCode': 200,
        'headers': {
            'Access-Control-Allow-Origin': '*'
        },
        'body': json.dumps({"error": "", "visitor": {"name": name}})
    }


if __name__ == "__main__":
    print(lambda_handler({"body": json.dumps({"otp": "73663"})}, None))

