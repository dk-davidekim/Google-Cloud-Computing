from flask import Flask, request
from google.cloud import storage, logging, pubsub_v1

app = Flask(__name__)

BANNED_COUNTRIES = ["North Korea", "Iran", "Cuba", "Myanmar",
                    "Iraq", "Libya", "Sudan", "Zimbabwe", "Syria"]

@app.route('/', defaults={'path': ''}, methods=['GET','POST','PUT', 'DELETE', 'HEAD', 'CONNECT', 'OPTIONS', 'TRACE', 'PATCH'])
@app.route('/<path:filename>', methods=['GET','POST','PUT', 'DELETE', 'HEAD', 'CONNECT', 'OPTIONS', 'TRACE', 'PATCH'])
def app_one(filename):
    logging_client = logging.Client(project='ds-561')
    logger = logging_client.logger('hw4')
    pub = pubsub_v1.PublisherClient()
    path = pub.topic_path('ds-561', 'hw3')

    if request.method == 'GET':
        country = request.headers.get("X-country", "")

        if country in BANNED_COUNTRIES:
            try: 
                data = str({'400 Forbidden from country': country})
                future = pub.publish(path, data.encode("utf-8"))
                message_id = future.result()
                logger.log_text(f"Message published with ID: {message_id}")
            except Exception as e:
                logger.log_text(f"PubSub Notification Failed {str(e)}")
            logger.log_text(f"Error Code 400: Forbidden: {str(country)}")
            return "Permission Denied", 400
        
        else:
            try:
                filename = filename.replace('bu-ds561-dk98-bucket/', '')
                storage_client = storage.Client()
                bucket = storage_client.bucket('bu-ds561-dk98-bucket')
                blob = bucket.blob(filename)
                file_content = blob.download_as_text()
                logger.log_text(f"200: {filename}")
                return file_content, 200
            except Exception as e:
                logger.log_text(f"Error Code 404: {filename}: {str(e)}")
                return 'File not found', 404
    else:
        logger.log_text(f"Error Code 501: {request.method}")
        return 'Not implemented', 501

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8080)
