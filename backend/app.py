from flask import Flask
from flask_cors import CORS
from config import Config
from routes.chat import chat_bp
from routes.health import health_bp


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    CORS(app, origins=["http://localhost:3000", "https://chat.winegod.ai"])

    app.register_blueprint(chat_bp, url_prefix='/api')
    app.register_blueprint(health_bp)

    return app


if __name__ == '__main__':
    app = create_app()
    app.run(host='0.0.0.0', port=int(Config.FLASK_PORT), debug=True)
