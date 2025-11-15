# src/mcp/canvas_server.py

from fastmcp import FastMCP
from pydantic import Field
from typing import List, Dict, Any
import os
from dotenv import load_dotenv
from src.utils.text_sanitizer import sanitize_data
from src.canvas.client import CanvasClient

load_dotenv()

# Initialize Canvas client
canvas = CanvasClient(
    base_url=os.getenv("CANVAS_URL"), access_token=os.getenv("CANVAS_TOKEN")
)

# Create MCP server
mcp = FastMCP(
    name="canvas-lms",
    instructions="""Canvas LMS assistant that helps students with courses, assignments, grades, and announcements.""",
)


@mcp.tool()
async def get_courses() -> List[Dict[str, Any]]:
    """Get all enrolled courses with id, name, course_code, and current grade."""
    result = canvas.get_courses()
    return sanitize_data(result)


@mcp.tool()
async def get_assignments(
    course_id: str = Field(description="Canvas course ID"),
) -> List[Dict[str, Any]]:
    """Get all assignments for a course including due dates, grades, and submission status."""
    result = canvas.get_assignments(course_id)
    return sanitize_data(result)


@mcp.tool()
async def get_upcoming_assignments(
    days: int = Field(
        default=7,
        description="Number of days to look ahead from today. Use smart values: 6 for 'this week', 21 for 'this month', etc.",
    ),
    include_overdue: bool = Field(
        default=True,
        description="Include overdue unsubmitted assignments from the past week",
    ),
) -> List[Dict[str, Any]]:
    """
    Get assignments due in the upcoming days, with smart handling of temporal queries.

    Examples:
    - "What's due this week?" → days=6 (Sun-Sat)
    - "What's due this month?" → days=21 (rest of November)
    - "What's due in 5 days?" → days=5
    - "What's overdue?" → days=0, include_overdue=True

    By default, includes overdue unsubmitted assignments from the past 7 days.
    """
    result = canvas.get_upcoming_assignments(
        days=days, include_past_week=include_overdue
    )
    return sanitize_data(result)


@mcp.tool()
async def get_grades(
    course_id: str = Field(description="Canvas course ID"),
) -> Dict[str, Any]:
    """Get grade information for a specific course."""
    result = canvas.get_grades(course_id)
    return sanitize_data(result)


@mcp.tool()
async def get_all_grades() -> List[Dict[str, Any]]:
    """Get grades for ALL enrolled courses at once. Use this for 'How am I doing overall?' queries."""
    result = canvas.get_all_grades()
    return sanitize_data(result)


@mcp.tool()
async def get_quizzes(
    course_id: str = Field(description="Canvas course ID"),
) -> List[Dict[str, Any]]:
    """Get all quizzes for a course with grades and submission status."""
    result = canvas.get_quizzes(course_id)
    return sanitize_data(result)


@mcp.tool()
async def get_announcements(
    days: int = Field(default=7, description="Number of days to look back"),
) -> List[Dict[str, Any]]:
    """Get recent announcements from all enrolled courses."""
    result = canvas.get_announcements(days)
    return sanitize_data(result)


@mcp.tool()
async def get_discussions(
    course_id: str = Field(description="Canvas course ID"),
) -> List[Dict[str, Any]]:
    """Get discussion topics for a course."""
    result = canvas.get_discussions(course_id)
    return sanitize_data(result)


@mcp.tool()
async def get_course_files(
    course_id: str = Field(description="Canvas course ID"),
) -> List[Dict[str, Any]]:
    """Get files and documents for a course."""
    result = canvas.get_course_files(course_id)
    return sanitize_data(result)


@mcp.tool()
async def get_modules(
    course_id: str = Field(description="Canvas course ID"),
) -> List[Dict[str, Any]]:
    """Get course modules/structure. Returns files if no modules exist."""
    result = canvas.get_modules(course_id)
    return sanitize_data(result)


@mcp.tool()
async def get_course_summary(
    course_id: str = Field(description="Canvas course ID"),
) -> Dict[str, Any]:
    """Get complete course overview: grades, upcoming assignments, recent announcements."""
    result = canvas.get_course_summary(course_id)
    return sanitize_data(result)


@mcp.tool()
async def get_course_id_by_name(
    course_name: str = Field(description="Course name or code to search for"),
) -> str:
    """Find course ID by name (e.g., 'CS 555', 'Machine Learning'). Returns numeric ID or error."""
    course_id = canvas.get_course_id_by_name(course_name)
    return course_id if course_id else f"Course '{course_name}' not found"


@mcp.tool()
async def submit_assignment(
    course_id: str = Field(description="Canvas course ID"),
    assignment_id: str = Field(description="Assignment ID to submit to"),
    file_path: str = Field(
        description="Full path to file to submit (e.g., /home/user/report.pdf)"
    ),
    comment: str = Field(default="", description="Optional submission comment"),
) -> Dict[str, Any]:
    """
    Submit a file to a Canvas assignment. Uploads file and creates submission.
    IMPORTANT: Always verify assignment details before submitting!
    """
    result = canvas.submit_assignment(course_id, assignment_id, file_path, comment)
    return sanitize_data(result)


def main():
    """Entry point for the Canvas MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
