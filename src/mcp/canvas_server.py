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


def main():
    """Entry point for the Canvas MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
