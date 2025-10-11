from fastmcp import FastMCP
from pydantic import Field
from typing import List, Dict, Any
import os
from dotenv import load_dotenv

# Import Canvas client
from src.canvas.client import CanvasClient

load_dotenv()

# Initialize Canvas client
canvas = CanvasClient(
    base_url=os.getenv("CANVAS_URL"),
    access_token=os.getenv("CANVAS_TOKEN")
)

# Create MCP server
mcp = FastMCP(
    name="canvas-lms",
    instructions="""
    This is a Canvas LMS server that provides access to:
    - Course information and enrollment data
    - Assignments and due dates
    - Grades and submissions
    - Recent announcements
    
    Use these tools to help students manage their academic workload.
    """
)


@mcp.tool()
async def get_courses() -> List[Dict[str, Any]]:
    """Get all enrolled courses for the current user.
    
    Returns a list of courses with id, name, course_code, enrollment term, 
    and current grade information.
    """
    return canvas.get_courses()


@mcp.tool()
async def get_assignments(
    course_id: str = Field(description="Canvas course ID")
) -> List[Dict[str, Any]]:
    """Get all assignments for a specific course.
    
    Returns assignment details including:
    - Name and ID
    - Due date
    - Points possible
    - Submission status (submitted or not)
    - Grade and score if submitted
    """
    return canvas.get_assignments(course_id)


@mcp.tool()
async def get_upcoming_assignments(
    days: int = Field(
        default=7, 
        description="Number of days to look ahead (default: 7)"
    )
) -> List[Dict[str, Any]]:
    """Get all upcoming assignments across all enrolled courses.
    
    Returns assignments due within the specified number of days,
    sorted by due date. Includes course information for each assignment.
    """
    return canvas.get_upcoming_assignments(days)


@mcp.tool()
async def get_grades(
    course_id: str = Field(description="Canvas course ID")
) -> Dict[str, Any]:
    """Get grade information for a specific course.
    
    Returns current grade, final grade, scores, and unposted grades
    for the specified course.
    """
    return canvas.get_grades(course_id)


@mcp.tool()
async def get_announcements(
    days: int = Field(
        default=7,
        description="Number of days to look back (default: 7)"
    )
) -> List[Dict[str, Any]]:
    """Get recent announcements from all enrolled courses.
    
    Returns announcements posted within the specified number of days,
    including title, message, author, and posting date.
    """
    return canvas.get_announcements(days)

@mcp.tool()
async def get_discussions(
    course_id: str = Field(description="Canvas course ID")
) -> List[Dict[str, Any]]:
    """Get discussion topics for a specific course.
    
    Returns discussion topics including:
    - Title and message preview
    - Author and posted date
    - Unread count and reply count
    - Discussion type
    """
    return canvas.get_discussions(course_id)


@mcp.tool()
async def get_course_files(
    course_id: str = Field(description="Canvas course ID")
) -> List[Dict[str, Any]]:
    """Get files and documents for a specific course.
    
    Returns file information including:
    - Display name and filename
    - File size and type
    - Upload/update dates
    - Download URL
    """
    return canvas.get_course_files(course_id)


@mcp.tool()
async def get_calendar_events(
    days_ahead: int = Field(
        default=14,
        description="Number of days to look ahead (default: 14)"
    )
) -> List[Dict[str, Any]]:
    """Get upcoming calendar events from Canvas.
    
    Returns events including:
    - Event title and description
    - Start and end times
    - Location
    - Associated course
    """
    return canvas.get_calendar_events(days_ahead)

def main():
    """Entry point for the Canvas MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
