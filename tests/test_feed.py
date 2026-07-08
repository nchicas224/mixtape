"""
tests/test_feed.py - Mixtape

Tests for feed retrieval logic.
"""

import pytest
from datetime import datetime, timezone, timedelta
from app import create_app, db
from models import User, Playlist, Song, ListeningEvent, friendships
from services.feed_service import get_friends_listening_now

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
    
def test_feed_shows_correct_friends_listening_now(app, user, monkeypatch):
    class FakeDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2024, 6, 16, 9, 0, 0, tzinfo=timezone.utc)
    
    monkeypatch.setattr("services.feed_service.datetime", FakeDateTime)
    with app.app_context():
        curr_user = db.session.get(User, user.id)
        friend = User(username="frienduser", email="frienduser@example.com")
        db.session.add(friend)
        db.session.flush()

        db.session.execute(friendships.insert().values(user_id=curr_user.id, friend_id=friend.id))
        db.session.execute(friendships.insert().values(user_id=friend.id, friend_id=curr_user.id))

        song = Song(title="Track 1", artist="Test Artist", shared_by=curr_user.id)
        db.session.add(song)
        db.session.flush()

        listened_at = datetime(2024, 6, 15, 23, 0, 0, tzinfo=timezone.utc)
        listening_event = ListeningEvent(
            user_id=friend.id,
            song_id=song.id,
            listened_at=listened_at
        )
        
        db.session.add(listening_event)
        db.session.commit()

        feed = get_friends_listening_now(curr_user.id)

        assert feed == []


