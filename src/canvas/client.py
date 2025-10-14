import requests
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv
from datetime import datetime, timezone

load_dotenv()


def format_date(date_str: str) -> str:
    """
    Format ISO date string to readable format
    
    Args:
        date_str: ISO format date string
        
    Returns:
        Formatted date like "October 13, 2025 at 3:59 PM"
    """
    if not date_str:
        return "No date"
    
    try:
        dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        return dt.strftime("%B %d, %Y at %I:%M %p")
    except:
        return date_str
    
class CanvasClient:
    """Client for interacting with Canvas LMS API"""
    
    def __init__(self, base_url: str = None, access_token: str = None):
        """
        Initialize Canvas client
        
        Args:
            base_url: Canvas instance URL
            access_token: Canvas API access token
        """
        self.base_url = (base_url or os.getenv("CANVAS_URL")).rstrip('/')
        self.access_token = access_token or os.getenv("CANVAS_TOKEN")
        
        if not self.base_url or not self.access_token:
            raise ValueError("Canvas URL and access token are required")
        
        self.headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }
        
        self.api_base = f"{self.base_url}/api/v1"
    
    def _make_request(
        self, 
        endpoint: str, 
        method: str = "GET",
        params: Optional[Dict] = None,
        data: Optional[Dict] = None
    ) -> Any:
        """
        Make HTTP request to Canvas API
        
        Args:
            endpoint: API endpoint (without /api/v1 prefix)
            method: HTTP method
            params: Query parameters
            data: Request body
            
        Returns:
            JSON response
        """
        url = f"{self.api_base}/{endpoint.lstrip('/')}"
        
        try:
            response = requests.request(
                method=method,
                url=url,
                headers=self.headers,
                params=params,
                json=data,
                timeout=30
            )
            response.raise_for_status()
            return response.json()
        
        except requests.exceptions.HTTPError as e:
            if response.status_code == 401:
                raise Exception("Unauthorized: Check your Canvas access token")
            elif response.status_code == 403:
                raise Exception("Forbidden: Insufficient permissions")
            elif response.status_code == 404:
                raise Exception(f"Not found: {endpoint}")
            else:
                raise Exception(f"HTTP {response.status_code}: {str(e)}")
        
        except requests.exceptions.RequestException as e:
            raise Exception(f"Request failed: {str(e)}")
    
    def get_courses(self) -> List[Dict[str, Any]]:
        """
        Get all enrolled courses for current user
        
        Returns:
            List of course dictionaries with id, name, course_code, etc.
        """
        courses = self._make_request(
            "courses",
            params={
                "enrollment_state": "active",
                "include[]": ["term", "total_scores"]
            }
        )
        
        # Return simplified course info
        return [
            {
                "id": course["id"],
                "name": course["name"],
                "course_code": course.get("course_code", ""),
                "enrollment_term": course.get("term", {}).get("name", ""),
                "current_grade": course.get("enrollments", [{}])[0].get("computed_current_grade")
            }
            for course in courses
        ]
    
    def get_assignments(self, course_id: str) -> List[Dict[str, Any]]:
        """Get all assignments for a course"""
        assignments = self._make_request(
            f"courses/{course_id}/assignments"
        )
        
        return [
            {
                "id": assignment["id"],
                "name": assignment["name"],
                "due_at": format_date(assignment.get("due_at")),
                "due_at_raw": assignment.get("due_at"),  # Keep raw for calculations
                "points_possible": assignment.get("points_possible"),
                "submission_types": assignment.get("submission_types", []),
                "submitted": assignment.get("has_submitted_submissions", False),
                "grade": assignment.get("grade"),
                "score": assignment.get("score")
            }
            for assignment in assignments
        ]
    
    def get_upcoming_assignments(self, days: int = 7) -> List[Dict[str, Any]]:
        """
        Get assignments due in the next N days across all courses
        
        Args:
            days: Number of days to look ahead
            
        Returns:
            List of upcoming assignments with course info
        """
        courses = self.get_courses()
        upcoming = []
        
        # Make timezone-aware datetimes (UTC)
        from datetime import timezone
        now = datetime.now(timezone.utc)
        future = now + timedelta(days=days)
        
        for course in courses:
            try:
                assignments = self.get_assignments(course["id"])
                
                for assignment in assignments:
                    if assignment["due_at"]:
                        # Parse ISO datetime (Canvas returns UTC with Z)
                        due_date = datetime.fromisoformat(
                            assignment["due_at"].replace('Z', '+00:00')
                        )
                        
                        # Check if due within time window
                        if now <= due_date <= future:
                            upcoming.append({
                                **assignment,
                                "course_name": course["name"],
                                "course_code": course["course_code"]
                            })
            except Exception as e:
                print(f"Error fetching assignments for {course['name']}: {e}")
                continue
        
        # Sort by due date
        upcoming.sort(key=lambda x: x["due_at"])
        return upcoming

    
    def get_grades(self, course_id: str) -> Dict[str, Any]:
        """
        Get grade information for a course
        
        Args:
            course_id: Canvas course ID
            
        Returns:
            Grade information including current grade and scores
        """
        enrollments = self._make_request(
            f"courses/{course_id}/enrollments",
            params={"user_id": "self"}
        )
        
        if not enrollments:
            return {"error": "No enrollment found"}
        
        enrollment = enrollments[0]
        grades = enrollment.get("grades", {})
        
        return {
            "current_score": grades.get("current_score"),
            "current_grade": grades.get("current_grade"),
            "final_score": grades.get("final_score"),
            "final_grade": grades.get("final_grade"),
            "unposted_current_score": grades.get("unposted_current_score"),
            "unposted_current_grade": grades.get("unposted_current_grade")
        }
    
    def get_announcements(self, days: int = 7) -> List[Dict[str, Any]]:
        """
        Get recent announcements from all courses
        
        Args:
            days: Number of days to look back
            
        Returns:
            List of announcements
        """
        courses = self.get_courses()
        
        # Build context codes for all courses
        context_codes = [f"course_{course['id']}" for course in courses]
        
        # Calculate start date
        start_date = (datetime.now() - timedelta(days=days)).isoformat()
        
        # Build query parameters
        params = {
            "context_codes[]": context_codes,
            "start_date": start_date
        }
        
        announcements = self._make_request("announcements", params=params)
        
        return [
            {
                "id": ann["id"],
                "title": ann["title"],
                "message": ann["message"],
                "posted_at": ann["posted_at"],
                "author": ann.get("author", {}).get("display_name", "Unknown"),
                "course_id": ann.get("context_code", "").replace("course_", "")
            }
            for ann in announcements
        ]

    def get_discussions(self, course_id: str) -> List[Dict[str, Any]]:
        """
        Get discussion topics for a course
        
        Args:
            course_id: Canvas course ID
            
        Returns:
            List of discussion topics
        """
        import re
        
        def strip_html(text: str) -> str:
            """Remove HTML tags and clean up text"""
            if not text:
                return ""
            # Remove HTML tags
            text = re.sub(r'<[^>]+>', '', text)
            # Remove extra whitespace
            text = ' '.join(text.split())
            # Limit length
            return text[:300] + "..." if len(text) > 300 else text
        
        try:
            discussions = self._make_request(
                f"courses/{course_id}/discussion_topics"
            )
            
            if not discussions:
                return [{"message": "No discussions found for this course"}]
            
            return [
                {
                    "id": disc["id"],
                    "title": disc["title"],
                    "message": strip_html(disc.get("message", "")),
                    "posted_at": disc.get("posted_at"),
                    "author": disc.get("author", {}).get("display_name", "Unknown"),
                    "unread_count": disc.get("unread_count", 0),
                    "reply_count": disc.get("discussion_subentry_count", 0)
                }
                for disc in discussions
            ]
        except Exception as e:
            return [{"error": f"Could not fetch discussions: {str(e)}"}]

    def get_course_files(self, course_id: str) -> List[Dict[str, Any]]:
        """
        Get files for a course
        
        Args:
            course_id: Canvas course ID
            
        Returns:
            List of files
        """
        files = self._make_request(
            f"courses/{course_id}/files"
        )
        
        return [
            {
                "id": file["id"],
                "display_name": file.get("display_name", ""),
                "filename": file.get("filename", ""),
                "size": file.get("size", 0),
                "content_type": file.get("content-type", ""),
                "url": file.get("url", ""),
                "created_at": file.get("created_at"),
                "updated_at": file.get("updated_at"),
                "folder_id": file.get("folder_id")
            }
            for file in files
        ]

    def get_calendar_events(self, days_ahead: int = 14) -> List[Dict[str, Any]]:
        """
        Get upcoming calendar events
        
        Args:
            days_ahead: Number of days to look ahead
            
        Returns:
            List of calendar events
        """
        from datetime import timezone
        
        start_date = datetime.now(timezone.utc).isoformat()
        end_date = (datetime.now(timezone.utc) + timedelta(days=days_ahead)).isoformat()
        
        # Use different endpoint that doesn't require special permissions
        try:
            events = self._make_request(
                "calendar_events",
                params={
                    "start_date": start_date,
                    "end_date": end_date,
                    "type": "assignment"  # Just get assignment events
                }
            )
        except Exception as e:
            # Fallback: get upcoming assignments instead
            print(f"Calendar API failed, using assignments: {e}")
            return self.get_upcoming_assignments(days_ahead)
        
        return [
            {
                "id": event["id"],
                "title": event["title"],
                "description": event.get("description", ""),
                "start_at": event.get("start_at"),
                "end_at": event.get("end_at"),
                "location_name": event.get("location_name", ""),
                "context_name": event.get("context_name", ""),
                "type": event.get("type", "event")
            }
            for event in events
        ]

    def get_modules(self, course_id: str) -> List[Dict[str, Any]]:
        """
        Get modules (units/weeks) for a course, or files if no modules exist
        
        Args:
            course_id: Canvas course ID
            
        Returns:
            List of modules with items, or files if no modules
        """
        try:
            modules = self._make_request(
                f"courses/{course_id}/modules",
                params={"include[]": ["items"]}
            )
            
            # If no modules found, return files instead
            if not modules or len(modules) == 0:
                return self._get_files_as_modules(course_id)
            
            return [
                {
                    "id": module["id"],
                    "name": module["name"],
                    "position": module.get("position", 0),
                    "unlock_at": module.get("unlock_at"),
                    "state": module.get("state", ""),
                    "published": module.get("published", False),
                    "items_count": module.get("items_count", 0),
                    "items": [
                        {
                            "id": item["id"],
                            "title": item["title"],
                            "type": item["type"],
                            "indent": item.get("indent", 0)
                        }
                        for item in module.get("items", [])[:10]  # First 10 items
                    ]
                }
                for module in modules
            ]
        except Exception as e:
            # On error, try returning files as fallback
            return self._get_files_as_modules(course_id)


    def _get_files_as_modules(self, course_id: str) -> List[Dict[str, Any]]:
        """
        Helper: Return course files formatted as a module structure
        
        Args:
            course_id: Canvas course ID
            
        Returns:
            Files formatted as a single "Files" module
        """
        try:
            files = self.get_course_files(course_id)
            
            if not files:
                return [{"message": "No modules or files found for this course"}]
            
            # Format files as module items
            file_items = [
                {
                    "id": file["id"],
                    "title": file["display_name"],
                    "type": "File",
                    "size": file["size"],
                    "url": file.get("url", "")
                }
                for file in files[:20]  # Limit to first 20 files
            ]
            
            return [
                {
                    "id": "files",
                    "name": "Course Files",
                    "position": 1,
                    "state": "active",
                    "published": True,
                    "items_count": len(file_items),
                    "items": file_items,
                    "is_files_fallback": True
                }
            ]
        except Exception as e:
            return [{"error": f"Could not fetch modules or files: {str(e)}"}]



    def get_quizzes(self, course_id: str) -> List[Dict[str, Any]]:
        """
        Get quizzes for a course
        
        Args:
            course_id: Canvas course ID
            
        Returns:
            List of quizzes with details
        """
        try:
            quizzes = self._make_request(
                f"courses/{course_id}/quizzes"
            )
            
            return [
                {
                    "id": quiz["id"],
                    "title": quiz["title"],
                    "description": quiz.get("description", "")[:200],  # Truncate description
                    "quiz_type": quiz.get("quiz_type", ""),
                    "time_limit": quiz.get("time_limit"),
                    "question_count": quiz.get("question_count", 0),
                    "points_possible": quiz.get("points_possible"),
                    "due_at": quiz.get("due_at"),
                    "lock_at": quiz.get("lock_at"),
                    "published": quiz.get("published", False),
                    "allowed_attempts": quiz.get("allowed_attempts", 1)
                }
                for quiz in quizzes
            ]
        except Exception as e:
            return [{"error": f"Could not fetch quizzes: {str(e)}"}]


    def get_assignment_submissions(self, course_id: str, assignment_id: str) -> Dict[str, Any]:
        """
        Get submission details for a specific assignment
        
        Args:
            course_id: Canvas course ID
            assignment_id: Assignment ID
            
        Returns:
            Submission details
        """
        try:
            submission = self._make_request(
                f"courses/{course_id}/assignments/{assignment_id}/submissions/self"
            )
            
            return {
                "id": submission.get("id"),
                "assignment_id": submission.get("assignment_id"),
                "submitted_at": submission.get("submitted_at"),
                "score": submission.get("score"),
                "grade": submission.get("grade"),
                "attempt": submission.get("attempt"),
                "workflow_state": submission.get("workflow_state", ""),
                "late": submission.get("late", False),
                "missing": submission.get("missing", False),
                "excused": submission.get("excused", False),
                "submission_comments": [
                    {
                        "comment": comment.get("comment", ""),
                        "author": comment.get("author_name", "Unknown"),
                        "created_at": comment.get("created_at")
                    }
                    for comment in submission.get("submission_comments", [])
                ]
            }
        except Exception as e:
            return {"error": f"Could not fetch submission: {str(e)}"}
