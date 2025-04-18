# Stage 1: Build the React front‑end
FROM node:18-alpine AS web-builder
WORKDIR /web

# Copy the entire front‑end source
COPY web/ . 

# Install dependencies and build
RUN npm install
RUN npm run build

# Stage 2: Build the FastAPI backend
FROM python:3.11-slim
WORKDIR /app

# Install lib needed by PyMuPDF
RUN apt-get update && apt-get install -y libmupdf-dev && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the app code
COPY app/ ./app/

# Copy the built front‑end into the 'static' directory
COPY --from=web-builder /web/dist ./static

# Expose port and start the server
EXPOSE 8080
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
