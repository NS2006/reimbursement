from urllib.parse import quote

from flask import Response, jsonify

from backend.repositories import attachment_repository
from backend.services import file_storage

# The file of an attachment (a receipt photo or PDF), for the website. It was copied into our file storage when the
# report arrived (the other system's link has expired since); the backend reads it from there and passes it on, so
# the website gets it from its own address (no CORS or embedding rules in the way, and pdf.js can read it).


def get_file(attachment_id):
    """GET /api/attachments/<id>/file: the attachment's file, shown inline (an image or a PDF).

    Answers 404 for an unknown attachment or a file missing from the storage, and 502 when the storage can't be
    reached."""
    attachment = attachment_repository.find(attachment_id)
    if attachment is None:
        return _error(404, "not_found", f"No attachment with id {attachment_id}.")

    try:
        data = file_storage.read(attachment["storage_path"])
    except file_storage.StorageError as error:
        if error.missing:
            return _error(404, "file_missing", f"The file of {attachment['name']} is not in the file storage.")
        return _error(502, "file_storage_unavailable", f"The file of {attachment['name']} can't be read right now.")

    return Response(data, content_type=attachment["content_type"], headers={
        "Content-Disposition": f"inline; filename*=UTF-8''{quote(attachment['name'])}",
        "X-Content-Type-Options": "nosniff",
        # Stored under its content, so the file of an attachment never changes
        "Cache-Control": "private, max-age=86400, immutable",
    })


def _error(status, error, message):
    return jsonify(error=error, message=message), status
