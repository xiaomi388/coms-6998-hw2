import json
import boto3
from botocore.exceptions import ClientError
import base64
import sys
import cv2
import json
import uuid
import datetime
import time
import random
from boto3.dynamodb.conditions import Key

db1_name = "passcodes"
db2_name = "visitors"
photoS3 = "6998hw2s3"
collection_id = 'Faces'  # Rekognition collection
wp1 = "http://6998hw2s3frontend.s3-website-us-west-1.amazonaws.com"
wp2 = "http://6998hw2s3frontend2.s3-website-us-west-1.amazonaws.com"
stream_processor = "stream_processorHW2"
ownerPhoneNumber = "+16622280114"

'''s3: us-east-1, 
collection(Faces): us-east-1, 
KVS(stream0): us-east-1, 
KDS(data_stream0): us-east1, 
stream processor(stream_processorHW2): us-east-1 '''


# Collection Related Part
def if_known_face(collection_face_details):
    # if_known == 1, found matched face in collections
    # if_known == -1, no matched face in collections
    # if_known == 0, No face at all, error
    if_known = 0
    face_id = ""
    if len(collection_face_details) > 0:
        matchedFaces = collection_face_details[0]["MatchedFaces"]
        if len(matchedFaces) > 0:
            face_id = matchedFaces[0]["Face"]["FaceId"]
            if_known = 1
        else:
            if_known = -1
    return if_known, face_id


def collection_insert(objectkey):
    client = boto3.client('rekognition')
    try:
        response = client.index_faces(CollectionId=collection_id,
                                      Image={'S3Object': {'Bucket': photoS3, 'Name': objectkey}},
                                      ExternalImageId=objectkey,
                                      MaxFaces=1,
                                      QualityFilter="AUTO",
                                      DetectionAttributes=['ALL'])
        face_id = response['FaceRecords'][0]['Face']['FaceId']
    except ClientError as e:
        print(e)
    return face_id


# DB2 related part
def identify_fetch_DB2_face_by_faceId(face_id):
    db2 = boto3.resource('dynamodb')
    table = db2.Table(db2_name)
    response = table.get_item(Key={"faceId": face_id})
    try:
        DB2_face_info = response["Item"]
        if DB2_face_info["name"] != "":
            return DB2_face_info
        else:
            print("No official record in DB2, since there is no visitor name.")
            return None
    except:
        print("No relative photos in DB2 with faceId: ", face_id)
        return None


def retrieve_phoneNumber_DB2(DB2_face_info):
    phone_number = DB2_face_info["phoneNumber"]
    if phone_number:
        if len(phone_number) == 12 and phone_number[:2] == "+1":
            return phone_number
        elif len(phone_number) == 10 and "+1" not in phone_number:
            phone_number = "+1" + phone_number
            return phone_number
        return None
    return None


def append_photo_DB2(face_id, name, phone_number, photos, objectkey):
    db2 = boto3.resource('dynamodb')
    table = db2.Table(db2_name)
    photo = {
        "objectKey": objectkey,
        "bucket": photoS3,
        "createdTimestamp": datetime.datetime.now().isoformat(timespec='seconds')
    }
    photos.append(photo)
    try:
        table.put_item(
            Item={
                "faceId": face_id,
                "name": name,
                "phoneNumber": phone_number,
                "photos": photos
            }
        )
    except ClientError as e:
        print(e)


# DB1&DB3 related part
def check_owner_message_DB3():
    db3 = boto3.resource('dynamodb')

    table = db3.Table("messages")
    response = table.scan()
    return response["Count"] == 0


def check_otp_DB1(face_id):
    db1 = boto3.resource('dynamodb')

    table = db1.Table(db1_name)
    response = table.query(KeyConditionExpression=Key("faceId").eq(face_id))
    if response["Count"] != 0:
        return True
    return False


def generate_otp():
    return random.randint(10000, 99999)


def store_owner_messageTTL_DB3(face_id):
    # otp = generate_otp()
    db3 = boto3.resource('dynamodb')
    table = db3.Table("messages")
    try:
        response = table.put_item(
            Item={
                'faceId': face_id,
                'ttl': int(datetime.datetime.now().timestamp() + 120),

            }
        )

    except ClientError as e:
        print(e)


def store_otp_DB1(face_id, otp):
    # otp = generate_otp()
    db1 = boto3.resource('dynamodb')
    table = db1.Table(db1_name)
    try:
        response = table.put_item(
            Item={
                'faceId': face_id,
                'passcode': str(otp),
                'ttl': int(datetime.datetime.now().timestamp() + 300),

            }
        )

    except ClientError as e:
        print(e)


def sendSMS(phone_number, message):
    client = boto3.client(
        "sns", region_name="us-east-1")
    '''client = boto3.client(
        "sns", 
        region_name="us-east-1"
        aws_access_key_id="",
        aws_secret_access_key=""
        )'''
        
    try:
        print(phone_number, message)
        client.publish(
            PhoneNumber=phone_number,
            Message=message
        )
        print("SMS message sent!")
    except ClientError as e:
        print(e)
        print("SMS sending Error!")


# Photo Fetch Part
def getEndpoint(streamARN):
    kvs = boto3.client('kinesisvideo', region_name='us-east-1')
    kvs_endpoint = kvs.get_data_endpoint(
        APIName="GET_MEDIA",
        StreamARN=streamARN
    )['DataEndpoint']
    return kvs_endpoint


def retrieve_photo(streamARN, fragmentNumber):
    kvs_endpoint = getEndpoint(streamARN)

    kvm = boto3.client('kinesis-video-media', endpoint_url=kvs_endpoint, region_name='us-east-1')
    '''StartSelector = {
            'AfterFragmentNumber' : fragmentNumber,
            'StartSelectorType': 'FRAGMENT_NUMBER'
        }
        StartSelector = {
            'StartSelectorType': 'NOW'
            }'''
    kvs_stream = kvm.get_media(
        StreamARN=streamARN,
        StartSelector={
            'AfterFragmentNumber': fragmentNumber,
            'StartSelectorType': 'FRAGMENT_NUMBER'
        }
    )
    # kvs_stream = kvm.get_media_for_fragment_list(StreamName='KVS1',Fragments=[fragmentNumber])
    clip = kvs_stream['Payload']
    chunks = clip.iter_chunks(chunk_size=512)

    photo_dir = '/tmp/picture.jpg'
    mkv_dir = '/tmp/video_clip'

    with open(mkv_dir, 'wb') as file:
        for i in range(1, 512):
            try:
                chunk = next(chunks)
                file.write(chunk)
            except:
                break

    file = open(mkv_dir, 'rb')
    file.seek(0)

    vidcap = cv2.VideoCapture(mkv_dir)
    success, photo = vidcap.read()

    if success is False:
        print("Vidcap read error")
    # save the photo to photo_dir
    else:
        writeSuccess = cv2.imwrite(photo_dir, photo)
        if writeSuccess is True:
            return '/tmp/picture.jpg'
        else:
            print("Picture write error.")
    return None


# S3 Related Part
def append_photo_s3(photo_dir):
    s3_client = boto3.client('s3')
    addon_key = str(uuid.uuid4())
    key = addon_key + '.jpg'
    try:
        s3_client.upload_file(photo_dir, photoS3, key)
    except ClientError as e:
        print(e)
    objectkey = key
    return objectkey


def append_unknown_temp_photo_s3(photo_dir):
    s3_client = boto3.client('s3')
    print('NOW YOU ARE IN APPEDING UNKNOWN S3 PART')
    try:
        '''response = boto3.client('s3').put_object(
        Bucket="6998hw2s3",
        Key="current_visitor.jpg",
        Body= photo
        ) '''
        response = s3_client.upload_file(photo_dir, '6998hw2s3', 'current_visitor.jpg')
    except ClientError as e:
        print(e)

        print("S3 storing unknown visitor failure!")
    objectkey = 'current_visitor.jpg'
    return objectkey


def lambda_handler(event, context):
    '''print(event)
    return {
            'statusCode': 200,
            'body': json.dumps('You have reached the end line of LF1')}'''
    for record in event["Records"]:
        payload = base64.b64decode(record["kinesis"]["data"])
        data = json.loads(payload.decode("ASCII"))
        print(data)
        streamARN = data["InputInformation"]["KinesisVideo"]["StreamArn"]
        fragmentNumber = data["InputInformation"]["KinesisVideo"]["FragmentNumber"]
        serverTimestamp = data["InputInformation"]["KinesisVideo"]["ServerTimestamp"]
        collection_face_details = data["FaceSearchResponse"]
        

        if_known, face_id = if_known_face(collection_face_details)

        print("If known ?", if_known)

        # Known or Unknown
        if if_known == 0:
            print("No face at all, Error!")
            return {
                'statusCode': 200,
                'body': json.dumps('No face at all, Error!')}
                
        # Get the photo&append to s3 no matter known or unknown visitor
        photo_dir = retrieve_photo(streamARN, fragmentNumber)
        if photo_dir is None:
            return {
                'statusCode': 200,
                'body': json.dumps('No face at all, Error!')}
        objectkey = append_photo_s3(photo_dir)
        
        if if_known == 1:
            print("The visitor was recognized by collections.")

            ##check if known face in db2
            DB2_face_info = identify_fetch_DB2_face_by_faceId(face_id)
            print("DB full info: ", DB2_face_info)

            # If in DB2, then update db2 + send sms to visitor
            if DB2_face_info:

                # update db2
                phone_number = retrieve_phoneNumber_DB2(DB2_face_info)
                name = DB2_face_info["name"]
                photos = DB2_face_info["photos"]
                append_photo_DB2(face_id, name, phone_number, photos, objectkey)

                otp = generate_otp()
                if check_otp_DB1(face_id) is False:
                    # Send OTP for double-known visitor
                    try:
                        store_otp_DB1(face_id, otp)
                        message = "You are the one on file, please use the one time passcode. " + str(
                            otp) + " The pass code will expire in 5 minutes"
                        sendSMS(phone_number, message)
                    except:
                        print("Cannot store otp to visitors.")




            # If not officially in DB2, then update photo list
            elif DB2_face_info is None:
                # update DB2
                db2 = boto3.resource('dynamodb')
                table = db2.Table(db2_name)
                response = table.get_item(Key={"faceId": face_id})
                photos = response['Item']["photos"]
                name = response['Item']["name"]
                phoneNumber = response['Item']["phoneNumber"]
                append_photo_DB2(face_id, name, phoneNumber, photos, objectkey)

        elif if_known == -1 or face_id == "":
            # for every 5 minutes, we can only add one new visitor at most
            if check_owner_message_DB3() is False:
                return {
                    'statusCode': 200,
                    'body': json.dumps('Can not add a new visitor at this time.')}

            # For unknown visitor, append to collections then get face_id, then append to db2
            print("The visitor was NOT recognized by collections.")

            # Get face_id from collections
            face_id = collection_insert(objectkey)

            #append to db2 with face_id generated from collection
            append_photo_DB2(face_id, "", "", [], objectkey)
            print("You have finished the db2 appending.")

            # Send verification link + s3 link to the owner
            s3_link = "https://" + photoS3 + ".s3.amazonaws.com/" + objectkey
            verification_link = wp1 + '/?faceId=' + face_id

            message = "Well,well, master, we have a brand new visitor. Click here to view the photo. \n" + s3_link + '\n' + "If you would like to admit him, please click here. \n" + verification_link
            sendSMS(ownerPhoneNumber, message)
            
            #In the following two minutes, we can not allow more owner messages
            store_owner_messageTTL_DB3(face_id)
            print("Message sent to owner.")

        return {
            'statusCode': 200,
            'body': json.dumps('You have reached the end line of LF1')}


if __name__ == "__main__":
    print(check_owner_message_DB3())
