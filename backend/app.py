import re

from flask import Flask
from flask_cors import CORS
from config import Config
from routes.chat import chat_bp
from routes.health import health_bp


def create_app():
    flask_app = Flask(__name__)
    flask_app.config.from_object(Config)

    CORS(flask_app, origins=[
        "http://localhost:3000",
        "https://chat.winegod.ai",
        re.compile(r"https://winegod.*\.vercel\.app"),
    ])

    flask_app.register_blueprint(chat_bp, url_prefix='/api')
    flask_app.register_blueprint(health_bp)

    return flask_app


# Gunicorn usa "app:app" — precisa existir no nivel do modulo
app = create_app()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(Config.FLASK_PORT), debug=True)
