from dataclasses import dataclass

@dataclass
class Course:
    id: int
    name: str

    @classmethod
    def from_dict(cls, d: dict) -> "Course":
        return cls(id=d["id"], name=d.get("name", "Unnamed"))
