import requests
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv

load_dotenv()


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
        """
        Get all assignments for a course
        
        Args:
            course_id: Canvas course ID
            
        Returns:
            List of assignment dictionaries
        """
        assignments = self._make_request(
            f"courses/{course_id}/assignments",
            params={"include[]": ["submission"]}
        )
        
        return [
            {
                "id": assignment["id"],
                "name": assignment["name"],
                "due_at": assignment.get("due_at"),
                "points_possible": assignment.get("points_possible"),
                "submission_types": assignment.get("submission_types", []),
                "submitted": assignment.get("submission", {}).get("submitted_at") is not None,
                "grade": assignment.get("submission", {}).get("grade"),
                "score": assignment.get("submission", {}).get("score")
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
