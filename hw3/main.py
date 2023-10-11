from google.cloud import storage, logging, pubsub_v1
import functions_framework


def app_one(request):
    logging_client = logging.Client(project='ds-561')
    logger = logging_client.logger('hw3')

    if request.method == 'GET':                                         # Check if request method is 'GET'
        
        try:
            filename = request.path.lstrip('/')                         # Retrieve the link path "bucketname/directory/htmlfile"
            filename = filename.replace('bu-ds561-dk98-bucket/', '')    # Get rid of the bucketname

            storage_client = storage.Client()                           # Create storage client
            bucket = storage_client.bucket('bu-ds561-dk98-bucket')      # Assign the bucket
            
            blob = bucket.blob(filename)                                # Find the file inside the bucket
            file_content = blob.download_as_text()                      # Download the file as text
            
            logger.log_text(f"200: {filename}")
            return file_content, 200                                    # Return the file and 200 status
        
        except Exception as e:                                          # If there's an error in getting the file
            logger.log_text(f"Error Code 404: {filename}: {str(e)}")    # Log the error
            return 'File not found', 404                                # End function with a 404 status
            
    else:                                                               # If method is any other than 'GET'
        logger.log_text(f"Error Code 501: {request.method}")            # Log the 501 error
        return 'Not implemented', 501                                   # End function with a 501 status


from google.cloud import pubsub_v1                                      # Import PubSub from Google Cloud

pub = pubsub_v1.PublisherClient()                                       # Initiate publisher
path = pub.topic_path('ds-561', 'hw3')                                  # Configure publisher subscription path

BANNED_COUNTRIES = ["North Korea", "Iran", "Cuba", "Myanmar",           # List for banned countries
                    "Iraq", "Libya", "Sudan", "Zimbabwe", "Syria"]

def app_one_edited(request):                                            # Function that checks country and runs app_one
    logging_client = logging.Client(project='ds-561')
    logger = logging_client.logger('hw3')

    country = request.headers["X-country"]                              # Get the country name from http-client.py request

    if country in BANNED_COUNTRIES:                                     # If the country name is one of the banned countries
        try: 
            data = str({'400 Forbidden from country': country})         # Try publishing "forbidden"
            future=pub.publish(path, data.encode("utf-8"))
            message_id = future.result()
            logger.log_text(f"Message published with ID: {message_id}")
        except Exception as e:                                          # If there's an error log the error
            logger.log_text(f"PubSub Notification Failed {str(e)}")

        logger.log_text(f"Error Code 400: Forbidden: {str(country)}")   # Log error and abort with an error code 400
        return "Permission Denied", 400

    else:                                                               # If country is not banned
        app_one(request)                                                # Run app_one(request)


