# Importing flask module in the project is mandatory
# An object of Flask class is our WSGI application.
import csv
import os
from google.cloud import firestore
from flask import Flask, request, jsonify 
import requests, json
from openai import OpenAI

# Flask constructor takes the name of 
# current module (__name__) as argument.
app = Flask(__name__)

#ChatGPT API key
client = OpenAI(
    api_key = "sk-proj-czDzsNeDWP1ga6mioWZLT3BlbkFJNyywbxcSpmRdD1LB0Gc6",
)

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
    location_competitiveness = get_area_difficulty(data['location'])
    data['location_competitiveness'] = location_competitiveness
    # Print or log the data for debugging purposes
    print(data)
    
    # Initialize Firestore
    db = initialize_firestore('api/firebase-credentials.json')
    
    # Define collection name and document ID (you may want to generate a unique ID or use a meaningful identifier)
    collection_name = 'userData'
    document_id = data.get('user_id', 'default_id')  # Use 'id' from data if present, otherwise 'default_id'
    
    # Store data in Firestore
    store_data_in_firestore(db, collection_name, document_id, data)
    
    # Return a JSON response
    return jsonify(data), 200

def get_area_difficulty(location):
    client = OpenAI(
        api_key = "sk-proj-czDzsNeDWP1ga6mioWZLT3BlbkFJNyywbxcSpmRdD1LB0Gc6",
    )
    prompt = (
        f"Given this location description: {location}, rate the competitiveness of the area in terms of competitiveness in applying to college (ie, how hard is it to get into an selective american college being from here) from 1 to 10, where 10 is the most competitive and oversaturated, "
        "and 1 is the least competitive. If unsure becuase the description is too vague, provide a score of 5 or 6. If the prompt contains no description, return '-1' EXACTLY! "
        "Consider both domestic (US) and international locations. Try to think as a college admissions officer. \n\n"
        "Return ONLY the rating as a SINGLE number. The scale should be weighted so 5/6 is the average college applicant, 1 is extremely underrepresented, and 2 is extremely overrrepresented location"
    )
    
    response = client.chat.completions.create(
        #model = "gpt-3.5-turbo-0125",
        model = "gpt-4o",
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": prompt},
        ],
        functions=[
            {
                "name": "get_location_difficulty",
                "description": "Returns a number from 1-10 representing the competitiveness of applying to college from a given location",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "location_competitiveness": {
                            "type": "array",
                            "items": {
                                "type": "string"
                            }
                        }
                    },
                    "required": ["location_competitiveness"]
                }
            }
        ],
        function_call="auto"
    )
    
    try:
        function_response = completion.choices[0].message.function_call.arguments
        location_competitiveness = json.loads(function_response).get('location_competitiveness', [])
        return location_competitiveness
    except ValueError:
        # If the response is not a valid number, return a default value
        return -1

@app.route("/addusercollegeinformation")
def addUserCollegeInformation():
    # Get the parameters from the request
    user_id = request.args.get('user_id')
    major = request.args.get('major')
    college_desc = request.args.get('college_desc')
    
    # Print or log the data for debugging purposes
    print(f'user_id: {user_id}, major: {major}, college_desc: {college_desc}')
    
    # Initialize Firestore
    db = initialize_firestore('api/firebase-credentials.json')
    
    # Define collection name and document ID
    collection_name = 'userData'
    document_id = user_id
    
    # Get a reference to the document
    doc_ref = db.collection(collection_name).document(document_id)
    
    # Load college data from CSV
    college_data = load_college_data('api/us_universities.csv')
    
    # Get the structured list of interested colleges and major
    interested_colleges = get_interested_colleges(college_desc, college_data)
    major = get_similar_major(major)
    #return major
    #return major
    # Update the document with the new information
    doc_ref.update({
        'major': major,
        'interested_colleges': interested_colleges
    })

    response = find_similar_entries(user_id, interested_colleges, major)
    return response
    # Return a JSON response
    #return jsonify({'status': 'success', 'user_id': user_id, 'major': major, 'college_desc': college_desc}), 200


def load_college_data(csv_file):
    college_data = []
    with open(csv_file, 'r') as file:
        reader = csv.reader(file)
        for row in reader:
            college_data.append({
                'name': row[0],
            })
    return college_data

def get_interested_colleges(college_desc, college_data):
    completion = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "You are a helpful assistant that structures college descriptions."},
            {"role": "user", "content": f"Given the following description of college preferences: '{college_desc}', and the list of all US colleges, return a list of all the colleges that match the preferences"}
        ],
        functions=[
            {
                "name": "get_college_list",
                "description": "Returns a structured list of colleges based on the description of preferences.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "college_list": {
                            "type": "array",
                            "items": {
                                "type": "string"
                            }
                        }
                    },
                    "required": ["college_list"]
                }
            }
        ],
        function_call="auto"
    )

    function_response = completion.choices[0].message.function_call.arguments
    structured_colleges = json.loads(function_response).get('college_list', [])

    return structured_colleges

def calculate_score(value_user, value_entry, buffer, max_score, reduction_factor):
    if value_user == value_entry:
        return max_score
    elif abs(value_user - value_entry) <= buffer:
        return max_score * reduction_factor
    else:
        return 0

def calculate_similarity(user_info, entry):
    score = 0
    max_points = 0

    # Define the weights for each category
    weights = {
        'race': 15,
        'income': 7,
        'fin_aid': 3,
        'first_gen': 15,
        'urm_status': 15,
        'school_type': 7,
        'major': 20,
        #'sat_score': 15,
        #'act_score': 15,
        'course_rigor': 5,
        'school_competitiveness': 10,
        'location_competitiveness': 15,
        'legacy': 25
    }
    
    # Simple attribute checks
    for attribute in ['race', 'income', 'fin_aid', 'first_gen', 'urm_status', 'school_type', 'major']:
        if user_info[attribute] == entry[attribute]:
            score += weights[attribute]
        max_points += weights[attribute]

    # Complex attribute checks
    #score += calculate_score(user_info['sat_score'], entry['sat_score'], 100, weights['sat_score'], 0.1)
    #score += calculate_score(user_info['act_score'], entry['act_score'], 4, weights['act_score'], 0.2)
    score += calculate_score(user_info['course_rigor'], entry['course_rigor'], 1, weights['course_rigor'], 0.5)
    score += calculate_score(user_info['school_competitiveness'], entry['school_competitiveness'], 1, weights['school_competitiveness'], 0.5)
    score += calculate_score(user_info['location_competitiveness'], entry['location_competitiveness'], 2, weights['location_competitiveness'], [0.25, 0.75])

    # Legacy check
    user_legacy = user_info['legacy']
    entry_legacy = entry['legacy']
    for u_legacy in user_legacy:
        for e_legacy in entry_legacy:
            u_num, u_school = u_legacy.split('-')
            e_num, e_school = e_legacy.split('-')
            if u_school == e_school:
                num_diff = abs(int(u_num) - int(e_num))
                if num_diff == 0:
                    score += weights['legacy']
                elif num_diff == 1:
                    score += weights['legacy'] * 0.5
                elif num_diff == 2:
                    score += weights['legacy'] * 0.25
    max_points += weights['legacy']

    similarity_percentage = (score / max_points) * 100
    return similarity_percentage

def get_user_info(user_id, db):
    doc_ref = db.collection('userData').document(user_id)
    doc = doc_ref.get()
    if doc.exists:
        return doc.to_dict()
    else:
        return None

def get_all_entries(db):
    activities = db.collection('activities').stream()
    demographics = db.collection('demographics').stream()
    academics = db.collection('academics').stream()
    majors = db.collection('majors').stream()
    results = db.collection('results').stream()
    
    activities_data = [doc.to_dict() for doc in activities]
    demographics_data = {doc.id: doc.to_dict() for doc in demographics}
    academics_data = {doc.id: doc.to_dict() for doc in academics}
    majors_data = {doc.id: doc.to_dict() for doc in majors}
    results_data = {doc.id: doc.to_dict() for doc in results}
    
    return activities_data, demographics_data, academics_data, majors_data, results_data

def filter_entries_by_colleges(interested_colleges, results_data):
    filtered_post_ids = []
    
    # Normalize interested_colleges
    normalized_interested_colleges = [college.strip().lower().replace(' ', '_') for college in interested_colleges]
    count = 0
    for result in results_data.values():
        accepted_colleges = result.get('accepted_colleges', [])
        normalized_accepted_colleges = [college.strip().lower().replace(' ', '_') for college in accepted_colleges]
        
        if any(college in normalized_accepted_colleges for college in normalized_interested_colleges):
            filtered_post_ids.append(result['post_id'])
            count += 1
    return filtered_post_ids, count

def filter_entries_by_major(user_major, majors_data):
    user_major_normalized = user_major.strip().lower().replace(' ', '_')
    #input_major_formatted = user_major.upper().strip().replace(' ', '_')
    #return input_major_formatted, 0
    user_major_category = get_major_category(user_major_normalized)
    #return user_major_category, user_major_normalized
    #return str(user_major_category), str(user_major_category)
    if not user_major_category:
        return [], 0

    filtered_post_ids = []
    count = 0
    for result in majors_data.values():
        post_major = result.get('similar_major', '').strip().lower().replace(' ', '_')
        post_major_category = get_major_category(post_major)
        if post_major_category == user_major_category:
            filtered_post_ids.append(result['post_id'])
            count += 1
    
    return filtered_post_ids, count

# Load major categories from the CSV file
def load_major_categories(csv_file):
    major_categories = {}
    with open(csv_file, 'r') as file:
        reader = csv.reader(file)
        next(reader)  # Skip the header row
        for row in reader:
            major = row[1].strip().lower().replace(' ', '_')  # Ensure consistent formatting
            category = row[2].strip().lower().replace(' ', '_')
            major_categories[major] = category
    return major_categories

def get_major_category(input_major):
    return load_major_categories('api/majors-list.csv')[input_major]
    #return load_major_categories('api/majors-list.csv')

def get_similar_major(input_major):
    major_categories = load_major_categories('api/majors-list.csv')
    major_list = list(major_categories.keys())
    input_major = input_major.replace(' ', '_')

    for major in major_list:
        if major.lower().strip() == input_major.lower().strip():
            return major

    client = OpenAI(
        api_key="sk-proj-czDzsNeDWP1ga6mioWZLT3BlbkFJNyywbxcSpmRdD1LB0Gc6",
    )
    
    prompt = f"Given the major '{input_major}', identify the major is is equivalent or closest to from this list: {', '.join(major_categories)}"
    
    response = client.chat.completions.create(
        model="gpt-4-turbo",
        messages=[
            {"role": "system", "content": "You are assisting in finding the most similar major."},
            {"role": "user", "content": prompt}
        ],
        max_tokens=50,
        stop=None

    )
    
    function_response = response.choices[0].message.content
    
    # Extract the closest major from the response
    closest_major = None
    for major in major_list:
        if major.lower() in function_response.lower():
            closest_major = major
            break
    
    return closest_major if closest_major else "n/a or undecided"

def compile_entry(post_id, demographics_data, academics_data, majors_data):
    entry = {}
    entry.update(demographics_data[post_id])
    entry.update(academics_data[post_id])
    entry.update(majors_data[post_id])
    return entry

def find_similar_entries(user_id, interested_colleges, major):
    db = initialize_firestore('api/firebase-credentials.json')
    user_info = get_user_info(user_id, db)
    #return str(user_info)
    if not user_info:
        return jsonify({"error": "User not found"}), 404
    
    activities_data, demographics_data, academics_data, majors_data, results_data = get_all_entries(db)
    
    filtered_post_ids_colleges, count = filter_entries_by_colleges(interested_colleges, results_data)
    filtered_post_ids_majors, count2 = filter_entries_by_major(major, majors_data)
    filtered_post_ids = find_intersection(filtered_post_ids_majors, filtered_post_ids_colleges)
    similar_entries = []
    #return str(filtered_post_ids_majors) + " "  + str(count2)
    #str1 = str(interested_colleges) + " and then " + str(results_data)
    #return str1
    return str(filtered_post_ids_majors)
    for post_id in filtered_post_ids:
        entry = compile_entry(post_id, demographics_data, academics_data, majors_data)
        similarity = calculate_similarity(user_info, entry)
        similar_entries.append((entry, similarity))
    #return similar_entries[0]
    similar_entries.sort(key=lambda x: x[1], reverse=True)
    top_20_entries = similar_entries[:20]
    
    # Store the top 20 entries in Firestore
    #store_data_in_firestore(db, 'similarProfiles', user_id, top_20_entries)
    
    #return jsonify(top_20_entries), 200

def find_intersection(college_filtered_ids, major_filtered_ids):
    return list(set(college_filtered_ids) & set(major_filtered_ids))

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