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

## Issue #1 - User reports that their streak continues to reset on the turnover from Saturday to Sunday

### How I reproduced it

I ran `pytest tests/test_streaks.py::test_streak_increments_on_sunday`. The test creates a user, calls `update_listening_streak()` with Saturday June 15, 2024, then calls it again with Sunday June 16, 2024. After the Saturday call, the streak is 1. After the Sunday call, the expected streak is 2 because the user listened on consecutive days. The actual value was still/reset to 1, and pytest failed with `assert 1 == 2`. My debug print showed `last_date=2024-06-15, days_since_last=1`, confirming the Sunday call was being treated as one day after the previous listen.

### How I found the root cause

I started in `tests/test_streaks.py` because I noticed failures when running the entire test suite with `pytest`. I also traced the data through the user route back into `get_streak`, where I noticed that the function just queries the existing streak. Since `get_streak` only reads the stored value, I looked into `record_listening_event` and `update_listening_streak` because those are where the streak gets changed. I added a debug statement in `update_listening_streak` because the user story said the user already had a continuous streak. When I ran the Sunday test, the debug statement printed `days_since_last=1`, which matched the expected Saturday-to-Sunday sequence after the first event was registered. That made me focus on the conditionals after that calculation, because the date difference was correct but the streak still reset.

### The root cause

The root cause was in `services/streak_service.py` on line 74. The composite conditional with `today.weekday()` did not match the intended behavior from the docstring. The condition checked whether it had been exactly one day since the user last listened and whether the current date was not Sunday: `days_since_last == 1 and today.weekday() != 6`. In Python, `weekday()` returns `6` for Sunday. That meant a valid Saturday-to-Sunday listen had `days_since_last == 1`, but still failed the increment condition because Sunday made `today.weekday() != 6` false. The code then fell into the reset branch instead of incrementing the streak.

### My fix and side-effect check

I removed `and today.weekday() != 6` so the condition became `elif days_since_last == 1:`. This matches the stated rule that listening on the next calendar day should increment the streak, regardless of which weekday it is.

After the fix, I reran `pytest tests/test_streaks.py::test_streak_increments_on_sunday`, and it passed with `1 passed`. I also ran the full test suite with `pytest`. The streak tests all passed, and the full suite reported `11 passed` and `2 failed`. The two remaining failures were in `tests/test_playlists.py`, so they were separate from the streak change. I removed the debug print after confirming the fix.

## Issue #2 - Friends from yesterday evening still appear in Listening Now

### How I reproduced it

I created a new test suite in `tests/test_feed.py`, set up pytest fixtures, and wrote a test function for the desired Listening Now behavior. I injected the `monkeypatch` fixture so I could patch `datetime` in `services/feed_service.py`. The monkeypatch made the feed service use a fake current time of June 16, 2024 at 9:00 AM UTC. In the test data, I created a current user, a friend, a friendship between them, a song, and a `ListeningEvent` where the friend listened at 11:00 PM UTC on June 15, 2024. I expected the feed to return an empty list because that listen happened yesterday. Before the fix, the function returned the friend in the list from `ListeningEvent` results.

### How I found the root cause

After tracing the request from `routes/feed.py` back to `get_friends_listening_now()` in `services/feed_service.py`, I noticed that the `ListeningEvent` query was filtered with a `cutoff` variable. That cutoff was calculated by subtracting the global `RECENT_THRESHOLD` from `datetime.now(timezone.utc)`. Since the user story described a midnight turnover problem, I focused on `RECENT_THRESHOLD` and the cutoff calculation. I wrote a test with mock data and monkeypatching to solidify the bug. The test reproduced the issue, which confirmed that the bug lived inside `get_friends_listening_now()` rather than in the route or the friendship setup.

### The root cause

When `RECENT_THRESHOLD` is set to `timedelta(hours=24)`, the feed uses a rolling 24-hour window without accounting for midnight turnover. At the fake current time of June 16, 2024 at 9:00 AM UTC, the cutoff becomes June 15, 2024 at 9:00 AM UTC. The friend's listen at June 15, 2024 at 11:00 PM UTC is later than that cutoff, so it passes the `ListeningEvent.listened_at >= cutoff` filter even though it happened yesterday. The user story expected Listening Now to show friends who listened today, not any friend who listened within the last 24 hours.

### My fix and side-effect check

I removed `RECENT_THRESHOLD` because the feed should not use a rolling 24-hour window. I also removed the `cutoff` variable and replaced it with a `start_of_today` threshold created from the current datetime. The `ListeningEvent` query still filters by friend user IDs, but now it checks `ListeningEvent.listened_at >= start_of_today` so only events from the current calendar day are included.

After the fix, I reran `pytest tests/test_feed.py::test_feed_shows_correct_friends_listening_now`, and it passed with `1 passed`. I also ran the full test suite with `pytest`. The feed test passed, and the full suite reported `12 passed` and `2 failed`. The two remaining failures were in `tests/test_playlists.py`, so they were separate from the feed change.
