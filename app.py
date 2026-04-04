from __future__ import annotations

import os
import shutil
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

from flask import Flask, flash, g, redirect, render_template, request, send_from_directory, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename


BASE_DIR = Path(__file__).resolve().parent
DATA_ROOT = Path(os.getenv("DATA_ROOT", str(BASE_DIR)))
DATABASE_PATH = DATA_ROOT / "app.db"
UPLOADS_DIR = DATA_ROOT / "uploads"
REPO_DATABASE_PATH = BASE_DIR / "app.db"
REPO_UPLOADS_DIR = BASE_DIR / "uploads"

AUTHOR_EMAIL = os.getenv("AUTHOR_EMAIL", "tom@gmail.com")
AUTHOR_PASSWORD = os.getenv("AUTHOR_PASSWORD", "12344321")

ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "gif"}
ALLOWED_VIDEO_EXTENSIONS = {"mp4", "webm", "mov", "m4v"}
BAD_WORDS = (
    "хуй",
    "пизд",
    "еба",
    "єба",
    "йоб",
    "бля",
    "сук",
    "нахуй",
    "муд",
    "fuck",
    "shit",
    "bitch",
)
REACTIONS = {
    "like": {"column": "like_count"},
    "heart": {"column": "heart_count"},
    "fire": {"column": "fire_count"},
}
LEGACY_POST_TRANSLATIONS = {
    "Теплая фокачча с травами": {
        "title": "Тепла фокача з травами",
        "description": "М'яка домашня фокача з оливковою олією, часником і запашними травами. Добре пасує до супів, пасти або просто до вечірнього чаю.",
        "category": "recipe",
    },
    "Видео: карамельные сырники без лишней возни": {
        "title": "Відео: карамельні сирники без зайвого клопоту",
        "description": "Короткий ролик із ніжними сирниками, золотистою скоринкою та акуратною подачею. Ідеально для сніданку або спокійного пізнього ранку.",
        "category": "video",
    },
}


app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("FLASK_SECRET_KEY", "friend-recipe-secret-key")
app.config["MAX_CONTENT_LENGTH"] = 200 * 1024 * 1024


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(_: object | None) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()


def ensure_column(cursor: sqlite3.Cursor, table: str, column: str, definition: str) -> None:
    columns = {row[1] for row in cursor.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in columns:
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def is_allowed_file(filename: str, allowed_extensions: set[str]) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in allowed_extensions


def save_uploaded_file(file_storage, allowed_extensions: set[str]) -> str:
    filename = secure_filename(file_storage.filename or "")
    if not filename or not is_allowed_file(filename, allowed_extensions):
        raise ValueError("Цей формат файлу не підтримується.")

    extension = filename.rsplit(".", 1)[1].lower()
    new_name = f"{uuid.uuid4().hex}.{extension}"
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    destination = UPLOADS_DIR / new_name
    file_storage.save(destination)
    return f"uploads/{new_name}"


def normalize_text(text: str) -> str:
    return "".join(ch.lower() for ch in text if ch.isalnum() or ch.isspace())


def contains_bad_words(text: str) -> bool:
    normalized = normalize_text(text)
    return any(word in normalized for word in BAD_WORDS)


def format_datetime_label(value: str | None) -> str:
    if not value:
        return ""

    for parser in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            parsed = datetime.strptime(value, parser)
            return parsed.strftime("%d.%m.%Y • %H:%M")
        except ValueError:
            continue
    return value


def get_current_author_email() -> str:
    author_row = get_db().execute("SELECT email FROM author WHERE id = 1").fetchone()
    if author_row and author_row["email"]:
        return author_row["email"]
    return AUTHOR_EMAIL


def bootstrap_data_root() -> None:
    DATA_ROOT.mkdir(parents=True, exist_ok=True)

    if DATA_ROOT == BASE_DIR:
        return

    if not DATABASE_PATH.exists() and REPO_DATABASE_PATH.exists():
        shutil.copy2(REPO_DATABASE_PATH, DATABASE_PATH)

    if REPO_UPLOADS_DIR.exists():
        UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
        for source_file in REPO_UPLOADS_DIR.iterdir():
            target_file = UPLOADS_DIR / source_file.name
            if source_file.is_file() and not target_file.exists():
                shutil.copy2(source_file, target_file)


def import_initial_content_from_repo(cursor: sqlite3.Cursor) -> None:
    if DATA_ROOT == BASE_DIR or not REPO_DATABASE_PATH.exists() or REPO_DATABASE_PATH == DATABASE_PATH:
        return

    target_posts_count = cursor.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
    if target_posts_count > 0:
        return

    source_db = sqlite3.connect(REPO_DATABASE_PATH)
    source_db.row_factory = sqlite3.Row

    try:
        source_columns = {
            row[1] for row in source_db.execute("PRAGMA table_info(posts)").fetchall()
        }
        like_expr = "like_count" if "like_count" in source_columns else "0"
        heart_expr = "heart_count" if "heart_count" in source_columns else "0"
        fire_expr = "fire_count" if "fire_count" in source_columns else "0"

        source_posts = source_db.execute(
            f"""
            SELECT title, category, description, image_url, video_url, created_at,
                   {like_expr} AS like_count,
                   {heart_expr} AS heart_count,
                   {fire_expr} AS fire_count
            FROM posts
            ORDER BY id
            """
        ).fetchall()

        if not source_posts:
            return

        source_author = source_db.execute(
            "SELECT email, password_hash FROM author WHERE id = 1"
        ).fetchone()
        if source_author:
            cursor.execute(
                "UPDATE author SET email = ?, password_hash = ? WHERE id = 1",
                (source_author["email"], source_author["password_hash"]),
            )

        cursor.executemany(
            """
            INSERT INTO posts (
                title, category, description, image_url, video_url, created_at,
                like_count, heart_count, fire_count
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    post["title"],
                    post["category"],
                    post["description"],
                    post["image_url"],
                    post["video_url"],
                    post["created_at"],
                    post["like_count"],
                    post["heart_count"],
                    post["fire_count"],
                )
                for post in source_posts
            ],
        )

        target_posts = cursor.execute(
            "SELECT id, title, created_at FROM posts ORDER BY id"
        ).fetchall()
        target_map = {
            (row["title"], row["created_at"]): row["id"]
            for row in target_posts
        }

        source_posts_with_ids = source_db.execute(
            "SELECT id, title, created_at FROM posts ORDER BY id"
        ).fetchall()
        post_id_map = {
            source_row["id"]: target_map.get((source_row["title"], source_row["created_at"]))
            for source_row in source_posts_with_ids
        }

        source_comments = source_db.execute(
            """
            SELECT post_id, author_name, body, created_at
            FROM comments
            ORDER BY id
            """
        ).fetchall()
        comment_rows = [
            (
                post_id_map[comment["post_id"]],
                comment["author_name"],
                comment["body"],
                comment["created_at"],
            )
            for comment in source_comments
            if post_id_map.get(comment["post_id"])
        ]
        if comment_rows:
            cursor.executemany(
                """
                INSERT INTO comments (post_id, author_name, body, created_at)
                VALUES (?, ?, ?, ?)
                """,
                comment_rows,
            )
    finally:
        source_db.close()


def migrate_legacy_post_content(cursor: sqlite3.Cursor) -> None:
    for old_title, payload in LEGACY_POST_TRANSLATIONS.items():
        cursor.execute(
            """
            UPDATE posts
            SET title = ?, description = ?, category = ?
            WHERE title = ?
            """,
            (
                payload["title"],
                payload["description"],
                payload["category"],
                old_title,
            ),
        )


def init_db() -> None:
    bootstrap_data_root()
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

    db = sqlite3.connect(DATABASE_PATH)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    cursor = db.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS author (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            email TEXT NOT NULL,
            password_hash TEXT NOT NULL
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            category TEXT NOT NULL,
            description TEXT NOT NULL,
            image_url TEXT,
            video_url TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id INTEGER NOT NULL,
            author_name TEXT NOT NULL,
            body TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(post_id) REFERENCES posts(id) ON DELETE CASCADE
        )
        """
    )

    ensure_column(cursor, "posts", "like_count", "INTEGER NOT NULL DEFAULT 0")
    ensure_column(cursor, "posts", "heart_count", "INTEGER NOT NULL DEFAULT 0")
    ensure_column(cursor, "posts", "fire_count", "INTEGER NOT NULL DEFAULT 0")

    cursor.execute("SELECT id FROM author WHERE id = 1")
    if cursor.fetchone() is None:
        cursor.execute(
            "INSERT INTO author (id, email, password_hash) VALUES (1, ?, ?)",
            (AUTHOR_EMAIL, generate_password_hash(AUTHOR_PASSWORD)),
        )

    import_initial_content_from_repo(cursor)
    migrate_legacy_post_content(cursor)
    db.commit()
    db.close()


def map_comment_row(comment: sqlite3.Row) -> dict:
    return {
        "id": comment["id"],
        "author_name": comment["author_name"],
        "body": comment["body"],
        "created_at": comment["created_at"],
        "created_at_display": format_datetime_label(comment["created_at"]),
    }


def map_post_row(post: sqlite3.Row, comments_by_post: dict[int, list[sqlite3.Row]]) -> dict:
    raw_video_url = post["video_url"] or ""
    raw_image_url = post["image_url"] or ""
    video_url = raw_video_url
    image_url = raw_image_url or "https://images.unsplash.com/photo-1495521821757-a1efb6729352?auto=format&fit=crop&w=1400&q=80"
    if video_url.startswith("uploads/"):
        video_url = url_for("uploaded_file", filename=video_url.removeprefix("uploads/"))
    if image_url.startswith("uploads/"):
        image_url = url_for("uploaded_file", filename=image_url.removeprefix("uploads/"))

    return {
        "id": post["id"],
        "title": post["title"],
        "category": post["category"],
        "description": post["description"],
        "image_url": image_url,
        "video_url": video_url,
        "raw_image_url": raw_image_url,
        "raw_video_url": raw_video_url,
        "is_uploaded_video": raw_video_url.startswith("uploads/") if raw_video_url else False,
        "created_at": post["created_at"],
        "created_at_display": format_datetime_label(post["created_at"]),
        "like_count": post["like_count"],
        "heart_count": post["heart_count"],
        "fire_count": post["fire_count"],
        "comments": [map_comment_row(comment) for comment in comments_by_post.get(post["id"], [])],
    }


def fetch_comments_grouped() -> dict[int, list[sqlite3.Row]]:
    comments_rows = get_db().execute(
        """
        SELECT id, post_id, author_name, body, created_at
        FROM comments
        ORDER BY datetime(created_at) DESC, id DESC
        """
    ).fetchall()

    comments_by_post: dict[int, list[sqlite3.Row]] = {}
    for comment in comments_rows:
        comments_by_post.setdefault(comment["post_id"], []).append(comment)
    return comments_by_post


def fetch_posts(category: str | None = None) -> list[dict]:
    query = """
        SELECT id, title, category, description, image_url, video_url, created_at,
               like_count, heart_count, fire_count
        FROM posts
    """
    params: list[str] = []
    if category:
        query += " WHERE category = ?"
        params.append(category)
    query += " ORDER BY datetime(created_at) DESC, id DESC"

    posts_rows = get_db().execute(query, params).fetchall()
    comments_by_post = fetch_comments_grouped()
    return [map_post_row(post, comments_by_post) for post in posts_rows]


def fetch_post(post_id: int) -> dict | None:
    post_row = get_db().execute(
        """
        SELECT id, title, category, description, image_url, video_url, created_at,
               like_count, heart_count, fire_count
        FROM posts
        WHERE id = ?
        """,
        (post_id,),
    ).fetchone()

    if post_row is None:
        return None

    comments_by_post = fetch_comments_grouped()
    return map_post_row(post_row, comments_by_post)


def fetch_latest_posts(limit: int = 4) -> list[dict]:
    posts_rows = get_db().execute(
        """
        SELECT id, title, category, description, image_url, video_url, created_at,
               like_count, heart_count, fire_count
        FROM posts
        ORDER BY datetime(created_at) DESC, id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    comments_by_post = fetch_comments_grouped()
    return [map_post_row(post, comments_by_post) for post in posts_rows]


def is_author_logged_in() -> bool:
    return bool(session.get("author_logged_in"))


@app.route("/uploads/<path:filename>")
def uploaded_file(filename: str):
    return send_from_directory(UPLOADS_DIR, filename)


@app.context_processor
def inject_globals():
    return {
        "is_author_logged_in": is_author_logged_in(),
        "current_email": get_current_author_email(),
    }


@app.route("/")
def home():
    return render_template("home.html", posts=fetch_latest_posts())


@app.route("/recipes")
def recipes():
    return render_template("recipes.html", posts=fetch_posts("recipe"))


@app.route("/videos")
def videos():
    return render_template("videos.html", posts=fetch_posts("video"))


@app.route("/author")
def author():
    edit_post = None
    edit_id = request.args.get("edit", "").strip()
    if is_author_logged_in() and edit_id.isdigit():
        edit_post = fetch_post(int(edit_id))
        if edit_post is None:
            flash("Не вдалося знайти запис для редагування.", "error")
        else:
            edit_post["image_input_value"] = (
                edit_post["raw_image_url"] if edit_post["raw_image_url"] and not edit_post["raw_image_url"].startswith("uploads/") else ""
            )
            edit_post["video_input_value"] = (
                edit_post["raw_video_url"] if edit_post["raw_video_url"] and not edit_post["raw_video_url"].startswith("uploads/") else ""
            )
    return render_template("author.html", posts=fetch_posts(), edit_post=edit_post)


@app.post("/login")
def login():
    email = request.form.get("email", "").strip()
    password = request.form.get("password", "").strip()

    author_row = get_db().execute("SELECT email, password_hash FROM author WHERE id = 1").fetchone()

    if author_row and email == author_row["email"] and check_password_hash(author_row["password_hash"], password):
        session["author_logged_in"] = True
        flash("Вхід успішний. Панель автора відкрита.", "success")
    else:
        flash("Невірна пошта або пароль.", "error")
    return redirect(url_for("author"))


@app.post("/logout")
def logout():
    session.pop("author_logged_in", None)
    flash("Ти вийшов із панелі автора.", "info")
    return redirect(url_for("author"))


def collect_post_form_data(existing_post: dict | None = None) -> tuple[str, str, str, str, str]:
    title = request.form.get("title", "").strip()
    category = request.form.get("category", "recipe").strip()
    description = request.form.get("description", "").strip()
    image_url = request.form.get("image_url", "").strip()
    video_url = request.form.get("video_url", "").strip()

    if category not in {"recipe", "video"}:
        category = "recipe"

    if existing_post:
        image_url = image_url or existing_post["raw_image_url"]
        video_url = video_url or existing_post["raw_video_url"]

    return title, category, description, image_url, video_url


def replace_post_files(image_url: str, video_url: str) -> tuple[str, str]:
    image_file = request.files.get("image_file")
    video_file = request.files.get("video_file")

    if image_file and image_file.filename:
        image_url = save_uploaded_file(image_file, ALLOWED_IMAGE_EXTENSIONS)
    if video_file and video_file.filename:
        video_url = save_uploaded_file(video_file, ALLOWED_VIDEO_EXTENSIONS)

    return image_url, video_url


@app.post("/posts")
def create_post():
    if not is_author_logged_in():
        flash("Лише автор може додавати нові записи.", "error")
        return redirect(url_for("author"))

    title, category, description, image_url, video_url = collect_post_form_data()

    if not title or not description:
        flash("Заповни назву й короткий опис запису.", "error")
        return redirect(url_for("author"))

    try:
        image_url, video_url = replace_post_files(image_url, video_url)
    except ValueError as error:
        flash(str(error), "error")
        return redirect(url_for("author"))

    if category == "recipe":
        video_url = ""

    db = get_db()
    db.execute(
        """
        INSERT INTO posts (title, category, description, image_url, video_url)
        VALUES (?, ?, ?, ?, ?)
        """,
        (title, category, description, image_url, video_url),
    )
    db.commit()
    flash("Новий запис опубліковано.", "success")
    return redirect(url_for("author"))


@app.post("/posts/<int:post_id>/update")
def update_post(post_id: int):
    if not is_author_logged_in():
        flash("Лише автор може редагувати записи.", "error")
        return redirect(url_for("author"))

    existing_post = fetch_post(post_id)
    if existing_post is None:
        flash("Запис для редагування не знайдено.", "error")
        return redirect(url_for("author"))

    title, category, description, image_url, video_url = collect_post_form_data(existing_post)

    if not title or not description:
        flash("Назва й опис мають бути заповнені.", "error")
        return redirect(url_for("author", edit=post_id))

    try:
        image_url, video_url = replace_post_files(image_url, video_url)
    except ValueError as error:
        flash(str(error), "error")
        return redirect(url_for("author", edit=post_id))

    if category == "recipe":
        video_url = ""

    db = get_db()
    db.execute(
        """
        UPDATE posts
        SET title = ?, category = ?, description = ?, image_url = ?, video_url = ?
        WHERE id = ?
        """,
        (title, category, description, image_url, video_url, post_id),
    )
    db.commit()
    flash("Запис оновлено. Виправлення збережені.", "success")
    return redirect(url_for("author") + f"#post-{post_id}")


@app.post("/posts/<int:post_id>/delete")
def delete_post(post_id: int):
    if not is_author_logged_in():
        flash("Лише автор може видаляти записи.", "error")
        return redirect(url_for("author"))

    existing_post = get_db().execute("SELECT id FROM posts WHERE id = ?", (post_id,)).fetchone()
    if existing_post is None:
        flash("Запис для видалення не знайдено.", "error")
        return redirect(url_for("author"))

    db = get_db()
    db.execute("DELETE FROM posts WHERE id = ?", (post_id,))
    db.commit()
    flash("Запис видалено.", "success")
    return redirect(url_for("author"))


@app.post("/comments")
def create_comment():
    post_id = request.form.get("post_id", "").strip()
    author_name = request.form.get("author_name", "").strip()
    body = request.form.get("body", "").strip()
    next_page = request.form.get("next_page", "home").strip()
    redirect_target = next_page if next_page in {"home", "recipes", "videos", "author"} else "home"

    if not post_id.isdigit():
        flash("Не вдалося визначити, до якого запису належить коментар.", "error")
        return redirect(url_for(redirect_target))

    if not author_name or not body:
        flash("Щоб залишити коментар, вкажи ім'я та текст.", "error")
        return redirect(url_for(redirect_target) + f"#post-{post_id}")

    if contains_bad_words(author_name) or contains_bad_words(body):
        flash("Коментар не опубліковано, бо в ньому є лайка або грубі слова.", "error")
        return redirect(url_for(redirect_target) + f"#post-{post_id}")

    db = get_db()
    db.execute(
        """
        INSERT INTO comments (post_id, author_name, body)
        VALUES (?, ?, ?)
        """,
        (int(post_id), author_name, body),
    )
    db.commit()
    flash("Коментар опубліковано.", "success")
    return redirect(url_for(redirect_target) + f"#post-{post_id}")


@app.post("/posts/<int:post_id>/react/<reaction>")
def react(post_id: int, reaction: str):
    next_page = request.form.get("next_page", "home").strip()
    redirect_target = next_page if next_page in {"home", "recipes", "videos", "author"} else "home"

    if reaction not in REACTIONS:
        flash("Такої реакції не існує.", "error")
        return redirect(url_for(redirect_target) + f"#post-{post_id}")

    column = REACTIONS[reaction]["column"]
    db = get_db()
    db.execute(f"UPDATE posts SET {column} = {column} + 1 WHERE id = ?", (post_id,))
    db.commit()
    return redirect(url_for(redirect_target) + f"#post-{post_id}")


init_db()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=False)
