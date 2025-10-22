# debug_specific_quiz.py
from src.canvas.client import CanvasClient
import json

client = CanvasClient()
course_id = "80546"  # CS 555
assignment_id = "615240"  # Quiz 02

print("=== DIRECT ASSIGNMENT FETCH ===")
try:
    assignment = client._make_request(f"courses/{course_id}/assignments/{assignment_id}")
    print(json.dumps(assignment, indent=2))
except Exception as e:
    print(f"Error: {e}")

print("\n=== ASSIGNMENT WITH INCLUDE PARAMS ===")
try:
    assignments = client._make_request(
        f"courses/{course_id}/assignments",
        params={
            "include[]": ["submission", "score_statistics"],
            "per_page": 100
        }
    )
    print(f"Total assignments returned: {len(assignments)}")
    quiz_assignments = [a for a in assignments if "615240" in str(a.get("id"))]
    if quiz_assignments:
        print("Found Quiz 02!")
        print(json.dumps(quiz_assignments[0], indent=2))
    else:
        print("Quiz 02 not in the list")
        print("Assignment IDs returned:", [a["id"] for a in assignments[:15]])
except Exception as e:
    print(f"Error: {e}")
