# src/canvas/client.py

import os
import requests
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import logging
import re
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


def format_date(date_str: str) -> str:
    """
    Format ISO date string to readable format

    Args:
        date_str: ISO format date string

    Returns:
        Formatted date like "October 23, 2025 at 3:59 PM"
    """
    if not date_str:
        return "No date"

    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        # Convert to local time
        local_dt = dt.astimezone()
        return local_dt.strftime("%B %d, %Y at %I:%M %p")
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
        self.base_url = (base_url or os.getenv("CANVAS_URL")).rstrip("/")
        self.access_token = access_token or os.getenv("CANVAS_TOKEN")
        self._cache = {}
        self._cache_ttl = 300  # 5 minutes

        if not self.base_url or not self.access_token:
            raise ValueError("Canvas URL and access token are required")

        self.headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

        self.api_base = f"{self.base_url}/api/v1"

    def _make_request(
        self,
        endpoint: str,
        method: str = "GET",
        params: Optional[Dict] = None,
        data: Optional[Dict] = None,
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
                timeout=30,
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

    def _get_cached(self, key: str) -> Optional[Any]:
        """Get cached response if still valid"""
        if key in self._cache:
            data, timestamp = self._cache[key]
            if (datetime.now() - timestamp).seconds < self._cache_ttl:
                return data
        return None

    def _set_cache(self, key: str, data: Any):
        """Cache response with timestamp"""
        self._cache[key] = (data, datetime.now())

    def get_courses(self) -> List[Dict[str, Any]]:
        """
        Get all enrolled courses for current user (cached)

        Returns:
            List of course dictionaries with id, name, course_code, INSTRUCTOR, etc.
        """
        cache_key = "courses"
        cached = self._get_cached(cache_key)
        if cached:
            return cached

        courses = self._make_request(
            "courses",
            params={
                "enrollment_state": "active",
                # UPDATE 1: Add "teachers" to the include list
                "include[]": ["term", "total_scores", "teachers"],
            },
        )

        result = []
        for course in courses:
            teachers = course.get("teachers", [])
            instructor_name = ", ".join([t["display_name"] for t in teachers]) if teachers else "Unknown Instructor"

            result.append({
                "id": course["id"],
                "name": course["name"],
                "course_code": course.get("course_code", ""),
                "enrollment_term": course.get("term", {}).get("name", ""),
                "current_grade": course.get("enrollments", [{}])[0].get("computed_current_grade"),
                "instructor": instructor_name
            })

        self._set_cache(cache_key, result)
        return result

    def get_assignments(self, course_id: str) -> List[Dict[str, Any]]:
        """
        Get all assignments for a course (with caching)

        Args:
            course_id: Canvas course ID

        Returns:
            List of assignments with submission data
        """
        cache_key = f"assignments_{course_id}"
        cached = self._get_cached(cache_key)
        if cached:
            return cached

        assignments = self._make_request(
            f"courses/{course_id}/assignments",
            params={"include[]": ["submission", "score_statistics"], "per_page": 100},
        )

        result = []
        for assignment in assignments:
            # Check if it's a quiz
            is_quiz = (
                "online_quiz" in assignment.get("submission_types", [])
                or assignment.get("is_quiz_lti_assignment", False)
                or "quiz" in assignment.get("name", "").lower()
            )

            result.append(
                {
                    "id": assignment["id"],
                    "name": assignment["name"],
                    "due_at": format_date(assignment.get("due_at")),
                    "due_at_raw": assignment.get("due_at"),
                    "points_possible": assignment.get("points_possible"),
                    "submission_types": assignment.get("submission_types", []),
                    "submitted": assignment.get("has_submitted_submissions", False),
                    "grade": assignment.get("submission", {}).get("grade"),
                    "score": assignment.get("submission", {}).get("score"),
                    "workflow_state": assignment.get("submission", {}).get(
                        "workflow_state"
                    ),
                    "is_quiz": is_quiz,
                }
            )

        self._set_cache(cache_key, result)
        return result

    def get_upcoming_assignments(
        self,
        days: int = 7,
        include_past_week: bool = True,
        from_date: datetime = None,
        to_date: datetime = None,
    ) -> List[Dict[str, Any]]:
        """
        Get assignments due in a date range with smart defaults.

        Args:
            days: Number of days to look ahead (default: 7)
            include_past_week: Include overdue unsubmitted assignments from past 7 days (default: True)
            from_date: Optional explicit start date (overrides days)
            to_date: Optional explicit end date (overrides days)

        Returns:
            List of upcoming/overdue assignments with course info
        """
        courses = self.get_courses()

        # Use local timezone-aware datetime
        now = datetime.now().astimezone()

        # Determine date range
        if from_date and to_date:
            # Explicit date range provided (for "this month", "this week" queries)
            start_date = (
                from_date.astimezone()
                if from_date.tzinfo
                else from_date.replace(tzinfo=now.tzinfo)
            )
            end_date = (
                to_date.astimezone()
                if to_date.tzinfo
                else to_date.replace(tzinfo=now.tzinfo)
            )
        else:
            # Use days parameter
            # Include past week if flag is set (catches recent overdue items)
            start_date = now - timedelta(days=7) if include_past_week else now
            end_date = now + timedelta(days=days)

        upcoming = []

        for course in courses:
            course_id = str(course["id"])

            try:
                assignments = self.get_assignments(course_id)

                for assignment in assignments:
                    due_at_raw = assignment.get("due_at_raw")
                    if not due_at_raw:
                        continue

                    try:
                        # Parse Canvas UTC timestamp and convert to local time
                        due_date = datetime.fromisoformat(
                            due_at_raw.replace("Z", "+00:00")
                        )
                        due_date_local = due_date.astimezone()

                        # Check if assignment is in date range
                        is_in_range = start_date <= due_date_local <= end_date

                        # Also include if it's overdue and unsubmitted (even if outside explicit range)
                        is_overdue_unsubmitted = (
                            due_date_local < now
                            and not assignment.get("has_submitted_submissions", False)
                            and include_past_week
                        )

                        if is_in_range or is_overdue_unsubmitted:
                            upcoming.append(
                                {
                                    **assignment,
                                    "course_name": course["name"],
                                    "course_code": course.get("course_code", ""),
                                    "due_date_local": due_date_local.isoformat(),
                                    "is_overdue": due_date_local < now,
                                    "days_until_due": (due_date_local - now).days,
                                }
                            )

                    except Exception as e:
                        # Log but continue processing other assignments
                        logger.debug(
                            f"Error parsing due date for {assignment.get('name', 'unknown')}: {e}"
                        )
                        continue

            except Exception as e:
                logger.warning(
                    f"Error fetching assignments for course {course.get('name', 'unknown')}: {e}"
                )
                continue

        if not upcoming:
            # Provide contextual message based on date range
            if from_date and to_date:
                return [
                    {
                        "message": f"No assignments due between {from_date.strftime('%b %d')} and {to_date.strftime('%b %d, %Y')}"
                    }
                ]
            else:
                return [{"message": f"No assignments due in the next {days} days"}]

        # Sort by: overdue first (if any), then by due date
        upcoming.sort(
            key=lambda x: (not x.get("is_overdue", False), x.get("due_at_raw", ""))
        )

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
            f"courses/{course_id}/enrollments", params={"user_id": "self"}
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
            "unposted_current_grade": grades.get("unposted_current_grade"),
        }

    def get_all_grades(self) -> List[Dict[str, Any]]:
        """
        Get grades for ALL enrolled courses in one call

        Returns:
            List of course grades
        """
        try:
            courses = self.get_courses()

            all_grades = []
            for course in courses:
                course_id = str(course["id"])

                try:
                    grades = self.get_grades(course_id)
                    all_grades.append(
                        {
                            "course_id": course_id,
                            "course_name": course["name"],
                            "course_code": course.get("course_code", ""),
                            "grades": grades,
                        }
                    )
                except:
                    continue

            return all_grades

        except Exception as e:
            return [{"error": f"Could not fetch grades: {str(e)}"}]

    def get_course_summary(self, course_id: str) -> Dict[str, Any]:
        """
        Get comprehensive course info in one call

        Args:
            course_id: Canvas course ID

        Returns:
            Course summary with grades, upcoming assignments, recent announcements
        """
        try:
            courses = self.get_courses()
            course = next((c for c in courses if str(c["id"]) == str(course_id)), None)

            if not course:
                return {"error": "Course not found"}

            summary = {
                "course_name": course["name"],
                "course_code": course.get("course_code", ""),
                "grades": self.get_grades(course_id),
                "upcoming_assignments": [],
                "recent_announcements": [],
            }

            # Get upcoming assignments (due in next 7 days)
            try:
                assignments = self.get_assignments(course_id)
                now = datetime.now()
                week_from_now = now + timedelta(days=7)

                for assignment in assignments:
                    due_at_raw = assignment.get("due_at_raw")
                    if due_at_raw:
                        try:
                            due_date = datetime.fromisoformat(
                                due_at_raw.replace("Z", "+00:00")
                            )
                            due_date_local = due_date.astimezone()
                            if now <= due_date_local <= week_from_now:
                                summary["upcoming_assignments"].append(assignment)
                        except:
                            continue
            except:
                pass

            # Get recent announcements
            try:
                announcements = self.get_announcements()
                course_announcements = [
                    a for a in announcements if a.get("course_id") == str(course_id)
                ]
                summary["recent_announcements"] = course_announcements[:3]
            except:
                pass

            return summary

        except Exception as e:
            return {"error": f"Could not fetch course summary: {str(e)}"}

    def get_course_id_by_name(self, course_name: str) -> Optional[str]:
        """
        Find course ID by course name or code

        Args:
            course_name: Course name or code (e.g., "CS 555" or "Machine Learning")

        Returns:
            Course ID as string, or None if not found
        """
        try:
            courses = self.get_courses()
            search_term = course_name.lower().strip()

            for course in courses:
                if search_term in course.get("name", "").lower():
                    return str(course["id"])
                if search_term in course.get("course_code", "").lower():
                    return str(course["id"])

            return None
        except:
            return None

    def get_announcements(self, days: int = 7) -> List[Dict[str, Any]]:
        """
        Get recent announcements from all courses

        Args:
            days: Number of days to look back

        Returns:
            List of announcements
        """
        courses = self.get_courses()
        context_codes = [f"course_{course['id']}" for course in courses]
        start_date = (datetime.now() - timedelta(days=days)).isoformat()

        announcements = self._make_request(
            "announcements",
            params={"context_codes[]": context_codes, "start_date": start_date},
        )

        return [
            {
                "id": ann["id"],
                "title": ann["title"],
                "message": ann["message"][:500],  # Limit message length
                "posted_at": format_date(ann["posted_at"]),
                "author": ann.get("author", {}).get("display_name", "Unknown"),
                "course_id": ann.get("context_code", "").replace("course_", ""),
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

        def strip_html(text: str) -> str:
            """Remove HTML tags and clean up text"""
            if not text:
                return ""
            text = re.sub(r"<[^>]+>", "", text)
            text = " ".join(text.split())
            return text[:300] + "..." if len(text) > 300 else text

        try:
            discussions = self._make_request(f"courses/{course_id}/discussion_topics")

            if not discussions:
                return [{"message": "No discussions found for this course"}]

            return [
                {
                    "id": disc["id"],
                    "title": disc["title"],
                    "message": strip_html(disc.get("message", "")),
                    "posted_at": format_date(disc.get("posted_at")),
                    "author": disc.get("author", {}).get("display_name", "Unknown"),
                    "unread_count": disc.get("unread_count", 0),
                    "reply_count": disc.get("discussion_subentry_count", 0),
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
        files = self._make_request(f"courses/{course_id}/files")

        return [
            {
                "id": file["id"],
                "display_name": file.get("display_name", ""),
                "filename": file.get("filename", ""),
                "size": file.get("size", 0),
                "content_type": file.get("content-type", ""),
                "url": file.get("url", ""),
                "created_at": format_date(file.get("created_at")),
                "updated_at": format_date(file.get("updated_at")),
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
        start_date = datetime.now().isoformat()
        end_date = (datetime.now() + timedelta(days=days_ahead)).isoformat()

        try:
            events = self._make_request(
                "calendar_events",
                params={
                    "start_date": start_date,
                    "end_date": end_date,
                    "type": "assignment",
                },
            )

            return [
                {
                    "id": event["id"],
                    "title": event["title"],
                    "description": event.get("description", "")[:200],
                    "start_at": format_date(event.get("start_at")),
                    "end_at": format_date(event.get("end_at")),
                    "location_name": event.get("location_name", ""),
                    "context_name": event.get("context_name", ""),
                }
                for event in events
            ]
        except:
            # Fallback to upcoming assignments
            return self.get_upcoming_assignments(days_ahead)

    def get_modules(self, course_id: str) -> List[Dict[str, Any]]:
        """
        Get modules for a course, or files if no modules exist

        Args:
            course_id: Canvas course ID

        Returns:
            List of modules with items
        """
        try:
            modules = self._make_request(
                f"courses/{course_id}/modules", params={"include[]": ["items"]}
            )

            if not modules:
                return self._get_files_as_modules(course_id)

            return [
                {
                    "id": module["id"],
                    "name": module["name"],
                    "position": module.get("position", 0),
                    "items_count": module.get("items_count", 0),
                    "items": [
                        {"title": item["title"], "type": item["type"]}
                        for item in module.get("items", [])[:10]
                    ],
                }
                for module in modules
            ]
        except:
            return self._get_files_as_modules(course_id)

    def _get_files_as_modules(self, course_id: str) -> List[Dict[str, Any]]:
        """Return course files formatted as a module"""
        try:
            files = self.get_course_files(course_id)

            if not files:
                return [{"message": "No modules or files found"}]

            file_items = [
                {"title": file["display_name"], "type": "File", "size": file["size"]}
                for file in files[:20]
            ]

            return [
                {
                    "name": "Course Files",
                    "items_count": len(file_items),
                    "items": file_items,
                }
            ]
        except Exception as e:
            return [{"error": f"Could not fetch files: {str(e)}"}]

    def get_quizzes(self, course_id: str) -> List[Dict[str, Any]]:
        """
        Get quizzes with grades (works for native and LTI quizzes)

        Args:
            course_id: Canvas course ID

        Returns:
            List of quizzes with submission data
        """
        try:
            assignments = self.get_assignments(course_id)
            quizzes = [a for a in assignments if a.get("is_quiz", False)]

            if not quizzes:
                return [{"message": "No quizzes found for this course"}]

            return quizzes
        except Exception as e:
            return [{"error": f"Could not fetch quizzes: {str(e)}"}]

    def get_quiz_submissions(self, course_id: str) -> List[Dict[str, Any]]:
        """
        Get quiz submissions with grades

        Args:
            course_id: Canvas course ID

        Returns:
            List of quiz submissions
        """
        return self.get_quizzes(course_id)

    def submit_assignment(
        self, course_id: str, assignment_id: str, file_path: str, comment: str = ""
    ) -> Dict[str, Any]:
        """
        Submit a file to a Canvas assignment (3-step process)

        Args:
            course_id: Canvas course ID
            assignment_id: Assignment ID
            file_path: Full path to file on local filesystem
            comment: Optional submission comment

        Returns:
            Submission confirmation with details
        """
        import os

        try:
            # Validate file exists
            if not os.path.exists(file_path):
                return {"error": f"File not found: {file_path}"}

            if not os.path.isfile(file_path):
                return {"error": f"Path is not a file: {file_path}"}

            file_name = os.path.basename(file_path)
            file_size = os.path.getsize(file_path)

            logger.info(
                f"Starting submission: {file_name} ({file_size} bytes) to assignment {assignment_id}"
            )

            # Step 1: Request upload URL
            upload_url_endpoint = f"courses/{course_id}/assignments/{assignment_id}/submissions/self/files"

            upload_request = {
                "name": file_name,
                "size": file_size,
                "content_type": "application/octet-stream",
            }

            upload_data = self._make_request(
                upload_url_endpoint, method="POST", data=upload_request
            )

            upload_url = upload_data["upload_url"]
            upload_params = upload_data["upload_params"]

            logger.info(f"Got upload URL, uploading file...")

            # Step 2: Upload file to Canvas storage
            with open(file_path, "rb") as f:
                files = {"file": (file_name, f, "application/octet-stream")}

                # Use requests directly for file upload (not JSON)
                upload_response = requests.post(
                    upload_url, data=upload_params, files=files, timeout=60
                )
                upload_response.raise_for_status()
                uploaded_file = upload_response.json()
                file_id = uploaded_file["id"]

            logger.info(f"File uploaded successfully, file_id: {file_id}")

            # Step 3: Create submission with uploaded file
            submission_endpoint = (
                f"courses/{course_id}/assignments/{assignment_id}/submissions"
            )

            submission_data = {
                "submission": {
                    "submission_type": "online_upload",
                    "file_ids": [file_id],
                }
            }

            if comment:
                submission_data["comment"] = {"text_comment": comment}

            submission = self._make_request(
                submission_endpoint, method="POST", data=submission_data
            )

            logger.info(f"Submission successful!")

            return {
                "success": True,
                "message": f"Successfully submitted {file_name}",
                "submission_id": submission["id"],
                "submitted_at": format_date(submission.get("submitted_at")),
                "assignment_id": assignment_id,
                "file_name": file_name,
                "workflow_state": submission.get("workflow_state"),
                "attempt": submission.get("attempt"),
            }

        except Exception as e:
            logger.error(f"Submission failed: {str(e)}")
            return {"success": False, "error": f"Submission failed: {str(e)}"}
