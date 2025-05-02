from flask import Flask, request, jsonify, send_from_directory, make_response
from werkzeug.security import generate_password_hash, check_password_hash
from pymongo import MongoClient
from bson.objectid import ObjectId
from datetime import datetime
from requests import post, get
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)

client = MongoClient(
    "mongodb+srv://user:user@cluster0.c161u.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
)
db = client["job_portal"]
users_collection = db["users"]
jobs_collection = db["jobs"]
completed_jobs_collection = db["completed_jobs"]


@app.route("/")
def index():
    email = request.cookies.get("email")
    if email:
        user = users_collection.find_one({"email": email})
        if user:
            if user.get("type") == "employee":
                return send_from_directory("assets", "employee.html")
            else:
                return send_from_directory("assets", "worker.html")

    return send_from_directory("assets", "home.html")


@app.route("/<path:filename>")
def serve_assets(filename):
    return send_from_directory("assets", filename)


@app.route("/api/signup", methods=["POST"])
def signup():
    data = request.json
    email = data.get("email")
    if users_collection.find_one({"email": email}):
        return jsonify({"error": "User already exists"}), 400
    user = {
        "name": data.get("name"),
        "email": email,
        "password_hash": generate_password_hash(data.get("password")),
        "phone_no": data.get("phone"),
        "type": data.get("role"),
        "location": data.get("location"),
    }
    users_collection.insert_one(user)
    return jsonify({"message": "User registered successfully"})


@app.route("/api/login", methods=["POST"])
def login():
    data = request.json
    email = data.get("email")
    user = users_collection.find_one({"email": email})
    if not user or not check_password_hash(user["password_hash"], data.get("password")):
        return jsonify({"error": "Invalid credentials"}), 401
    user.pop("password_hash")
    del user["_id"]
    response = make_response(jsonify({"message": "Login successful", "user": user}))
    response.set_cookie("email", email)
    return response


@app.route("/api/set_user_type", methods=["POST"])
def set_user_type():
    data = request.json
    email = data.get("mail")
    user_type = data.get("type")
    result = users_collection.update_one(
        {"email": email}, {"$set": {"type": user_type}}
    )
    if result.matched_count == 0:
        return jsonify({"error": "User not found"}), 404
    return jsonify({"message": "User type updated"})


@app.route("/api/new_job", methods=["POST"])
def new_job():
    data = request.json
    job = {
        "email": data.get("email"),
        "title": data.get("title"),
        "description": data.get("description"),
        "skills": data.get("skills"),
        "location": data.get("location"),
        "daily_wage": data.get("daily_wage"),
        "duration": data.get("duration"),
        "assigned": False,
        "assigned_mail": None,
        "posted_on": datetime.now(),
        "applicants": [],
    }
    job_id = jobs_collection.insert_one(job).inserted_id
    return jsonify({"message": "Job posted successfully", "job_id": str(job_id)})


@app.route("/api/jobs", methods=["GET"])
def get_all_jobs():
    jobs = list(jobs_collection.find({}))
    for job in jobs:
        job["job_id"] = str(job.pop("_id"))
    return jsonify(jobs)


@app.route("/api/jobs/unfilled", methods=["GET"])
def get_unfilled_jobs():
    jobs = list(jobs_collection.find({"assigned": False}))
    jobs = [job for job in jobs if job.get("assigned_mail") is None]
    for job in jobs:
        job["job_id"] = str(job.pop("_id"))
    return jsonify(jobs)


@app.route("/api/jobs/unapplied", methods=["GET"])
def get_unapplied_jobs():
    email = request.args.get("email")
    jobs = list(jobs_collection.find({"applicants": {"$ne": email}}))
    for job in jobs:
        job["job_id"] = str(job.pop("_id"))
        employer = users_collection.find_one({"email": job["email"]}, {"_id": 0, "name": 1})
        job["employer"] = employer["name"] if employer else "Unknown"
    return jsonify(jobs)


@app.route("/api/jobs/filled", methods=["GET"])
def get_filled_jobs():
    jobs = list(jobs_collection.find({"assigned": True}))
    jobs = [job for job in jobs if job["assigned_mail"] is not None]
    for job in jobs:
        job["job_id"] = str(job.pop("_id"))
    return jsonify(jobs)


@app.route("/api/user_jobs", methods=["GET"])
def get_user_jobs():
    email = request.args.get("email")
    jobs = list(jobs_collection.find({"applicants": email}))
    for job in jobs:
        job["job_id"] = str(job.pop("_id"))
    return jsonify(jobs)


@app.route("/api/user_jobs_filled", methods=["GET"])
def get_user_jobs_filled():
    email = request.args.get("email")
    jobs = list(jobs_collection.find({"assigned_mail": email, "assigned": True}))
    for job in jobs:
        job["job_id"] = str(job.pop("_id"))
    return jsonify(jobs)


@app.route("/api/employee_jobs", methods=["GET"])
def get_employee_jobs():
    email = request.args.get("email")
    jobs = list(jobs_collection.find({"email": email}))
    for job in jobs:
        job["job_id"] = str(job.pop("_id"))
    return jsonify(jobs)


@app.route("/api/employee_job_unassigned", methods=["GET"])
def get_employee_job_unassigned():
    email = request.args.get("email")
    results = []
    jobs = list(
        jobs_collection.find({"email": email, "assigned": False, "assigned_mail": None})
    )
    for job in jobs:
        if len(job.get("applicants", [])) == 0:
            continue
        else:
            for applicant in job["applicants"]:
                appl = users_collection.find_one(
                    {"email": applicant}, {"_id": 0, "password_hash": 0}
                )
                result = {
                    "job_id": str(job["_id"]),
                    "title": job["title"],
                    "email": applicant,
                    "name": appl["name"],
                    "location": appl.get(
                        "location", ""
                    ),  # Include applicant's location
                    "assigned": False,
                    "status": "pending",
                }
                results.append(result)
    return jsonify(results)

@app.route("/api/job", methods=["GET"])
def get_job_details():
    job_id = request.args.get("id")
    job = jobs_collection.find_one({"_id": ObjectId(job_id)})

    if not job:
        return jsonify({"error": "Job not found"}), 404

    job["_id"] = str(job["_id"])  # Convert ObjectId to string

    # If the job is assigned, include worker details
    if job.get("assigned"):
        worker = users_collection.find_one({"email": job.get("assigned_mail")})
        if worker:
            job["assigned_phone"] = worker.get("phone_no", "N/A")

    return jsonify(job)


@app.route("/api/delete_job", methods=["POST"])
def delete_job():
    job_id = request.json.get("job_id")
    result = jobs_collection.delete_one({"_id": ObjectId(job_id)})
    if result.deleted_count == 0:
        return jsonify({"error": "Job not found"}), 404
    return jsonify({"message": "Job deleted successfully"})


@app.route("/api/cancel_job", methods=["POST"])
def cancel_job():
    job_id = request.json.get("job_id")
    email = request.json.get("email")
    result = jobs_collection.update_one(
        {"_id": ObjectId(job_id)}, {"$pull": {"applicants": email}}
    )
    if result.matched_count == 0:
        return jsonify({"error": "Job not found"}), 404
    return jsonify({"message": "Job application cancelled"})


@app.route("/api/user", methods=["GET"])
def get_user_info():
    email = request.args.get("email")
    user = users_collection.find_one({"email": email}, {"_id": 0, "password_hash": 0})
    if not user:
        return jsonify({"error": "User not found"}), 404
     # Fetch pics from the pics collection
    pics = list(db.pics.find({"email": email}, {"_id": 0, "pic_url": 1}))
    user["pics"] = [get(pic["pic_url"]).text.strip() for pic in pics]
    return jsonify(user)


@app.route("/api/apply_job", methods=["POST"])
def apply_job():
    data = request.json
    job_id = data.get("job_id")
    email = data.get("email")
    result = jobs_collection.update_one(
        {"_id": ObjectId(job_id), "assigned": False, "assigned_mail": None},
        {"$push": {"applicants": email}},
    )
    if result.matched_count == 0:
        return jsonify({"error": "Job not found or already assigned"}), 404
    return jsonify({"message": "Job applied successfully"})


@app.route("/api/assign_job", methods=["POST"])
def assign_job():
    data = request.json
    job_id = data.get("job_id")
    email = data.get("email")
    result = jobs_collection.update_one(
        {"_id": ObjectId(job_id)}, {"$set": {"assigned": True, "assigned_mail": email}}
    )
    if result.matched_count == 0:
        return jsonify({"error": "Job not found"}), 404
    return jsonify({"message": "Job assigned successfully"})


@app.route("/api/employer_stats", methods=["GET"])
def employer_stats():
    email = request.args.get("email")
    jobs_posted = jobs_collection.count_documents({"email": email})
    jobs_filled = jobs_collection.count_documents({"email": email, "assigned": True})
    return jsonify({"jobs_posted": jobs_posted, "jobs_filled": jobs_filled})


@app.route("/api/jobs_by_location", methods=["GET"])
def get_unassigned_jobs_by_location():
    location = request.args.get("location", "").lower()
    # Find all unassigned jobs with matching location (case-insensitive)
    jobs = list(
        jobs_collection.find(
            {
                "assigned": False,
                "assigned_mail": None,
                "location": {"$regex": location, "$options": "i"},
            }
        )
    )
    for job in jobs:
        job["job_id"] = str(job.pop("_id"))
    return jsonify(jobs)


@app.route("/api/edit_job", methods=["POST"])
def edit_job():
    data = request.json
    job_id = data.get("job_id")
    updated_fields = {
        "title": data.get("title"),
        "location": data.get("location"),
        "duration": data.get("duration"),
        "daily_wage": data.get("daily_wage"),
    }
    jobs_collection.update_one({"_id": ObjectId(job_id)}, {"$set": updated_fields})
    return jsonify({"message": "Job updated successfully"})


@app.route("/api/cancel_job_worker", methods=["POST"])
def cancel_job_worker():
    job_id = request.json.get("job_id")
    email = request.json.get("email")
    reason = request.json.get("reason")
    # You could store the reason in "cancellations" or update the job doc
    jobs_collection.update_one(
        {"_id": ObjectId(job_id)}, {"$pull": {"applicants": email}}
    )
    return jsonify({"message": f"Worker {email} canceled job with reason: {reason}"})


@app.route("/api/upload_worker_job_pic", methods=["POST"])
def upload_worker_job_pic():
    data = request.json
    email = data.get("email")
    pic_bytes = data.get("pic_bytes")

    webiste = "https://envs.sh"
    resp = post(webiste, files={"file": pic_bytes})

    db.pics.insert_one({"email": email, "pic_url": resp.text.strip()})
    return jsonify({"message": "Image uploaded successfully"})


@app.route("/api/get_user_photos", methods=["GET"])
def get_worker_photos():
    email = request.args.get("email")
    pics = list(db.pics.find({"email": email}))
    for pic in pics:
        pic["_id"] = str(pic["_id"])
        pic["pic_url"] = get(pic["pic_url"]).text.strip()

    return jsonify(pics)

import random
def get_rand_skills():
    skills = ["Elect", "Plumb", "Carp", "Mason", "Paint", "Clean", "Cook"]
    return random.sample(skills, 2)

...
@app.route("/api/nearby_workers", methods=["GET"])
def get_nearby_workers():
    email = request.args.get("email")
    user = users_collection.find_one({"email": email})
    loc = user.get("location")
    users = list(users_collection.find({"location": loc, "type": "worker"}))
    for user in users:
        user.pop("password_hash")
        user.pop("_id")
        user["reviews"] = [] if not user.get("reviews") else user["reviews"]
        # Remove automatic assignment of skills
        # user["skills"] = get_rand_skills() if not user.get("skills") else user["skills"]
        users_collection.update_one({"email": user["email"]}, {"$set": user}) 

        pics = list(db.pics.find({"email": user["email"]}))
        pics_urls = []
        for pic in pics:
            pics_urls.append(get(pic["pic_url"]).text.strip())
        user["pics"] = pics_urls

        # Include additional fields
        user["name"] = user.get("name")
        user["phone_no"] = user.get("phone_no")
        user["skills"] = user.get("skills", [])
        user["experience"] = user.get("experience", "")
        user["availability"] = user.get("availability", "")

    return jsonify(users)

@app.route("/api/update_skills", methods=["POST"])
def update_skills():
    data = request.json
    email = data.get("email")
    skills = data.get("skills")
    result = users_collection.update_one({"email": email}, {"$set": {"skills": skills}})
    if result.matched_count == 0:
        return jsonify({"error": "User not found"}), 404
    return jsonify({"message": "Skills updated successfully"})

@app.route("/api/update_experience", methods=["POST"])
def update_experience():
    data = request.json
    email = data.get("email")
    experience = data.get("experience")
    result = users_collection.update_one({"email": email}, {"$set": {"experience": experience}})
    if result.matched_count == 0:
        return jsonify({"error": "User not found"}), 404
    return jsonify({"message": "Experience updated successfully"})

@app.route("/api/update_availability", methods=["POST"])
def update_availability():
    data = request.json
    email = data.get("email")
    availability = data.get("availability")
    result = users_collection.update_one({"email": email}, {"$set": {"availability": availability}})
    if result.matched_count == 0:
        return jsonify({"error": "User not found"}), 404
    return jsonify({"message": "Availability updated successfully"})

@app.route("/api/mark_job_completed", methods=["POST"])
def mark_job_completed():
    data = request.json
    email = data.get("email")
    job_id = data.get("job_id")

    # Remove the job from the user's applications
    result = jobs_collection.update_one(
        {"_id": ObjectId(job_id), "applicants": email},
        {"$pull": {"applicants": email}}
    )

    if result.matched_count == 0:
        return jsonify({"error": "Job not found or not assigned to this user"}), 404

    # Add the job to the "completed_jobs" collection
    completed_jobs_collection.insert_one({
        "job_id": job_id,
        "email": email,
        "completed_on": datetime.utcnow()
    })

    return jsonify({"message": "Job marked as completed"})

@app.route("/api/completed_jobs_count", methods=["GET"])
def get_completed_jobs_count():
    email = request.args.get("email")
    if not email:
        return jsonify({"error": "Email is required"}), 400

    # Count the number of completed jobs for the worker
    completed_jobs_count = completed_jobs_collection.count_documents({"email": email})

    return jsonify({"completed_jobs_count": completed_jobs_count})

@app.route("/api/update_password", methods=["POST"])
def update_password():
    data = request.json
    email = data.get("email")
    current_password = data.get("current_password")
    new_password = data.get("new_password")

    # Find the user in the database
    user = users_collection.find_one({"email": email})
    if not user:
        return jsonify({"error": "User not found"}), 404

    # Verify the current password
    if not check_password_hash(user["password_hash"], current_password):
        return jsonify({"error": "Current password is incorrect"}), 400

    # Update the password
    new_password_hash = generate_password_hash(new_password)
    users_collection.update_one({"email": email}, {"$set": {"password_hash": new_password_hash}})

    return jsonify({"message": "Password updated successfully"})

@app.route("/api/update_location", methods=["POST"])
def update_location():
    data = request.json
    email = data.get("email")
    new_location = data.get("location")

    if not email or not new_location:
        return jsonify({"error": "Email and location are required"}), 400

    result = users_collection.update_one(
        {"email": email},
        {"$set": {"location": new_location}}
    )

    if result.matched_count == 0:
        return jsonify({"error": "User not found"}), 404

    return jsonify({"message": "Location updated successfully"})

@app.route("/api/review_worker", methods=["POST"])
def review_worker():
    data = request.json
    email = data.get("email")
    review = data.get("review")
    user = users_collection.find_one({"email": email})
    if not user.get("reviews"):
        user["reviews"] = []
    user["reviews"].append(review)
    users_collection.update_one({"email": email}, {"$set": user})
    return jsonify({"message": "Review added successfully"})

if __name__ == "__main__":
    app.run(debug=True)