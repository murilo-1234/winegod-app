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
from routes.config import config_bp
from routes.ingest import ingest_bp
from routes.ingest_review import ingest_review_bp
from routes.ops import ops_bp
from routes.ops_dashboard import ops_dashboard_bp
from utils.observability import init_sentry, init_posthog


def create_app():
    flask_app = Flask(__name__)
    flask_app.config.from_object(Config)

    # Flask session requer SECRET_KEY. Data Ops Dashboard usa cookie httponly.
    # Se OPS_SESSION_SECRET nao setado, usa fallback (apenas local/testes).
    flask_app.secret_key = (
        getattr(Config, "OPS_SESSION_SECRET", None)
        or getattr(Config, "SECRET_KEY", None)
        or "local-dev-only-not-for-production"
    )

    # F11.2/F11.3 - observabilidade. Ambas chamadas sao no-op silencioso
    # se SENTRY_DSN / POSTHOG_API_KEY nao estao setados. Init antes do
    # CORS e dos blueprints porque Sentry precisa ver as rotas desde o
    # primeiro request.
    init_sentry(flask_app)
    init_posthog()

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
    flask_app.register_blueprint(config_bp, url_prefix='/api')
    flask_app.register_blueprint(ingest_bp, url_prefix='/api')
    flask_app.register_blueprint(ingest_review_bp, url_prefix='/api')
    # Winegod Data Ops: sem prefixo /api, endpoints em /ops/*.
    flask_app.register_blueprint(ops_bp)
    # Dashboard Fase 3 (HTML + UI-API), tambem sem prefixo /api.
    flask_app.register_blueprint(ops_dashboard_bp)

    return flask_app


# Gunicorn usa "app:app" — precisa existir no nivel do modulo
app = create_app()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(Config.FLASK_PORT), debug=True)
