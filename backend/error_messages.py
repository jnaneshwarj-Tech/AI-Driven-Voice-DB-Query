"""Central translation of internal failures into safe user messages."""
import logging

from fastapi import HTTPException


logger = logging.getLogger(__name__)


def user_message(error: Exception | str, operation: str = "operation") -> str:
    """Return a short, non-technical message while logging the real failure."""
    text = str(error).lower()
    if "duplicate" in text or "1062" in text:
        return "Student already exists."
    if "admission" in text and ("year" in text or "batch" in text):
        return "Year doesn't match."
    if "not found" in text or "no record" in text:
        return "No record found."
    if "permission" in text or "forbidden" in text:
        return "Permission denied."
    if "usn" in text:
        return "Invalid USN."
    if operation == "delete":
        return "Could not delete student."
    if operation == "restore":
        return "Could not restore student."
    if operation == "update":
        return "Could not update student."
    if operation in {"insert", "add"}:
        return "Could not save changes."
    if operation == "upload":
        return "Upload failed."
    return "Something went wrong. Please try again."


def safe_http_error(status_code: int, error: Exception | str, operation: str = "operation") -> HTTPException:
    logger.error("%s failed: %s", operation, error)
    return HTTPException(status_code=status_code, detail=user_message(error, operation))
