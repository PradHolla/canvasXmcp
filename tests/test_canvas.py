from src.canvas.client import CanvasClient
from src.canvas.models import Course


def test_get_course_and_model():
    client = CanvasClient()
    data = client.get_course(1)
    assert data["id"] == 1
    course = Course.from_dict(data)
    assert course.name == "Course 1"


def test_get_course_invalid():
    client = CanvasClient()
    try:
        client.get_course(0)
        assert False, "Expected ValueError for course_id=0"
    except ValueError:
        assert True
