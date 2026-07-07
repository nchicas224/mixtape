# Mixtape Codebase Map

## Main Files

`app.py` is the Flask application factory. It creates the app, sets the database configuration, connects SQLAlchemy with `db.init_app(app)`, registers the route blueprints, and calls `db.create_all()` inside an app context so the database tables exist before requests are handled.

`models.py` defines the database structure with SQLAlchemy models. The main models are `User`, `Song`, `Tag`, `Playlist`, `ListeningEvent`, `Rating`, and `Notification`. It also defines join tables for many-to-many relationships: `friendships` connects users to friends, `song_tags` connects songs to tags, and `playlist_entries` connects playlists to songs while storing playlist order and who added the song. Most models have a `to_dict()` method so route responses can return JSON-friendly dictionaries.

`routes/` contains the request-facing Flask blueprints. These files read URL parameters, query parameters, or JSON body data, then call service functions and return JSON responses.

- `routes/songs.py` handles song search, song detail lookup, rating songs, and recording listens.
- `routes/playlists.py` handles playlist creation, playlist detail lookup, playlist song lookup, and adding songs to playlists.
- `routes/users.py` handles user profiles, streak lookup, notification lookup, and marking notifications as read.
- `routes/feed.py` handles the friends listening now feed and the general activity feed.

`services/` contains the business logic and most database operations. The route files stay small because they delegate the real work to services.

- `services/search_service.py` searches songs and loads single song details.
- `services/playlist_service.py` creates playlists and retrieves playlist data.
- `services/notification_service.py` creates notifications, adds songs to playlists, rates songs, retrieves notifications, and marks notifications as read.
- `services/streak_service.py` records listening events and updates listening streaks.
- `services/feed_service.py` builds friend listening feeds from listening events.

`seed_data.py` resets and fills the database with sample users, friendships, songs, tags, playlists, listening events, ratings, and notifications. This gives the app realistic data to test with.

`tests/` contains pytest tests for important behavior like streaks, search, and playlists. These tests call into the app and service logic to check expected behavior.

`README.md` explains the project purpose, setup steps, file structure, test commands, and the main areas of the app.

## Data Flow: Adding A Song To A Playlist

The playlist add flow starts when a client sends a request to:

```http
POST /playlists/<playlist_id>/songs
```

The JSON body must include:

```json
{
  "song_id": "the-song-id",
  "added_by": "the-user-id"
}
```

In `routes/playlists.py`, the `add_song()` route reads `song_id` and `added_by` from the request body. If either value is missing, it returns a `400` error. If both are present, it calls:

```python
add_to_playlist(playlist_id, song_id, added_by)
```

That function lives in `services/notification_service.py`. It loads the `Song`, the user who added the song, and the `Playlist` from the database. If any of them do not exist, it raises a `ValueError`, and the route turns that into an error response.

If the song is not already in the playlist, `add_to_playlist()` appends the song to `playlist.songs` and commits the change. The relationship between playlists and songs is stored through the `playlist_entries` join table from `models.py`.

After adding the song, the service checks whether the user who added it is different from the user who originally shared the song. If they are different, it calls `create_notification()` to create a `Notification` row for the original sharer. The notification body says who added the song and which playlist it was added to.

Later, that user can fetch their notifications through:

```http
GET /users/<user_id>/notifications
```

That route is in `routes/users.py`, and it calls `get_notifications()` from `services/notification_service.py`.

## Organization Patterns

The app uses a clear route-service-model pattern. Routes handle HTTP concerns like reading request data, validating required fields, choosing status codes, and returning JSON. Services handle business rules and database changes. Models define the shape of the database and relationships.

SQLAlchemy relationships are used to connect models instead of manually storing every connection on one table. For example, songs and tags are connected through `song_tags`, playlists and songs are connected through `playlist_entries`, and users are connected to friends through `friendships`.

The app often converts model objects to dictionaries before returning them from routes. Methods like `Song.to_dict()`, `User.to_dict()`, and `Notification.to_dict()` control exactly what fields appear in API responses and convert datetimes into strings with `isoformat()`.

Database writes usually happen in service functions. The common pattern is to load needed models with `db.session.get(...)`, create or update model objects, add new objects with `db.session.add(...)`, and save changes with `db.session.commit()`.
