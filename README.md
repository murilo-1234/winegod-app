# winegod.ai

AI sommelier global. Chat with Baco, the god of wine.

## What is WineGod?

WineGod.ai is an AI-powered wine recommendation platform. Ask Baco — the god of wine — about any wine, get personalized recommendations, compare options, and discover hidden gems from our database of 1.7M+ wines across 50 countries.

## Features

- Chat with Baco (AI sommelier persona)
- Wine recommendations by price, region, grape, occasion
- WineGod Score — proprietary value-for-money rating
- Multi-language support (responds in your language)
- Photo/label recognition (coming soon)
- Voice input (coming soon)

## Tech Stack

- **Frontend**: Next.js + TypeScript + Tailwind CSS
- **Backend**: Python/Flask
- **Database**: PostgreSQL (Render)
- **AI**: Claude API (Anthropic)
- **OCR**: Gemini Flash (Google)

## Getting Started

### Prerequisites
- Node.js >= 18
- Python >= 3.10
- PostgreSQL access (Render)

### Backend
```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env  # Fill in your API keys
python app.py
```

### Frontend
```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:3000 and start chatting with Baco.

## Environment Variables

Create a `.env` file in the backend directory:

```
ANTHROPIC_API_KEY=your_key
DATABASE_URL=your_postgresql_url
GEMINI_API_KEY=your_key
FLASK_PORT=5000
FLASK_ENV=development
```

## License

Proprietary. All rights reserved.
