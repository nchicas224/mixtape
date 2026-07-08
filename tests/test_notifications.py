"""
tests/test_notifications.py - Mixtape

Tests for notification creation and retrieval logic.
"""

import pytest
from app import create_app, db
from models import User, Song
from services.notification_service import rate_song, get_notifications

@pytest.fixture
def app():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    with app.app_context():
        db.create_all()
        yield app
        db.drop_all()

@pytest.fixture
def user(app):
    with app.app_context():
        u = User(username="testuser", email="test@example.com")
        db.session.add(u)
        db.session.commit()
        yield u

@pytest.fixture
def rater(app):
    with app.app_context():
        f = User(username="rater", email="rater@example.com")
        db.session.add(f)
        db.session.commit()
        yield f

def test_notification_sent_after_song_rating(app, user, rater):
    with app.app_context():
        curr_user = db.session.get(User, user.id)
        rater_user = db.session.get(User, rater.id)

        song = Song(title="Track 1", artist="Test Artist", shared_by=curr_user.id)
        db.session.add(song)
        db.session.flush()

        score = 5
        rating = rate_song(
            user_id=rater_user.id,
            song_id=song.id,
            score=score
        )

        notifications = get_notifications(user_id=curr_user.id)

        assert any(
            n["user_id"] == curr_user.id
            and n["type"] == "song_rated"
            and rater_user.username in n["body"]
            and song.title in n["body"]
            for n in notifications
        )
