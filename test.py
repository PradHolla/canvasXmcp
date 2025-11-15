import requests
from dotenv import load_dotenv
import os

load_dotenv()

CANVAS_BASE_URL = os.getenv("CANVAS_URL")
API_TOKEN = os.getenv("CANVAS_TOKEN")

HEADERS = {
    "Authorization": f"Bearer {API_TOKEN}"
}

course_id = "82456"
assignment_id = "628956"

url = f"{CANVAS_BASE_URL}/api/v1/courses/{course_id}/assignments/{assignment_id}"
params = {"include[]": ["submission", "can_submit"]}

response = requests.get(url, headers=HEADERS, params=params)
data = response.json()

print(f"Can submit: {data.get('can_submit')}")
print(f"Submission types: {data.get('submission_types')}")
print(f"Current submission: {data.get('submission')}")