
# Paycheck Digest – Deployment Ready

This project bundles a FastAPI backend with a React + Vite frontend for parsing pay‑stub PDFs.

## Quickstart

1. Copy `.env.example` to `.env` and fill in `OPENAI_API_KEY`.
2. Build and run via Docker:
   ```bash
   docker-compose up --build
   ```
3. Open http://localhost:8080 in your browser.

## Endpoints

- **GET /** → Frontend UI  
- **GET /health**  
- **POST /digest** (form-data `file`: PDF or ZIP)  
- **GET /history**  
- **GET /analytics**

## CI

GitHub Actions builds the frontend and runs backend tests on push.
