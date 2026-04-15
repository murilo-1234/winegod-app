import re

from flask import Flask
from flask_cors import CORS
from config import Config
from routes.chat import chat_bp
from routes.health import health_bp
from routes.auth import auth_bp
from routes.credits import credits_bp
from routes.sharing import sharing_bp
from routes.auth_facebook import auth_facebook_bp
from routes.auth_apple import auth_apple_bp
from routes.auth_microsoft import auth_microsoft_bp
from routes.conversations import conversations_bp


def create_app():
    flask_app = Flask(__name__)
    flask_app.config.from_object(Config)

    CORS(flask_app, origins=[
        re.compile(r"http://localhost:\d+"),
        "https://chat.winegod.ai",
        re.compile(r"https://winegod.*\.vercel\.app"),
    ])

    flask_app.register_blueprint(chat_bp, url_prefix='/api')
    flask_app.register_blueprint(health_bp)
    flask_app.register_blueprint(auth_bp, url_prefix='/api')
    flask_app.register_blueprint(credits_bp, url_prefix='/api')
    flask_app.register_blueprint(sharing_bp, url_prefix='/api')
    flask_app.register_blueprint(auth_facebook_bp, url_prefix='/api')
    flask_app.register_blueprint(auth_apple_bp, url_prefix='/api')
    flask_app.register_blueprint(auth_microsoft_bp, url_prefix='/api')
    flask_app.register_blueprint(conversations_bp, url_prefix='/api')

    return flask_app


# Gunicorn usa "app:app" — precisa existir no nivel do modulo
app = create_app()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(Config.FLASK_PORT), debug=True)
