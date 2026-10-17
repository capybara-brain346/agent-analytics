from fastapi import HTTPException, status


def not_implemented() -> HTTPException:
    return HTTPException(status.HTTP_501_NOT_IMPLEMENTED, "Not implemented yet")
