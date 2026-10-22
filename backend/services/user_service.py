from flask import jsonify

from backend.repositories import user_repository


def list_users():
    return jsonify(users=user_repository.find_all())
