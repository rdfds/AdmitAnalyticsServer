# Importing flask module in the project is mandatory
# An object of Flask class is our WSGI application.
import os
from google.cloud import firestore
from flask import Flask, request, jsonify 
import requests, json

# Flask constructor takes the name of 
# current module (__name__) as argument.
app = Flask(__name__)

# The route() function of the Flask class is a decorator, 
# which tells the application which URL should call 
# the associated function.
@app.route("/")
def hello_world():
    return "Hello World"

@app.route("/processuserinformation")
def processUserInformation():
    # Get the parameters from the request and convert to a dictionary
    data = request.args.to_dict()
    # Print or log the data for debugging purposes
    print(data)
    
    # Initialize Firestore
    credentials_path = 'firebase-credentials.json'
    db = initialize_firestore(credentials_path)
    
    # Define collection name and document ID (you may want to generate a unique ID or use a meaningful identifier)
    collection_name = 'userData'
    document_id = data.get('user_id', 'default_id')  # Use 'id' from data if present, otherwise 'default_id'
    
    # Store data in Firestore
    store_data_in_firestore(db, collection_name, document_id, data)
    
    # Return a JSON response
    return jsonify(data), 200

def initialize_firestore(credentials_path):
    # Set the environment variable for the Firestore credentials
    os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = credentials_path
    # Initialize Firestore client
    db = firestore.Client()
    return db

def store_data_in_firestore(db, collection_name, document_id, data):
    # Get a reference to the collection
    collection_ref = db.collection(collection_name)
    # Create or update a document with the specified ID
    doc_ref = collection_ref.document(document_id)
    # Set the data in the document
    doc_ref.set(data)
    print(f'Data stored in collection: {collection_name}, document ID: {document_id}')