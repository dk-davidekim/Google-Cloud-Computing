from flask import Flask, request
from google.cloud import storage, logging, pubsub_v1
from google.cloud.sql.connector import Connector
import os
from dotenv import load_dotenv
from datetime import datetime
import pymysql
import sqlalchemy
from sqlalchemy import text

app = Flask(__name__)

load_dotenv()

class DatabaseConnector:
    def __init__(self):
        db_connection_string = os.getenv('DB_CONNECTION_STRING')
        db_user = os.getenv('DB_USER')
        db_password = os.getenv('DB_PASSWORD')
        db_database = os.getenv('DB_DATABASE')

        self.connector = Connector()

        def getconn():
            return self.connector.connect(
                db_connection_string,
                "pymysql",
                user=db_user,
                password=db_password,
                db=db_database
            )

        self.pool = sqlalchemy.create_engine(
            "mysql+pymysql://",
            creator=getconn
        )

        self.initialize_database()

    def initialize_database(self):
        with self.pool.connect() as conn:
            conn.execute(text("CREATE DATABASE IF NOT EXISTS hw10db"))
            conn.execute(text("USE hw10db"))
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS Clients (
                    client_id INT AUTO_INCREMENT PRIMARY KEY,
                    client_ip VARCHAR(255) UNIQUE NOT NULL,
                    country VARCHAR(255),
                    gender VARCHAR(255),
                    age VARCHAR(255),
                    income VARCHAR(255),
                    is_banned BOOLEAN
                );
            """))
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS Files (
                    file_id INT AUTO_INCREMENT PRIMARY KEY,
                    file_name VARCHAR(255) UNIQUE NOT NULL
                );
            """))
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS Requests (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    client_id INT,
                    file_id INT,
                    time_of_day TIME,
                    FOREIGN KEY (client_id) REFERENCES Clients(client_id),
                    FOREIGN KEY (file_id) REFERENCES Files(file_id)
                );
            """))
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS ErrorCodes (
                    error_code_id INT AUTO_INCREMENT PRIMARY KEY,
                    error_code INT UNIQUE NOT NULL,
                    description TEXT
                );
            """))
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS Failed_Requests (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    time_of_request TIME,
                    file_id INT,
                    error_code_id INT,
                    FOREIGN KEY (file_id) REFERENCES Files(file_id),
                    FOREIGN KEY (error_code_id) REFERENCES ErrorCodes(error_code_id)
                );
            """))
            conn.commit()

class Logger:
    def __init__(self):
        project_id = 'ds-561'
        logger_name = 'hw10'

        self.logging_client = logging.Client(project=project_id)
        self.logger = self.logging_client.logger(logger_name)

    def log(self, message):
        self.logger.log_text(message)


class PubSub:
    def __init__(self):
        project_id = 'ds-561'
        topic_name = 'hw10-topic'

        self.pub_client = pubsub_v1.PublisherClient()
        self.topic_path = self.pub_client.topic_path(project_id, topic_name)

        self.logger = Logger()

    def publish(self, message):
        try:
            data = message.encode('utf-8')
            future = self.pub_client.publish(self.topic_path, data)
            message_id = future.result()
            self.logger.log(f"Message published with ID: {message_id}")
        except Exception as e:
            self.logger.log(f"PubSub Notification Failed: {str(e)}")


class DatabaseManager:
    def __init__(self):
        self.logger = Logger()
        self.error_codes = {
            9001: "No Headers - Required headers are missing",
            400: "Forbidden Access - Access denied due to client's country",
            404: "File Not Found - The requested file does not exist",
            501: "Method Not Implemented - The request method is not supported",
        }
        self.dbConnector = DatabaseConnector()

    def insert_client(self, country, client_ip, gender, age, income, is_banned):
        with self.dbConnector.pool.connect() as connection:
            try:
                result = connection.execute(
                    sqlalchemy.text("SELECT client_id FROM Clients WHERE client_ip = :client_ip"),
                    {"client_ip": client_ip}
                ).first()
                client_id = result[0] if result else None

                if client_id is None:
                    connection.execute(
                        sqlalchemy.text(
                            "INSERT INTO Clients (client_ip, country, gender, age, income, is_banned) "
                            "VALUES (:client_ip, :country, :gender, :age, :income, :is_banned)"
                        ),
                        {
                            "client_ip": client_ip,
                            "country": country,
                            "gender": gender,
                            "age": age,
                            "income": income,
                            "is_banned": is_banned
                        }
                    )
                    client_id = connection.execute(sqlalchemy.text("SELECT LAST_INSERT_ID()")).scalar()
                connection.commit()
                return client_id
            except Exception as e:
                self.logger.log(f"insert_client sql failed: {str(e)}")
                connection.rollback()

    def insert_file(self, requested_file):
        with self.dbConnector.pool.connect() as connection:
            try:
                result = connection.execute(
                    sqlalchemy.text("SELECT file_id FROM Files WHERE file_name = :requested_file"),
                    {"requested_file": requested_file}
                ).first()
                file_id = result[0] if result else None

                if file_id is None:
                    connection.execute(
                        sqlalchemy.text("INSERT INTO Files (file_name) VALUES (:requested_file)"),
                        {"requested_file": requested_file}
                    )
                    file_id = connection.execute(sqlalchemy.text("SELECT LAST_INSERT_ID()")).scalar()
                connection.commit()
                return file_id
            except Exception as e:
                self.logger.log(f"insert_file sql failed: {str(e)}")
                connection.rollback()

    def insert_error_code(self, error_code, description=""):
        with self.dbConnector.pool.connect() as connection:
            try:
                result = connection.execute(
                    sqlalchemy.text("SELECT error_code_id FROM ErrorCodes WHERE error_code = :error_code"),
                    {"error_code": error_code}
                ).first()
                error_code_id = result[0] if result else None

                if error_code_id is None:
                    connection.execute(
                        sqlalchemy.text(
                            "INSERT INTO ErrorCodes (error_code, description) VALUES (:error_code, :description)"
                        ),
                        {
                            "error_code": error_code,
                            "description": description
                        }
                    )
                    error_code_id = connection.execute(sqlalchemy.text("SELECT LAST_INSERT_ID()")).scalar()
                connection.commit()
                return error_code_id
            except Exception as e:
                self.logger.log(f"insert_error_code sql failed: {str(e)}")
                connection.rollback()

    def insert_request_or_failure(self, time_of_day, file_id, client_id, error_code_id):
        with self.dbConnector.pool.connect() as connection:
            try:
                if error_code_id:
                    # Insert into Failed_Requests
                    connection.execute(
                        sqlalchemy.text(
                            "INSERT INTO Failed_Requests (time_of_request, file_id, error_code_id) "
                            "VALUES (:time_of_day, :file_id, :error_code_id)"
                        ),
                        {
                            "time_of_day": time_of_day,
                            "file_id": file_id,
                            "error_code_id": error_code_id
                        }
                    )
                else:
                    # Insert into Requests
                    connection.execute(
                        sqlalchemy.text(
                            "INSERT INTO Requests (client_id, file_id, time_of_day) "
                            "VALUES (:client_id, :file_id, :time_of_day)"
                        ),
                        {
                            "client_id": client_id,
                            "file_id": file_id,
                            "time_of_day": time_of_day
                        }
                    )
                connection.commit()
            except Exception as e:
                self.logger.log(f"insert_request_or_failure sql failed: {str(e)}")
                connection.rollback()


    def handle_database(self, country, client_ip, gender, age, income, is_banned, time_of_day, requested_file, error_code):
        try:
            error_code_id = None
            file_id = self.insert_file(requested_file)
            client_id = self.insert_client(country, client_ip, gender, age, income, is_banned)

            if error_code:
                description = self.error_codes.get(error_code, "Unknown error")
                error_code_id = self.insert_error_code(error_code, description)

            self.insert_request_or_failure(time_of_day, file_id, client_id, error_code_id)

            self.logger.log('Handling database completed successfully')

        except Exception as e:
            self.logger.log(f'Error in handle_database: {e}')





# Main Application Service
class AppService:
    BANNED_COUNTRIES = ["North Korea", "Iran", "Cuba", "Myanmar",
                        "Iraq", "Libya", "Sudan", "Zimbabwe", "Syria"]

    def __init__(self):
        self.logger = Logger()
        self.pubsub = PubSub()
        self.db_manager = DatabaseManager()

    def handle_request(self, filename, request_method, headers):
        country = headers.get("X-country")
        client_ip = headers.get("X-client-IP")
        gender = headers.get("X-gender")
        age = headers.get("X-age")
        income = headers.get("X-income")

        if not (country and client_ip and gender and age and income):
            error_code = 9001 # Custom Error Code
            self.logger.log(f"Error Code 9001: No Header")
            return 'No Headers', error_code

        is_banned = country in AppService.BANNED_COUNTRIES

        time_of_day = datetime.now().strftime('%H:%M:%S')

        requested_file = filename.replace('hw10_bucket/', '')

        error_code = None

        if request_method == 'GET':
            if is_banned:
                data = str({'400 Forbidden from country': country})
                self.pubsub.publish(data)
                self.logger.log(f"Error Code 400: Forbidden: {str(country)}")
                error_code = 400
                self.db_manager.handle_database(country, client_ip, gender, age, income, is_banned, time_of_day, requested_file, error_code)
                return "Permission Denied", error_code

            try:
                storage_client = storage.Client()
                bucket = storage_client.bucket('hw10_bucket')
                blob = bucket.blob(requested_file)
                file_content = blob.download_as_text()
                self.logger.log(f"200: {requested_file}")
                self.db_manager.handle_database(country, client_ip, gender, age, income, is_banned, time_of_day, requested_file, error_code)
                return file_content, 200
            except Exception as e:
                self.logger.log(f"Error Code 404: {requested_file}: {str(e)}")
                error_code = 404
                self.db_manager.handle_database(country, client_ip, gender, age, income, is_banned, time_of_day, requested_file, error_code)
                return 'File not found', error_code

        else:
            error_code = 501
            self.db_manager.handle_database(country, client_ip, gender, age, income, is_banned, time_of_day, requested_file, error_code)
            self.logger.log(f"Error Code 501: {request_method}")
            return 'Not implemented', error_code

# Flask route handling
service = AppService()

@app.route('/', defaults={'path': ''}, methods=['GET', 'POST', 'PUT', 'DELETE', 'HEAD', 'CONNECT', 'OPTIONS', 'TRACE', 'PATCH'])
@app.route('/<path:filename>', methods=['GET', 'POST', 'PUT', 'DELETE', 'HEAD', 'CONNECT', 'OPTIONS', 'TRACE', 'PATCH'])
def app_one(filename):
    return service.handle_request(filename, request.method, request.headers)

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8080)
