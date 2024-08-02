# Importing flask module in the project is mandatory
# An object of Flask class is our WSGI application.
import csv
import os
from google.cloud import firestore
from flask import Flask, request, jsonify 
import requests, json
from openai import OpenAI
import string

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
    if (data['location'] == "none"):
        location_competitiveness = -1
    else:
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
    return "success"

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
                            "type": "integer",
                        }
                    },
                    "required": ["location_competitiveness"]
                }
            }
        ],
        function_call="auto"
    )
    
    try:
        function_response = response.choices[0].message.function_call.arguments
        location_competitiveness = json.loads(function_response).get('location_competitiveness', 5)
        return location_competitiveness
    except ValueError:
        # If the response is not a valid number, return a default value
        return 5

@app.route("/addusercollegeinformation")
def addUserCollegeInformation():
    # Get the parameters from the request
    user_id = request.args.get('user_id')
    major = request.args.get('major')
    college_desc = request.args.get('college_desc')

    translator = str.maketrans('', '', string.punctuation)
    # Use the translate method to remove all punctuation
    college_desc = college_desc.translate(translator)
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
    #.replace(",", "")?
    interested_colleges = get_interested_colleges(college_desc, college_data)
    return jsonify({"interested_colleges" : interested_colleges})
    major = get_similar_major(major)
    #return major
    #return major
    # Update the document with the new information
    doc_ref.update({
        'major': major,
        'interested_colleges': interested_colleges
    })

    return "success"

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
        #try to fix this make it work for more descriptions
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "You are a helpful assistant that structures college descriptions."},
            {"role": "user", "content": f"Given the following description of college preferences/categories of interest: '{college_desc}', and the list of all known US colleges: '{college_data}', return a list of all the colleges that match the preferences/categories"}
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

def calculate_similarity(user_info, post_id, demographics_data, academics_data, majors_data):
    score = 0
    max_points = 0

    # Define the weights for each category
    weights = {
        'race': 30,
        'income': 10,
        'fin_aid': 5,
        'first_gen': 20,
        'urm_status': 15,
        'school_type': 7,
        'major': 10,
        #'sat_score': 15,
        #'act_score': 15,
        #'course_rigor': 5,
        'school_competitiveness': 10,
        'location_competitiveness': 15,
        #'legacy': 25
    }
    idx = 0
    demographics_list = []
    # Simple attribute checks
    for result in demographics_data.values():
        if result.get('post_id') == post_id:
            idx+= 1
            demographics_list.append(result.get('race'))
            demographics_list.append(result.get('family_income_level')) 
            demographics_list.append(result.get('requesting_financial_aid'))
            demographics_list.append(result.get('first_generation'))
            demographics_list.append(result.get('underrepresented_minority_status'))
            demographics_list.append(result.get('school_type'))
            demographics_list.append(result.get('school_competitiveness'))
            demographics_list.append(result.get('location_competitiveness'))
            demographics_list.append(result.get('legacy_donor_connection'))

    #return str(demographics_list) + post_id + " " + str(idx)
    score = 0
    count = 0
    for attribute in ['race', 'income', 'fin_aid', 'first_gen', 'urm_status', 'school_type']:
        if user_info[attribute] != "-1" and demographics_list[count] != "-1":
            if user_info[attribute].lower().strip().replace(' ', '_') == demographics_list[count].lower().strip().replace(' ', '_'):
                score += weights[attribute]
            max_points += weights[attribute]
        count += 1

    # Complex attribute checks
    #score += calculate_score(user_info['sat_score'], entry['sat_score'], 100, weights['sat_score'], 0.1)
    #score += calculate_score(user_info['act_score'], entry['act_score'], 4, weights['act_score'], 0.2)
    #score += calculate_score(user_info['course_rigor'], entry['course_rigor'], 1, weights['course_rigor'], 0.5)
    #competitveness typo in userdata table
    if user_info['school_competitveness'] != "-1" and demographics_list[6] != "-1":
        score += calculate_score(int(user_info['school_competitveness']), int(demographics_list[6]), 1, weights['school_competitiveness'], 0.5)
        max_points += weights['major']


    if user_info['location_competitiveness'] != "-1" and demographics_list[7] != "-1":
        score += calculate_score(int(user_info['location_competitiveness']), int(demographics_list[7]), 2, weights['location_competitiveness'], 0.5)
        max_points += weights['major']

    # Major attribute check
    for result in majors_data.values():
        if result.get('post_id') == post_id:
            major = result.get('similar_major')

    if user_info['major'] != "-1" and major != "-1":
        if user_info['major'].lower().strip().replace(' ', '_') == major.lower().strip().replace(' ', '_'):
            score += weights['major']
        max_points += weights['major']

    # Legacy check
    #user_legacy = user_info['legacy']
    #entry_legacy = demographics_list[8]
    #if "-" in user_legacy and "-" in entry_legacy:
    #    for u_legacy in user_legacy:
    #        for e_legacy in entry_legacy:
    #            u_num, u_school = u_legacy.split('-')
    #            e_num, e_school = e_legacy.split('-')
    #            if u_school == e_school:
    #                num_diff = abs(int(u_num) - int(e_num))
    #                if num_diff == 0:
    #                    score += weights['legacy']
    #                elif num_diff == 1:
    #                    score += weights['legacy'] * 0.5
    #                elif num_diff == 2:
    #                    score += weights['legacy'] * 0.25
    #    max_points += weights['legacy']

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
    majors = db.collection('major').stream()
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
        count += 1
        accepted_colleges = result.get('accepted_colleges', [])
        normalized_accepted_colleges = [college.strip().lower().replace(' ', '_') for college in accepted_colleges]
        
        if any(college in normalized_accepted_colleges for college in normalized_interested_colleges):
            filtered_post_ids.append(result['post_id'])
    return filtered_post_ids, count

def filter_entries_by_major(user_major, majors_data):
    user_major_normalized = user_major.strip().lower().replace(' ', '_')
    #input_major_formatted = user_major.upper().strip().replace(' ', '_')
    #return input_major_formatted, 0
    user_major_category = get_major_category(user_major_normalized)
    if not user_major_category:
        return []

    filtered_post_ids = []
    count = 0
    for result in majors_data.values():
        count += 1
        post_major = result.get('similar_major', '').strip().lower().replace(' ', '_')
        post_major_category = get_major_category(post_major)
        if post_major_category == user_major_category:
            filtered_post_ids.append(result['post_id'])
    
    return filtered_post_ids, len(majors_data)

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
    majors_list = load_major_categories('api/majors-list.csv')
    return majors_list.get(str(input_major))

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

@app.route("/findsimilarapplicants")
def find_similar_entries():
    user_id = request.args.get('user_id')
    db = initialize_firestore('api/firebase-credentials.json')
    user_info = get_user_info(user_id, db)
    interested_colleges = user_info['interested_colleges']
    major = user_info['major']
    #return str(user_info['location_competitiveness'])
    if not user_info:
        return jsonify({"error": "User not found"}), 404
    
    activities_data, demographics_data, academics_data, majors_data, results_data = get_all_entries(db)
    filtered_post_ids_colleges, count = filter_entries_by_colleges(interested_colleges, results_data)
    #return str((majors_data))
    filtered_post_ids_majors, count2 = filter_entries_by_major(major, majors_data)
    filtered_post_ids = find_intersection(filtered_post_ids_majors, filtered_post_ids_colleges)
    similar_entries = []

    #return calculate_similarity(user_info, filtered_post_ids[1], demographics_data, academics_data, majors_data)
    #return str(len(demographics_data)) + " " + str(demographics_data)

    #return str(filtered_post_ids_majors) + " " + str(count)
    #str1 = str(interested_colleges) + " and then " + str(results_data)
    #return str1
    #return str(filtered_post_ids) + " " + str(filtered_post_ids_colleges) + " " + str(count) + " " + str(filtered_post_ids_majors) + " " + str(count2)
    for post_id in filtered_post_ids:
        similarity = int(calculate_similarity(user_info, post_id, demographics_data, academics_data, majors_data))
        #return str(similarity)
        #entry = compile_entry(post_id, demographics_data, academics_data, majors_data)
        similar_entries.append((post_id, similarity))
    
    similar_entries.sort(key=lambda x: x[1], reverse=True)
    top_10_entries = similar_entries[:10]

    
    # Prepare JSON object to be returned
    detailed_top_10_entries = []
    detailed_top_10_entries_dict = {}
    idx = 0
    for entry in top_10_entries:
        idx += 1
        post_id = entry[0]
        similarity_score = entry[1]
        for result in demographics_data.values():
            if result.get('post_id') == post_id:       
                race_entry = result.get('race')
                if race_entry == "-1" or "-1" in race_entry or race_entry is None or race_entry == "":
                    race_entry = "N/A"
                else:
                    race_entry = race_entry.lower().capitalize()
                
                family_income_entry = result.get('family_income_level')
                if family_income_entry == "-1" or "-1" in family_income_entry or family_income_entry is None or family_income_entry == "":
                    family_income_entry = "N/A"
                else:
                    family_income_entry = family_income_entry.lower().capitalize()

                first_generation_entry = result.get('first_generation')
                if first_generation_entry == "-1" or "-1" in first_generation_entry or first_generation_entry is None or first_generation_entry == "":
                    first_generation_entry = "N/A"
                elif first_generation_entry == "y":
                    first_generation_entry = "Yes"
                elif first_generation_entry == "n":
                    first_generation_entry = "No"

                underrepresented_minority_status_entry = result.get('underrepresented_minority_status')
                if underrepresented_minority_status_entry == "-1" or "-1" in underrepresented_minority_status_entry or underrepresented_minority_status_entry is None or underrepresented_minority_status_entry == "":
                    underrepresented_minority_status_entry = "N/A"
                elif underrepresented_minority_status_entry == "y":
                    underrepresented_minority_status_entry = "Yes"
                elif underrepresented_minority_status_entry == "n":
                    underrepresented_minority_status_entry = "No"

                school_type_entry = result.get('school_type')
                if school_type_entry == "-1" or "-1" in school_type_entry or school_type_entry is None or school_type_entry == "":
                    school_type_entry = "N/A"
                else:
                    school_type_entry = school_type_entry.lower().capitalize()

                requesting_financial_aid_entry = result.get('requesting_financial_aid')
                if requesting_financial_aid_entry == "-1" or "-1" in requesting_financial_aid_entry or requesting_financial_aid_entry is None or requesting_financial_aid_entry == "":
                    requesting_financial_aid_entry = "N/A"
                elif requesting_financial_aid_entry == "y":
                    requesting_financial_aid_entry = "Yes"
                elif requesting_financial_aid_entry == "n":
                    requesting_financial_aid_entry = "No"

                school_competitiveness_entry = result.get('school_competitiveness')
                if school_competitiveness_entry == "-1" or "-1" in school_competitiveness_entry or school_competitiveness_entry is None or school_competitiveness_entry == "":
                    school_competitiveness_entry = "N/A"

                detailed_entry = {
                    "student_number": str(idx),
                    "post_id": post_id,
                    "similarity_score": similarity_score,
                    "race": race_entry,
                    "family_income_level" : family_income_entry,
                    "first_generation" : first_generation_entry,
                    "underrepresented_minority_status" : underrepresented_minority_status_entry,
                    "school_type" : school_type_entry,
                    "requesting_financial_aid" : requesting_financial_aid_entry,
                    "school_competitiveness" : school_competitiveness_entry,
                    "location_competitiveness" : result.get("location_competitiveness"),
                    "legacy_donor_connection" : result.get("legacy_donor_connection")
                }
        
        for result in majors_data.values():
            if result.get('post_id') == post_id:
                major_entry = result.get('similar_major')
                if major_entry == "-1" or "-1" in major_entry or major_entry is None or major_entry == "":
                    major_entry = "N/A"
                else:
                    major_entry = major_entry.lower().capitalize()
                major_entry_dict = {
                    "major" : major_entry
                }
                detailed_entry.update(major_entry_dict)
                
                detailed_top_10_entries_dict['match_' + str(idx)] = detailed_entry
                detailed_top_10_entries.append(detailed_entry)

    # Store the top 10 entries in Firestore
    store_data_in_firestore(db, 'similarProfiles', user_id, detailed_top_10_entries_dict)

    return jsonify(detailed_top_10_entries)

    
def find_intersection(college_filtered_ids, major_filtered_ids):
    return list(set(college_filtered_ids) & set(major_filtered_ids))

@app.route("/getallapplicantinfo")
def get_all_applicant_info():
    user_id = request.args.get("user_id")
    student_number = int(request.args.get("student_number"))

    # Initialize Firestore
    db = initialize_firestore('api/firebase-credentials.json')
    activities_data, demographics_data, academics_data, majors_data, results_data = get_all_entries(db)

    # Fetch the similar profiles document for the given user_id
    similar_profiles_ref = db.collection('similarProfiles').document(user_id)
    similar_profiles_doc = similar_profiles_ref.get()

    post_id = ""

    if similar_profiles_doc.exists:
        similar_profiles_data = similar_profiles_doc.to_dict()

        # Find the entry corresponding to the given student_number
        match_key = f"match_{student_number}"
        if match_key in similar_profiles_data:
            post_id = similar_profiles_data[match_key].get('post_id')

    detailed_entry = {}

    for result in demographics_data.values():
        if result.get('post_id') == post_id:
            race_entry = result.get('race')
            if race_entry == "-1" or "-1" in race_entry or race_entry is None or race_entry == "":
                race_entry = "N/A"
            else:
                race_entry = race_entry.lower().capitalize()
            
            family_income_entry = result.get('family_income_level')
            if family_income_entry == "-1" or "-1" in family_income_entry or family_income_entry is None or family_income_entry == "":
                family_income_entry = "N/A"
            else:
                family_income_entry = family_income_entry.lower().capitalize()

            first_generation_entry = result.get('first_generation')
            if first_generation_entry == "-1" or "-1" in first_generation_entry or first_generation_entry is None or first_generation_entry == "":
                first_generation_entry = "N/A"
            elif first_generation_entry == "y":
                first_generation_entry = "Yes"
            elif first_generation_entry == "n":
                first_generation_entry = "No"

            underrepresented_minority_status_entry = result.get('underrepresented_minority_status')
            if underrepresented_minority_status_entry == "-1" or "-1" in underrepresented_minority_status_entry or underrepresented_minority_status_entry is None or underrepresented_minority_status_entry == "":
                underrepresented_minority_status_entry = "N/A"
            elif underrepresented_minority_status_entry == "y":
                underrepresented_minority_status_entry = "Yes"
            elif underrepresented_minority_status_entry == "n":
                underrepresented_minority_status_entry = "No"

            school_type_entry = result.get('school_type')
            if school_type_entry == "-1" or "-1" in school_type_entry or school_type_entry is None or school_type_entry == "":
                school_type_entry = "N/A"
            else:
                school_type_entry = school_type_entry.lower().capitalize()

            requesting_financial_aid_entry = result.get('requesting_financial_aid')
            if requesting_financial_aid_entry == "-1" or "-1" in requesting_financial_aid_entry or requesting_financial_aid_entry is None or requesting_financial_aid_entry == "":
                requesting_financial_aid_entry = "N/A"
            elif requesting_financial_aid_entry == "y":
                requesting_financial_aid_entry = "Yes"
            elif requesting_financial_aid_entry == "n":
                requesting_financial_aid_entry = "No"

            school_competitiveness_entry = result.get('school_competitiveness')
            if school_competitiveness_entry == "-1" or "-1" in school_competitiveness_entry or school_competitiveness_entry is None or school_competitiveness_entry == "":
                school_competitiveness_entry = "N/A"

            demographics_entry = {
                "race": race_entry,
                "family_income_level" : family_income_entry,
                "first_generation" : first_generation_entry,
                "underrepresented_minority_status" : underrepresented_minority_status_entry,
                "school_type" : school_type_entry,
                "requesting_financial_aid" : requesting_financial_aid_entry,
                "school_competitiveness" : result.get('school_competitiveness'),
                "location_competitiveness" : result.get("location_competitiveness"),
                "legacy_donor_connection" : result.get("legacy_donor_connection")
            }
            detailed_entry.update(demographics_entry)
    
    for result in majors_data.values():
        if result.get('post_id') == post_id:
            major_entry = result.get('similar_major')
            if major_entry == "-1" or "-1" in major_entry or major_entry is None or major_entry == "":
                major_entry = "N/A"
            else:
                major_entry = major_entry.lower().capitalize()
            major_entry_dict = {
                "major" : major_entry
            }
            detailed_entry.update(major_entry_dict)
            

    for result in academics_data.values():
        if result.get('post_id') == post_id:
            act_score_entry = result.get('act_score')
            if act_score_entry == "-1" or "-1" in act_score_entry or act_score_entry is None or act_score_entry == "":
                act_score_entry = "N/A"
            else:
                act_score_entry = act_score_entry
            
            sat_score_entry = result.get('sat_score')
            if sat_score_entry == "-1" or "-1" in sat_score_entry or sat_score_entry is None or sat_score_entry == "":
                sat_score_entry = "N/A"
            else:
                sat_score_entry = sat_score_entry  

            course_rigor_entry = result.get('course_rigor')
            if course_rigor_entry == "-1" or "-1" in course_rigor_entry or course_rigor_entry is None or course_rigor_entry == "":
                course_rigor_entry = "N/A"
            else:
                course_rigor_entry = course_rigor_entry            
            academics_entry = {
                "act_score": act_score_entry,
                "sat_score": sat_score_entry,
                "gpa": result.get('gpa'),
                "course_rigor": course_rigor_entry
            }
            detailed_entry.update(academics_entry)

    activities_list = []

    count = 0
    for result in activities_data:
        if result.get('post_id') == post_id:
            count+=1
            activity_entry = {
                "activity": result.get('activity'),
                "category_tags": result.get('category_tags'),
                "diversity_uniqueness_score": result.get('diversity_uniqueness_score'),
                "leadership_initiative_score": result.get('leadership_initiative_score'),
                "saturation_of_broader_category": result.get('saturation_of_broader_category'),
                "scale_impact_reach_score": result.get('scale_impact_reach_score'),
                "school_hook": result.get('school_hook')
            }
            activities_list.append(activity_entry)

    detailed_entry["activities"] = activities_list
    detailed_entry["activity_count"] = count

    for result in results_data.values():
        if result.get('post_id') == post_id:
            results_entry = {
                "accepted_colleges": result.get('accepted_colleges'),
                "accepted_colleges_len": len(result.get('accepted_colleges')),
                "rejected_colleges": result.get('rejected_colleges'),
                "rejected_colleges_len": len(result.get('rejected_colleges'))
            }
            detailed_entry.update(results_entry)

    full_info_list = [detailed_entry]

    return jsonify(full_info_list)

@app.route("/getactivities")
def get_activities():
    user_id = request.args.get("user_id")
    student_number = int(request.args.get("student_number"))

    # Initialize Firestore
    db = initialize_firestore('api/firebase-credentials.json')
    activities_data, demographics_data, academics_data, majors_data, results_data = get_all_entries(db)

    # Fetch the similar profiles document for the given user_id
    similar_profiles_ref = db.collection('similarProfiles').document(user_id)
    similar_profiles_doc = similar_profiles_ref.get()

    post_id = ""

    if similar_profiles_doc.exists:
        similar_profiles_data = similar_profiles_doc.to_dict()

        # Find the entry corresponding to the given student_number
        match_key = f"match_{student_number}"
        if match_key in similar_profiles_data:
            post_id = similar_profiles_data[match_key].get('post_id')

    activities_list = []

    for result in activities_data:
        if result.get('post_id') == post_id:
            string_removed_underscore = result.get('activity').replace("_", " ")
            capitalized_string = string_removed_underscore.capitalize()
            # Format the string to include quotes
            activity_entry = {
                "activity": capitalized_string
            }
            activities_list.append(activity_entry)

    if len(activities_list) == 0:
        activities_list = []
        activities_list.append({"activity" : "None!"})

    return jsonify(activities_list) 

@app.route("/getacceptedcolleges")
def get_accepted_colleges():
    user_id = request.args.get("user_id")
    student_number = int(request.args.get("student_number"))

    # Initialize Firestore
    db = initialize_firestore('api/firebase-credentials.json')
    activities_data, demographics_data, academics_data, majors_data, results_data = get_all_entries(db)

    # Fetch the similar profiles document for the given user_id
    similar_profiles_ref = db.collection('similarProfiles').document(user_id)
    similar_profiles_doc = similar_profiles_ref.get()

    post_id = ""

    if similar_profiles_doc.exists:
        similar_profiles_data = similar_profiles_doc.to_dict()

        # Find the entry corresponding to the given student_number
        match_key = f"match_{student_number}"
        if match_key in similar_profiles_data:
            post_id = similar_profiles_data[match_key].get('post_id')

    accepted_colleges_list = []

    for result in results_data.values():
        if result.get('post_id') == post_id:
            accepted_colleges = result.get('accepted_colleges', [])
            for college in accepted_colleges:
                string_removed_underscore = college.replace("_", " ")
                capitalized_string = string_removed_underscore.capitalize()
                # Format the string to include quotes
                accepted_colleges_list.append({"accepted_college": capitalized_string})

    if len(accepted_colleges_list) == 0:
        accepted_colleges_list = []
        accepted_colleges_list.append({"accepted_college": "None!"})

    return jsonify(accepted_colleges_list)

@app.route("/getrejectedcolleges")
def get_rejected_colleges():
    user_id = request.args.get("user_id")
    student_number = int(request.args.get("student_number"))

    # Initialize Firestore
    db = initialize_firestore('api/firebase-credentials.json')
    activities_data, demographics_data, academics_data, majors_data, results_data = get_all_entries(db)

    # Fetch the similar profiles document for the given user_id
    similar_profiles_ref = db.collection('similarProfiles').document(user_id)
    similar_profiles_doc = similar_profiles_ref.get()

    post_id = ""

    if similar_profiles_doc.exists:
        similar_profiles_data = similar_profiles_doc.to_dict()

        # Find the entry corresponding to the given student_number
        match_key = f"match_{student_number}"
        if match_key in similar_profiles_data:
            post_id = similar_profiles_data[match_key].get('post_id')

    rejected_colleges_list = []

    for result in results_data.values():
        if result.get('post_id') == post_id:
            rejected_colleges = result.get('rejected_colleges', [])
            for college in rejected_colleges:
                string_removed_underscore = college.replace("_", " ")
                capitalized_string = string_removed_underscore.capitalize()
                # Format the string to include quotes
                rejected_colleges_list.append({"rejected_college": capitalized_string})

    if len(rejected_colleges_list) == 0:
        rejected_colleges_list = []
        rejected_colleges_list.append({"rejected_college": "None!"})

    return jsonify(rejected_colleges_list)


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
