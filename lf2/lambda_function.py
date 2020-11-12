import json
import random
import boto3
import math
from boto3.dynamodb.conditions import Key


def new_otp():
    digits = "0123456789"
    otp = ""
    for i in range(4):
        otp += digits[math.floor(random.random() * 10)]
    return otp


def lambda_handler(event, context):
    dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
    table = dynamodb.Table("visitors")
    body = json.loads(event["body"])
    # check if face is existed
    rec = table.query(KeyConditionExpression=Key("faceId").eq(body["face_id"]))
    if rec["Count"] != 0:
        return {
            "statusCode": 409,
            "body": json.dumps({"error": "the face id is existed"})
        }
    item = {
        "faceId": body["face_id"],
        "name": body["name"],
        "phoneNumber": body["phone_number"],
        "photos": []
    }
    table.put_item(Item=item)

    # add passcode
    otp = new_otp()
    table = dynamodb.Table("passcodes")
    table.put_item(Item={"passcode": otp})

    # send sms
    sns = boto3.client("sns", region_name="us-west-2")
    sns.publish(PhoneNumber=body["phone_number"], Message=f"[SmartDoor] your OTP is: {otp}")
    return {
        "statusCode": 201,
        "body": json.dumps({"error": ""})
    }


if __name__ == "__main__":
    print(lambda_handler({"body": {"face_id": "123456", "phone_number": "+16622280114", "name": "yufan"}}, None))