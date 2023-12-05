import os
import pandas as pd
import sqlalchemy
from dotenv import load_dotenv
from sklearn.ensemble import RandomForestClassifier
from sklearn.neural_network import MLPClassifier
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
from sklearn.metrics import accuracy_score
from google.cloud.sql.connector import Connector
from google.cloud import logging

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

class Logger:
    def __init__(self):
        project_id = os.getenv('GOOGLE_CLOUD_PROJECT_ID')
        logger_name = 'hw6'
        self.logging_client = logging.Client(project=project_id)
        self.logger = self.logging_client.logger(logger_name)

    def log(self, message):
        print(message)
        self.logger.log_text(message)

class Prediction:
    def __init__(self, db_interface):
        self.logger = Logger()
        self.db_interface = db_interface
        self.c_classifier = None
        self.i_classifier = None
        self.i_label_encoder = LabelEncoder()

    def predict_country(self):
        with self.db_interface.pool.connect() as conn:
            fetch_query = sqlalchemy.sql.text("SELECT client_ip, country FROM Clients")
            data = pd.read_sql(fetch_query, conn)
            
            data['binary_ip'] = data['client_ip'].apply(
                lambda ip: int(''.join([f'{int(byte):08b}' for byte in ip.split('.')]), 2)
            )
            
            features = data[['binary_ip']]
            labels = data['country']
            
            feature_train, feature_test, label_train, label_test = train_test_split(
                features, labels, test_size=0.3, random_state=0
            )
            
            model = RandomForestClassifier()
            model.fit(feature_train, label_train)
            
            predictions = model.predict(feature_test)
            accuracy = accuracy_score(label_test, predictions)
            self.logger.log(f'Accuracy of IP Classifier: {accuracy * 100:.2f}%')
            
            self.c_classifier = model

    def predict_income(self):
        with self.db_interface.pool.connect() as conn:
            fetch_query = sqlalchemy.sql.text("SELECT gender, age, country, is_banned, income FROM Clients")
            data = pd.read_sql(fetch_query, conn)
            
            y = self.i_label_encoder.fit_transform(data['income'])
            data = pd.get_dummies(data, columns=['gender', 'age', 'country', 'is_banned'])
            X = data.drop(['income'], axis=1)
            
            X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=0)
            
            mlp = MLPClassifier(hidden_layer_sizes=(50,), activation='relu', solver='adam', alpha=0.0001, learning_rate='adaptive', max_iter=100)
            mlp.fit(X_train, y_train)
            
            predictions = mlp.predict(X_test)
            accuracy = accuracy_score(y_test, predictions)
            self.logger.log(f'Accuracy of Income Classifier: {accuracy * 100:.2f}%')
            
            self.i_classifier = mlp

if __name__ == "__main__":
    db_connector = DatabaseConnector()
    db_interface = type('DBInterface', (object,), {'pool': db_connector.pool})
    prediction = Prediction(db_interface)
    prediction.predict_country()
    prediction.predict_income()
