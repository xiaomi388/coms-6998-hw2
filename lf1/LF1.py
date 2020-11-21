import json
import boto3
import base64
import sys
import cv2
import json
import uuid
import datetime
import time
import random

db1_name = "passcodes"
db2_name = "visitors"
photoS3 = "6998hw2s3"
collection_id= 'Faces'  # Rekognition collection
wp1 = "http://6998hw2s3frontend.s3-website-us-west-1.amazonaws.com"
wp2 = "http://6998hw2s3frontend2.s3-website-us-west-1.amazonaws.com"
stream_processor = ""
ownerEmail = "xiaomi388@gmail.com"
ownerPhoneNumber = "+18141111234"

#Collection Related Part
def if_known_face(collection_face_details):
    # if_known == 1, found matched face in collections
    # if_known == -1, no matched face in collections
    # if_known == 0, No face at all, error
    if_known = 0
    face_id = ""
    if len(collection_face_details)>0:
        matchedFaces = collection_face_details[0]["MatchedFaces"]
        if len(matchedFaces)>0:
            face_id = matchedFaces[0]["Face"]["FaceId"]
            if_known = 1
        else:
            if_known = -1
    return if_known, face_id

def collection_insert(objectkey):
    client = boto3.client('rekognition')
    response = client.index_faces(CollectionId=collection_id,
                                    Image={'S3Object':{'Bucket':photoS3,'Name':objectkey}},
                                    ExternalImageId= str(uuid.uuid4()),
                                    MaxFaces=1,
                                    QualityFilter="AUTO",
                                    DetectionAttributes=['ALL'])
    face_id = response['FaceRecords'][0]['Face']['FaceId']
    return face_id


#DB2 related part
def identify_fetch_DB2_face_by_faceId(face_id):
    db2 = boto3.resource('dynamodb')
    table = db2.Table(db2_name)
    response = table.get_item(Key = {"faceId": face_id})
    try: 
        DB2_face_info = response["Item"]
        if DB2_face_info["name"] != "":
            return DB2_face_info
        else:
            print("No official record in DB2, since there is no visitor name.")
            return None
    except:
        print("No relative photos in DB2 with faceId: ",face_id)
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
    table.put_item(
        Item = {
        "faceId": face_id,
        "name": name,
        "phoneNumber": phone_number,
        "photos": photos
    }
    )
        


#DB1 related part
def check_otp_DB1(face_id):
    db1 = boto3.resource('dynamodb')
    table = db1.Table(db1_name)
    response = table.get_item(Key = {"faceId": face_id})
    try:
        result = response["item"]
        if result["passcode"]:
            return True
    except:
        return False

def generate_otp():
    return random.randint(10000, 99999)

def store_otp_DB1(face_id, otp):
    #otp = generate_otp()
    db1 = boto3.resource('dynamodb')
    table = db1.Table(db1_name)
    response = table.put_item(
        Item = {
            'createdAtTimestamp' : str(datetime.datetime.now()),
            'ttl': int(datetime.datetime.now().timestamp()+ 300),
            'faceId': face_id,
            'passcode': otp,
        }
    )


def sendSMS(phone_number, message):
    client = boto3.client("sns")
    try:
        client.publish(
            PhoneNumber = phone_number,
            Message = message
        )
    except:
        print("SMS sending Error!")


#Photo Fetch Part
def getEndpoint(streamARN):
    kvs = boto3.client('kinesisvideo', region_name='us-east-1')
    kvs_endpoint = kvs.get_data_endpoint(
        APIName = "GET_MEDIA",
        StreamARN= streamARN
    )['DataEndpoint']
    return kvs_endpoint


def retrieve_photo(streamARN):
    kvs_endpoint = getEndpoint(streamARN)
    kvm = boto3.client('kinesis-video-media', endpoint_url = kvs_endpoint,region_name='us-east-1')
    kvs_stream = kvm.get_media(
        StreamARN = streamARN,
        StartSelector = {
            'StarSelectorType' : "NOW"
        }
    )
    kvs_stream = kvs_stream['Payload']
    photo_dir = '/tmp/picture.jpg'
    mkv_dir = '/tmp/video_clip.mkv'
    file = open(mkv_dir, 'wb')
    file.write(kvs_stream)
    vidcap = cv2.VideoCapture(mkv_dir)
    success, photo = vidcap.read()
    if success:
        #save the photo to photo_dir
        cv2.imwrite(photo_dir,photo)
    return photo_dir



#S3 Related Part
def append_photo_s3(photo_dir, face_id):
    s3_client = boto3.client('s3')
    addon_key = str(uuid.uuid4())
    key = face_id + '/' + addon_key + '.jpg'
    try:
        response = s3_client.upload_file(photo_dir, photoS3, key)
    except:
        print("S3 storing known visitor failure!")
    objectkey = key
    return objectkey

def append_unknown_temp_photo_s3(photo_dir):
    try:
        response = s3_client.upload_file(photo_dir, photoS3, 'current_visitor.jpg')
    except:
        print("S3 storing unknown visitor failure!")
    objectkey = 'current_visitor.jpg'
    return objectkey




def lambda_handler(event, context):
    for record in event["Records"]:
        payload=base64.b64decode(record["kinesis"]["data"])
        data = json.loads(payload.decode("ASCII"))
        streamARN = data["InputInformation"]["KinesisVideo"]["StreamArn"]
        fragmentNumber = data["InputInformation"]["KinesisVideo"]["FragmentNumber"]
        serverTimestamp = data["InputInformation"]["KinesisVideo"]["ServerTimestamp"]
        collection_face_details = data["FaceSearchResponse"]

        #Get the photo no matter known or unknown visitor
        photo_dir = retrieve_photo(streamARN)
        if_known, face_id = if_known_face(collection_face_details)

        #Known or Unknown
        if if_known == 0:
            print("No face at all, Error!")
        elif if_known == 1:
            print("The visitor was recognized by collections.")
            #Append in S3
            objectkey = append_photo_s3(photo_dir, face_id)
            ##check if known face in db2
            DB2_face_info = identify_fetch_DB2_face_by_faceId(face_id)

            #If in DB2, then update db2 + send sms to visitor
            if DB2_face_info:
                
                #update db2
                phone_number = retrieve_phoneNumber_DB2(DB2_face_info)
                name = DB2_face_info["name"]
                photos = DB2_face_info["photos"]
                append_photo_DB2(face_id, name, phone_number, photos, objectkey)

                if check_otp_DB1(face_id):
                    print("One time passcode has been sent, please check youir message.")
                else:
                    #Send OTP for double-known visitor
                    otp = generate_otp()
                    try:
                        store_otp_DB1(face_id, otp)
                    except:
                        print("Cannot store otp to visitors.")

                    message = "You are the one on file, please use the one time passcode. " + str(otp) + " The pass code will expire in 5 minutes"
                    sendSMS(phone_number, message)

            #If not in DB2, then create new index of DB2 and update or update directly
            else:
                #update DB2
                db2 = boto3.resource('dynamodb')
                table = db2.Table(db2_name)
                response = table.get_item(Key = {"faceId": face_id})
                try:
                    photos = response['Item']["photos"]
                    append_photo_DB2(face_id, "", "", photos, objectkey)
                except:
                    append_photo_DB2(face_id, "", "", [], objectkey)

                #Send owner the link
                #https://6998hw2s3.s3.amazonaws.com/captain-america
                s3_link ="https://"+photoS3+".s3.amazonaws.com/"+objectkey
                verification_link = wp1 + '/' + face_id

                message = "Well, master, we have a new visitor. Click here to view the photo. \n" 
                + s3_link + '\n' + "If you would like to admit him, please click here. \n" + verification_link

                sendSMS(ownerPhoneNumber, message)

        elif if_known == -1 or face_id == "":
            #For unknown visitor, append to collections then get face_id, then append to s3 and db2
            print("The visitor was NOT recognized by collections.")
            #append temp, no face_id, unknown visitor photo to s3
            objectkey_temp = append_unknown_temp_photo_s3(photo_dir)
            #Append photo with temp s3 link to collections
            #Get face_id from collections
            #objectkey = "current_visitor.jpg"
            face_id = collection_insert(objectkey_temp)
            #Append to s3
            #get official s3 link(object key) from s3
            official_objectkey = append_photo_s3(photo_dir, face_id)
            #Append to db2
            append_photo_DB2(face_id, "", "", [], official_objectkey)
            #Send verification link + s3 link to the owner
            s3_link ="https://"+photoS3+".s3.amazonaws.com/"+official_objectkey
            verification_link = wp1 + '/' + face_id

            message = "Well,well, master, we have a brand new visitor. Click here to view the photo. \n" + s3_link + '\n' + "If you would like to admit him, please click here. \n" + verification_link
            sendSMS(ownerPhoneNumber, message)

        return {
            'statusCode': 200,
            'body': json.dumps('You have reached the end line of LF1')}