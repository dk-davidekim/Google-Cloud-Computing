from google.cloud import pubsub_v1

def call_back(message):                                         # Callback if message received
    print(f"Received message: {message.data.decode('utf-8')}")  # Print the message
    message.ack()                                               

sub = pubsub_v1.SubscriberClient()                              # SubscriberClient
path = sub.subscription_path('ds-561', 'hw10-sub')              # Subscription Path

future = sub.subscribe(path, callback=call_back)                # Subscribe to the path and callback
print("Listening for messages on: {}".format(path))             # Indicating that it's listening

with sub:                                                       # Keep the app running
    try:
        future.result()
    except KeyboardInterrupt:
        future.cancel()