FROM python:3.11-slim
RUN apt-get update && apt-get install -y ffmpeg git curl unzip && rm -rf /var/lib/apt/lists/*
WORKDIR /app

# Install Deno (JavaScript Runtime for yt-dlp)
RUN curl -fsSL https://deno.land/install.sh | sh
ENV DENO_INSTALL="/root/.deno"
ENV PATH="/root/.deno/bin:$PATH"

# Clone and build the PO Token Provider
RUN git clone --single-branch --branch 2.0.2 https://github.com/Brainicism/bgutil-ytdlp-pot-provider.git /bgutil
WORKDIR /bgutil/server
RUN deno install --allow-scripts=npm:canvas --frozen

# Set up the Python App
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

# Start the PO Token Provider server in the background, then start Flask
CMD ["sh", "-c", "cd /bgutil/server && deno run --allow-all --allow-scripts=npm:canvas src/main.ts & python app.py"]
