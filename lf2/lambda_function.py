import json
import random
import boto3
import math
import time
from boto3.dynamodb.conditions import Key


def new_otp():
    digits = "0123456789"
    otp = ""
    for i in range(5):
        otp += digits[math.floor(random.random() * 10)]
    return otp


def lambda_handler(event, context):
    dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
    table = dynamodb.Table("visitors")
    body = json.loads(event["body"])
    # check if the face exists
    rec = table.query(KeyConditionExpression=Key("faceId").eq(body["face_id"]))
    if rec["Count"] != 0 and rec["Items"][0]["name"] != "":
        return {
            "statusCode": 409,
            "headers": {
                "Access-Control-Allow-Origin": "*"
            },
            "body": json.dumps({"error": "the visitor has been added"})
        }
    item = {
        "faceId": body["face_id"],
        "name": body["name"],
        "phoneNumber": body["phone_number"],
        "photos": []
    }
    table.put_item(Item=item)

    # add passcode
    while True:
        table = dynamodb.Table("passcodes")
        otp = new_otp()
        # check if the passcode exists
        rec = table.query(IndexName="passcode-index", KeyConditionExpression=Key("passcode").eq(otp))
        if rec["Count"] != 0:
            continue
        table.put_item(Item={
            "passcode": otp,
            "faceId": body["face_id"],
            "ttl": int(time.time())+300,
            "createdAtTimestamp": int(time.time())
        })
        break

    # send sms
    sns = boto3.client("sns", region_name="us-west-2")
    sns.publish(PhoneNumber=body["phone_number"],
                Message=f"You are the one on file, please use the one time passcode. : {otp} "
                        f"The pass code will expire in 5 minutes")
    return {
        "statusCode": 201,
        "headers": {
            "Access-Control-Allow-Origin": "*"
        },
        "body": json.dumps({"error": ""})
    }


if __name__ == "__main__":
    print(lambda_handler({"body": json.dumps({"face_id": "1234", "phone_number": "+16622280114", "name": "yufan"})}, None))

